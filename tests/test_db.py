"""Pruebas de clientes, facturas, saldos y relación con WhatsApp."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import app.config as config
import app.db as db
from app.clients import create_client, get_client_by_nit, get_client_by_whatsapp, update_client
from app.conversation import handle_conversation
from app.db import (
    INV_PAGADA,
    INV_PAGADA_PARCIAL,
    INV_PENDIENTE,
    PAY_CONFIRMADO,
    PAY_PENDIENTE,
    init_db,
)
from app.invoice_service import get_invoice_from_message
from app.invoices import (
    apply_saldo_reduction,
    create_invoice,
    get_invoice_by_id,
    get_invoices_by_whatsapp,
    get_pending_invoices,
    validate_saldo,
)
from app.payments import confirm_payment, create_payment, get_payment_by_id
from app.payments_api import PaymentConfirmBody, confirm_payment_endpoint
from app.sessions import reset_session
from app.webhook import receive_webhook


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        if self.db_path.exists():
            self.db_path.unlink()
        config.DATABASE_PATH = str(self.db_path)
        db._DB_PATH = self.db_path
        init_db()

    def tearDown(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

    def test_crear_cliente(self) -> None:
        client = create_client(
            whatsapp_id="59171110001",
            nombre="Test User",
            nit="9988776655",
            documento="CI-T1",
            email="test@example.com",
        )
        self.assertEqual(client["whatsapp_id"], "59171110001")
        self.assertEqual(client["nombre"], "Test User")
        self.assertEqual(client["nit"], "9988776655")
        self.assertTrue(client["activo"])
        self.assertIsNotNone(client["created_at"])

    def test_buscar_cliente_por_whatsapp(self) -> None:
        create_client(whatsapp_id="59171110002", nombre="Buscable")
        found = get_client_by_whatsapp("59171110002")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["nombre"], "Buscable")
        self.assertIsNone(get_client_by_whatsapp("00000000000"))

    def test_nit_opcional_y_busqueda(self) -> None:
        sin_nit = create_client(whatsapp_id="59171110020", nombre="Sin Identificacion")
        self.assertIsNone(sin_nit["nit"])
        con_nit = create_client(
            whatsapp_id="59171110021",
            nombre="Con Identificacion",
            nit="1122334455",
        )
        found = get_client_by_nit("1122334455")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["id"], con_nit["id"])
        reset_session(con_nit["whatsapp_id"])
        reply = handle_conversation(con_nit["whatsapp_id"], "hola")
        self.assertNotIn("1122334455", reply)

    def test_actualizar_identidad_cliente(self) -> None:
        client = create_client(
            whatsapp_id="59171110030",
            nombre="Editable",
            documento="CI-OLD",
        )
        updated = update_client(
            client["id"],
            nit="5566778899",
            documento="CI-NEW",
            email="nuevo@example.com",
        )
        self.assertEqual(updated["nit"], "5566778899")
        self.assertEqual(updated["documento"], "CI-NEW")
        self.assertEqual(updated["email"], "nuevo@example.com")
        by_nit = get_client_by_nit("5566778899")
        self.assertIsNotNone(by_nit)
        # Limpiar NIT sin tocar el chat
        cleared = update_client(client["id"], nit=None)
        self.assertIsNone(cleared["nit"])
        self.assertIsNone(get_client_by_nit("5566778899"))

    def test_limpiar_email_no_se_restaura_por_seed(self) -> None:
        """init_db/_seed no debe reponer email demo tras borrar a NULL."""
        ana = get_client_by_whatsapp("59176710767")
        self.assertIsNotNone(ana)
        cleared = update_client(ana["id"], email=None)
        self.assertIsNone(cleared["email"])
        init_db()
        again = get_client_by_whatsapp("59176710767")
        self.assertIsNotNone(again)
        self.assertIsNone(again["email"])

    def test_crear_factura_y_relacion(self) -> None:
        client = create_client(whatsapp_id="59171110003", nombre="Con Factura")
        inv = create_invoice(
            number="F-9001",
            cliente_id=client["id"],
            monto_original=100.0,
            fecha_vencimiento="2026-12-01",
            descripcion="Prueba",
        )
        self.assertEqual(inv["cliente_id"], client["id"])
        self.assertEqual(inv["monto_original"], 100.0)
        self.assertEqual(inv["saldo"], 100.0)
        self.assertEqual(inv["estado"], INV_PENDIENTE)

        all_inv = get_invoices_by_whatsapp("59171110003")
        self.assertEqual(len(all_inv), 1)
        self.assertEqual(all_inv[0]["number"], "F-9001")

    def test_consultar_y_filtrar_pendientes(self) -> None:
        client = create_client(whatsapp_id="59171110004", nombre="Varias")
        create_invoice(
            number="F-9002",
            cliente_id=client["id"],
            monto_original=200.0,
            saldo=200.0,
            fecha_vencimiento="2026-12-01",
        )
        create_invoice(
            number="F-9003",
            cliente_id=client["id"],
            monto_original=50.0,
            saldo=0.0,
            fecha_vencimiento="2026-11-01",
            estado=INV_PAGADA,
        )
        create_invoice(
            number="F-9004",
            cliente_id=client["id"],
            monto_original=80.0,
            saldo=40.0,
            fecha_vencimiento="2026-12-15",
            estado=INV_PAGADA_PARCIAL,
        )

        all_inv = get_invoices_by_whatsapp("59171110004")
        pending = get_pending_invoices(client["id"])
        self.assertEqual(len(all_inv), 3)
        self.assertEqual(len(pending), 2)
        self.assertTrue(all(p["saldo"] > 0 for p in pending))
        numbers = {p["number"] for p in pending}
        self.assertEqual(numbers, {"F-9002", "F-9004"})

    def test_calcular_saldo_y_pago_parcial(self) -> None:
        client = create_client(whatsapp_id="59171110005", nombre="Parcial")
        inv = create_invoice(
            number="F-9005",
            cliente_id=client["id"],
            monto_original=100.0,
            fecha_vencimiento="2026-12-01",
        )
        updated = apply_saldo_reduction(inv["id"], 30.0)
        self.assertEqual(updated["saldo"], 70.0)
        self.assertEqual(updated["estado"], INV_PAGADA_PARCIAL)

        payment = create_payment(
            cliente_id=client["id"],
            factura_id=inv["id"],
            monto=70.0,
        )
        self.assertEqual(payment["estado"], PAY_PENDIENTE)
        # PENDIENTE no mueve saldo
        still = get_invoices_by_whatsapp("59171110005")[0]
        self.assertEqual(still["saldo"], 70.0)

        confirmed = confirm_payment(payment["id"], referencia_externa="DEMO-REF")
        self.assertEqual(confirmed["estado"], PAY_CONFIRMADO)
        paid = get_invoices_by_whatsapp("59171110005")[0]
        self.assertEqual(paid["saldo"], 0.0)
        self.assertEqual(paid["estado"], INV_PAGADA)

    def test_evitar_saldo_negativo(self) -> None:
        with self.assertRaises(ValueError):
            validate_saldo(100.0, -1.0)
        client = create_client(whatsapp_id="59171110006", nombre="Negativo")
        with self.assertRaises(ValueError):
            create_invoice(
                number="F-9006",
                cliente_id=client["id"],
                monto_original=50.0,
                saldo=-5.0,
                fecha_vencimiento="2026-12-01",
            )
        inv = create_invoice(
            number="F-9007",
            cliente_id=client["id"],
            monto_original=50.0,
            fecha_vencimiento="2026-12-01",
        )
        with self.assertRaises(ValueError):
            apply_saldo_reduction(inv["id"], 60.0)

    def test_seed_ana_tiene_varias_facturas(self) -> None:
        ana = get_client_by_whatsapp("59176710767")
        self.assertIsNotNone(ana)
        assert ana is not None
        self.assertEqual(ana["nit"], "1020304019")
        all_inv = get_invoices_by_whatsapp("59176710767")
        pending = get_pending_invoices(ana["id"])
        self.assertGreaterEqual(len(all_inv), 4)
        self.assertGreaterEqual(len(pending), 2)
        self.assertTrue(all(p["saldo"] > 0 for p in pending))
        # NIT no se expone en el menú de WhatsApp
        reset_session("59176710767")
        reply = handle_conversation("59176710767", "hola")
        self.assertNotIn(ana["nit"], reply)

    def test_flujo_whatsapp_y_legacy(self) -> None:
        reset_session("59176710767")
        reply = handle_conversation("59176710767", "hola")
        self.assertIn("F1001", reply)
        self.assertIn("PEND", reply)
        # pagadas/anuladas no deben listarse como pendientes
        self.assertNotIn("F-1006", reply)

        inv = get_invoice_from_message("Factura F-1001")
        self.assertIsNotNone(inv)
        assert inv is not None
        self.assertEqual(inv["number"], "F-1001")
        self.assertEqual(inv["customer"], "Ana López")

    def test_webhook_responde(self) -> None:
        async def _run() -> None:
            req = MagicMock()
            req.json = AsyncMock(
                return_value={
                    "entry": [
                        {
                            "changes": [
                                {
                                    "value": {
                                        "messages": [
                                            {
                                                "from": "59176710767",
                                                "text": {"body": "hola"},
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            with patch("app.webhook.send_message", return_value=True) as sm:
                out = await receive_webhook(req)
                self.assertEqual(out, {"status": "ok"})
                self.assertTrue(sm.called)
                self.assertIn("facturas pendientes", sm.call_args[0][1].lower())

        import asyncio

        asyncio.run(_run())

    def test_payments_confirm_endpoint(self) -> None:
        import app.config as cfg

        cfg.PAYMENTS_CONFIRM_TOKEN = "test-secret-token"
        client = create_client(whatsapp_id="59171110040", nombre="Pago API")
        inv = create_invoice(
            number="F-9100",
            cliente_id=client["id"],
            monto_original=100.0,
            fecha_vencimiento="2026-12-01",
        )
        payment = create_payment(
            cliente_id=client["id"],
            factura_id=inv["id"],
            monto=40.0,
        )
        self.assertEqual(payment["estado"], PAY_PENDIENTE)

        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TEST-REF",
                monto=40.0,
                moneda="BOB",
                notificar_whatsapp=True,
            )
            req = MagicMock()
            req.headers = {"Authorization": "Bearer test-secret-token"}
            with patch("app.payments_api.send_message", return_value=True) as sm:
                out = await confirm_payment_endpoint(body, req)
                self.assertEqual(out["status"], "ok")
                self.assertEqual(out["payment"]["estado"], PAY_CONFIRMADO)
                self.assertEqual(out["invoice"]["saldo"], 60.0)
                self.assertTrue(out["whatsapp_notificado"])
                self.assertTrue(sm.called)
                self.assertIn("Pago confirmado", sm.call_args[0][1])

        import asyncio

        asyncio.run(_run())
        updated_pay = get_payment_by_id(payment["id"])
        assert updated_pay is not None
        self.assertEqual(updated_pay["referencia_externa"], "TEST-REF")
        updated_inv = get_invoice_by_id(inv["id"])
        assert updated_inv is not None
        self.assertEqual(updated_inv["saldo"], 60.0)
        self.assertEqual(updated_inv["estado"], INV_PAGADA_PARCIAL)


if __name__ == "__main__":
    unittest.main()
