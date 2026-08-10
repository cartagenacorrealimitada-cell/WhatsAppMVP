"""Pruebas de comandos de chat: cancelar y mis pagos."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app.config as config
import app.db as db
from app.clients import create_client
from app.conversation import handle_conversation
from app.db import STATE_SELECT_INVOICE, init_db
from app.invoices import create_invoice
from app.payments import create_payment
from app.sessions import get_session, reset_session


class ConversationCommandsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        if self.db_path.exists():
            self.db_path.unlink()
        config.DATABASE_PATH = str(self.db_path)
        db._DB_PATH = self.db_path
        init_db()
        self.wa = "59171118801"
        self.client = create_client(whatsapp_id=self.wa, nombre="Cmd User")
        self.invoice = create_invoice(
            number="R-CMD-1",
            cliente_id=self.client["id"],
            monto_original=80.0,
            fecha_vencimiento="2026-12-31",
        )

    def tearDown(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

    def test_cancelar_desde_seleccion(self) -> None:
        reset_session(self.wa)
        handle_conversation(self.wa, "hola")
        handle_conversation(self.wa, "1")
        session = get_session(self.wa)
        assert session is not None
        self.assertEqual(session["state"], STATE_SELECT_INVOICE)

        reply = handle_conversation(self.wa, "cancelar")
        self.assertIn("cancelada", reply.lower())
        session = get_session(self.wa)
        assert session is not None
        self.assertEqual(session["state"], "START")
        self.assertIsNone(session["selected_invoice_id"])

    def test_mis_pagos_vacio(self) -> None:
        reset_session(self.wa)
        reply = handle_conversation(self.wa, "mis pagos")
        self.assertIn("Sin pagos registrados", reply)
        self.assertIn("Cliente:", reply)
        self.assertIn("```", reply)

    def test_mis_pagos_lista(self) -> None:
        pay = create_payment(
            cliente_id=self.client["id"],
            factura_id=self.invoice["id"],
            monto=25.0,
        )
        reply = handle_conversation(self.wa, "pagos")
        self.assertIn(str(pay["id"]), reply)
        self.assertIn("RCMD1", reply)
        self.assertIn("PEND", reply)
        self.assertIn("25.00", reply)
        self.assertIn("Doc", reply)
        self.assertIn("+", reply)
        self.assertIn("|", reply)
        self.assertIn("```", reply)

    def test_facturas_tabla_educate(self) -> None:
        reset_session(self.wa)
        reply = handle_conversation(self.wa, "hola")
        self.assertIn("Cliente:", reply)
        self.assertIn("Saldos pendientes:", reply)
        self.assertIn("RCMD1", reply)
        self.assertIn("Saldo", reply)
        self.assertIn("Doc", reply)
        self.assertIn("TOTAL", reply)
        self.assertIn("+---+", reply)
        self.assertIn("```", reply)
        self.assertIn("F=factura", reply)

    def test_cancelar_en_confirmacion(self) -> None:
        reset_session(self.wa)
        handle_conversation(self.wa, "hola")
        handle_conversation(self.wa, "1")
        handle_conversation(self.wa, "10")
        reply = handle_conversation(self.wa, "no")
        self.assertIn("cancelada", reply.lower())

    def test_cancelar_desde_lista(self) -> None:
        reset_session(self.wa)
        handle_conversation(self.wa, "hola")
        reply = handle_conversation(self.wa, "salir")
        self.assertIn("cancelada", reply.lower())
        session = get_session(self.wa)
        assert session is not None
        self.assertEqual(session["state"], "START")

    def test_si_crea_pago_pendiente(self) -> None:
        reset_session(self.wa)
        handle_conversation(self.wa, "hola")
        handle_conversation(self.wa, "1")
        handle_conversation(self.wa, "10")
        reply = handle_conversation(self.wa, "si")
        self.assertIn("PENDIENTE", reply)
        self.assertIn("pago #", reply.lower())
        listed = handle_conversation(self.wa, "mis pagos")
        self.assertIn("PEND", listed)
        self.assertIn("10.00", listed)


if __name__ == "__main__":
    unittest.main()
