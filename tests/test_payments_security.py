"""Tests de seguridad para POST /payments/confirm."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app.config as config
import app.db as db
from app.clients import create_client
from app.db import INV_PAGADA_PARCIAL, PAY_CONFIRMADO, PAY_PENDIENTE, init_db
from app.invoices import create_invoice, get_invoice_by_id
from app.payment_service import confirm_or_reject_payment
from app.payments import create_payment, get_payment_by_id
from app.payments_api import PaymentConfirmBody, confirm_payment_endpoint


class PaymentsSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        if self.db_path.exists():
            self.db_path.unlink()
        config.DATABASE_PATH = str(self.db_path)
        db._DB_PATH = self.db_path
        config.PAYMENTS_CONFIRM_TOKEN = "test-secret-token"
        # payments_auth lee el módulo al importar — reasignar en config es suficiente
        # si auth importa desde config en cada llamada (sí lo hace).
        init_db()
        self.client = create_client(whatsapp_id="59171119901", nombre="Seguro")
        self.invoice = create_invoice(
            number="F-SEC-1",
            cliente_id=self.client["id"],
            monto_original=100.0,
            fecha_vencimiento="2026-12-01",
        )
        self.payment = create_payment(
            cliente_id=self.client["id"],
            factura_id=self.invoice["id"],
            monto=40.0,
            moneda="BOB",
        )

    def tearDown(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

    def _request(self, *, token: str | None = "test-secret-token") -> MagicMock:
        req = MagicMock()
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req.headers = headers
        return req

    def test_confirmacion_valida(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-OK-1",
                monto=40.0,
                moneda="BOB",
            )
            with patch("app.payments_api.send_message", return_value=True):
                out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out["status"], "ok")
            self.assertEqual(out["result"], "confirmed")
            self.assertEqual(out["payment"]["estado"], PAY_CONFIRMADO)
            self.assertEqual(out["invoice"]["saldo"], 60.0)

        import asyncio

        asyncio.run(_run())

    def test_sin_autenticacion(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-NOAUTH",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(body, self._request(token=None))
            self.assertEqual(out.status_code, 401)
            pay = get_payment_by_id(self.payment["id"])
            self.assertEqual(pay["estado"], PAY_PENDIENTE)
            inv = get_invoice_by_id(self.invoice["id"])
            self.assertEqual(inv["saldo"], 100.0)

        import asyncio

        asyncio.run(_run())

    def test_token_incorrecto(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-BADTOK",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(
                body, self._request(token="wrong-token")
            )
            self.assertEqual(out.status_code, 401)
            self.assertEqual(get_payment_by_id(self.payment["id"])["estado"], PAY_PENDIENTE)

        import asyncio

        asyncio.run(_run())

    def test_payload_invalido_resultado(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="PAGADO",
                referencia_externa="TXN-BADRES",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 400)

        import asyncio

        asyncio.run(_run())

    def test_pago_inexistente(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=999999,
                resultado="CONFIRMADO",
                referencia_externa="TXN-MISS",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 404)

        import asyncio

        asyncio.run(_run())

    def test_referencia_incorrecta(self) -> None:
        # Pre-asignar ref en el pago
        from app.db import get_connection

        conn = get_connection()
        conn.execute(
            "UPDATE payments SET referencia_externa = ? WHERE id = ?",
            ("TXN-FIXED", self.payment["id"]),
        )
        conn.commit()
        conn.close()

        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-OTHER",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 400)
            self.assertIn(b"referencia_externa_mismatch", out.body)

        import asyncio

        asyncio.run(_run())

    def test_monto_incorrecto(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-AMT",
                monto=99.0,
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 400)
            self.assertIn(b"monto_mismatch", out.body)

        import asyncio

        asyncio.run(_run())

    def test_moneda_incorrecta(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-CUR",
                monto=40.0,
                moneda="USD",
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 400)
            self.assertIn(b"moneda_mismatch", out.body)

        import asyncio

        asyncio.run(_run())

    def test_pago_ya_confirmado(self) -> None:
        confirm_or_reject_payment(
            payment_id=self.payment["id"],
            resultado="CONFIRMADO",
            referencia_externa="TXN-ONCE",
            monto=40.0,
            moneda="BOB",
            auth_ok=True,
            auth_method="test",
        )

        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-ONCE-2",
                monto=40.0,
            )
            out = await confirm_payment_endpoint(body, self._request())
            # ya no está PENDIENTE
            self.assertIn(out.status_code if hasattr(out, "status_code") else 200, (200, 409))
            inv = get_invoice_by_id(self.invoice["id"])
            self.assertEqual(inv["saldo"], 60.0)

        import asyncio

        asyncio.run(_run())

    def test_webhook_duplicado_misma_ref(self) -> None:
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-DUP",
                monto=40.0,
            )
            with patch("app.payments_api.send_message", return_value=True):
                out1 = await confirm_payment_endpoint(body, self._request())
                out2 = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out1["status"], "ok")
            self.assertEqual(out2["status"], "ok")
            self.assertTrue(out2["already_processed"])
            inv = get_invoice_by_id(self.invoice["id"])
            self.assertEqual(inv["saldo"], 60.0)

        import asyncio

        asyncio.run(_run())

    def test_concurrencia_misma_transaccion(self) -> None:
        results: list = []

        def worker() -> None:
            out = confirm_or_reject_payment(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-RACE",
                monto=40.0,
                moneda="BOB",
                auth_ok=True,
                auth_method="test",
            )
            results.append(out)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        confirmed = [r for r in results if r.status == "confirmed"]
        duplicates = [r for r in results if r.status == "duplicate"]
        self.assertEqual(len(confirmed) + len(duplicates), 2)
        self.assertGreaterEqual(len(confirmed), 1)
        inv = get_invoice_by_id(self.invoice["id"])
        self.assertEqual(inv["saldo"], 60.0)

    def test_rollback_si_saldo_invalido(self) -> None:
        # Forzar saldo insuficiente alterando invoice tras crear pago
        from app.db import get_connection

        conn = get_connection()
        conn.execute(
            "UPDATE invoices SET saldo = 1.0 WHERE id = ?",
            (self.invoice["id"],),
        )
        conn.commit()
        conn.close()

        out = confirm_or_reject_payment(
            payment_id=self.payment["id"],
            resultado="CONFIRMADO",
            referencia_externa="TXN-ROLL",
            monto=40.0,
            moneda="BOB",
            auth_ok=True,
            auth_method="test",
        )
        self.assertEqual(out.status, "error")
        pay = get_payment_by_id(self.payment["id"])
        self.assertEqual(pay["estado"], PAY_PENDIENTE)

    def test_saldo_una_sola_vez(self) -> None:
        confirm_or_reject_payment(
            payment_id=self.payment["id"],
            resultado="CONFIRMADO",
            referencia_externa="TXN-ONCE-SALDO",
            monto=40.0,
            moneda="BOB",
            auth_ok=True,
            auth_method="test",
        )
        confirm_or_reject_payment(
            payment_id=self.payment["id"],
            resultado="CONFIRMADO",
            referencia_externa="TXN-ONCE-SALDO",
            monto=40.0,
            moneda="BOB",
            auth_ok=True,
            auth_method="test",
        )
        inv = get_invoice_by_id(self.invoice["id"])
        self.assertEqual(inv["saldo"], 60.0)
        self.assertEqual(inv["estado"], INV_PAGADA_PARCIAL)

    def test_datos_externos_manipulados_no_aceptados(self) -> None:
        # El body del API no incluye cliente_id/invoice_id; monto manipulado se rechaza
        async def _run() -> None:
            body = PaymentConfirmBody(
                payment_id=self.payment["id"],
                resultado="CONFIRMADO",
                referencia_externa="TXN-MANIP",
                monto=1.0,  # mentira
            )
            out = await confirm_payment_endpoint(body, self._request())
            self.assertEqual(out.status_code, 400)
            self.assertEqual(get_payment_by_id(self.payment["id"])["estado"], PAY_PENDIENTE)

        import asyncio

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
