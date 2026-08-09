"""Pruebas del importador administrativo CSV (clientes + facturas)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app.config as config
import app.db as db
from app.clients import create_client, get_client_by_whatsapp
from app.csv_import import run_import
from app.db import init_db
from app.invoices import get_invoice, get_invoices_by_cliente_id


class CsvImportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        if self.db_path.exists():
            self.db_path.unlink()
        config.DATABASE_PATH = str(self.db_path)
        db._DB_PATH = self.db_path
        init_db()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        if self.db_path.exists():
            self.db_path.unlink()

    def _write(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_importar_cliente(self) -> None:
        path = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            "59170000001,Ana Uno,111,CI-1,59170000001,ana@ex.com,1\n",
        )
        summary = run_import(clients_csv=path)
        self.assertEqual(summary.clientes_leidos, 1)
        self.assertEqual(summary.clientes_creados, 1)
        self.assertEqual(summary.clientes_con_error, 0)
        client = get_client_by_whatsapp("59170000001")
        self.assertIsNotNone(client)
        assert client is not None
        self.assertEqual(client["nombre"], "Ana Uno")
        self.assertEqual(client["nit"], "111")

    def test_importar_varios_clientes(self) -> None:
        path = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            "59170000011,A,,CI-A,,a@ex.com,1\n"
            "59170000012,B,222,CI-B,,b@ex.com,1\n"
            "59170000013,C,333,CI-C,,c@ex.com,0\n",
        )
        summary = run_import(clients_csv=path)
        self.assertEqual(summary.clientes_leidos, 3)
        self.assertEqual(summary.clientes_creados, 3)
        self.assertEqual(summary.clientes_con_error, 0)

    def test_nit_opcional(self) -> None:
        path = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            "59170000021,Sin Nit,,DOC-X,,,1\n",
        )
        summary = run_import(clients_csv=path)
        self.assertEqual(summary.clientes_creados, 1)
        client = get_client_by_whatsapp("59170000021")
        assert client is not None
        self.assertIsNone(client["nit"])

    def test_evitar_duplicados(self) -> None:
        create_client(whatsapp_id="59170000031", nombre="Existente", nit="999001")
        path = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            "59170000031,Existente,999001,,,e@ex.com,1\n"
            "59170000032,Nuevo,999002,,,n@ex.com,1\n",
        )
        summary = run_import(clients_csv=path)
        self.assertEqual(summary.clientes_leidos, 2)
        self.assertEqual(summary.clientes_creados, 1)
        self.assertEqual(summary.clientes_omitidos, 1)
        self.assertEqual(summary.clientes_con_error, 0)

    def test_importar_factura_y_cliente_id(self) -> None:
        client = create_client(whatsapp_id="59170000041", nombre="Con Factura")
        path = self._write(
            "facturas.csv",
            "number,cliente_id,descripcion,monto_original,saldo,"
            "fecha_emision,fecha_vencimiento,estado\n"
            f"F-CSV-1,{client['id']},Demo,100.00,100.00,2026-01-01,2026-12-31,PENDIENTE\n",
        )
        summary = run_import(invoices_csv=path)
        self.assertEqual(summary.facturas_leidas, 1)
        self.assertEqual(summary.facturas_creadas, 1)
        inv = get_invoice("F-CSV-1")
        self.assertIsNotNone(inv)
        assert inv is not None
        self.assertEqual(inv["cliente_id"], client["id"])
        linked = get_invoices_by_cliente_id(client["id"])
        self.assertEqual(len(linked), 1)

    def test_saldo_negativo(self) -> None:
        client = create_client(whatsapp_id="59170000051", nombre="Neg")
        path = self._write(
            "facturas.csv",
            "number,cliente_id,descripcion,monto_original,saldo,"
            "fecha_emision,fecha_vencimiento,estado\n"
            f"F-NEG,{client['id']},Bad,50.00,-1,2026-01-01,2026-12-31,PENDIENTE\n",
        )
        summary = run_import(invoices_csv=path)
        self.assertEqual(summary.facturas_con_error, 1)
        self.assertEqual(summary.facturas_creadas, 0)
        self.assertIsNone(get_invoice("F-NEG"))
        self.assertTrue(any(e.campo == "saldo" for e in summary.errores))

    def test_saldo_superior_monto(self) -> None:
        client = create_client(whatsapp_id="59170000052", nombre="Over")
        path = self._write(
            "facturas.csv",
            "number,cliente_id,descripcion,monto_original,saldo,"
            "fecha_emision,fecha_vencimiento,estado\n"
            f"F-OVER,{client['id']},Bad,50.00,60,2026-01-01,2026-12-31,PENDIENTE\n",
        )
        summary = run_import(invoices_csv=path)
        self.assertEqual(summary.facturas_con_error, 1)
        self.assertIsNone(get_invoice("F-OVER"))

    def test_cliente_inexistente(self) -> None:
        path = self._write(
            "facturas.csv",
            "number,cliente_id,descripcion,monto_original,saldo,"
            "fecha_emision,fecha_vencimiento,estado\n"
            "F-NOCLI,99999,Bad,10.00,10.00,2026-01-01,2026-12-31,PENDIENTE\n",
        )
        summary = run_import(invoices_csv=path)
        self.assertEqual(summary.facturas_con_error, 1)
        self.assertTrue(any(e.campo == "cliente_id" for e in summary.errores))

    def test_fila_invalida(self) -> None:
        path = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            ",SinWhatsapp,,,,,,\n",
        )
        summary = run_import(clients_csv=path)
        self.assertEqual(summary.clientes_con_error, 1)
        self.assertEqual(summary.clientes_creados, 0)
        self.assertTrue(any(e.campo == "whatsapp_id" for e in summary.errores))

    def test_importacion_parcialmente_exitosa(self) -> None:
        client = create_client(whatsapp_id="59170000061", nombre="Parcial")
        clientes = self._write(
            "clientes.csv",
            "whatsapp_id,nombre,nit,documento,telefono,email,activo\n"
            "59170000062,Ok,,DOC-OK,,,1\n"
            ",FaltaId,,,,,,\n"
            "59170000061,Duplicado,,,,,1\n",
        )
        facturas = self._write(
            "facturas.csv",
            "number,cliente_id,descripcion,monto_original,saldo,"
            "fecha_emision,fecha_vencimiento,estado\n"
            f"F-OK,{client['id']},Good,40.00,40.00,2026-01-01,2026-12-31,PENDIENTE\n"
            f"F-BAD,{client['id']},Bad,40.00,99.00,2026-01-01,2026-12-31,PENDIENTE\n",
        )
        summary = run_import(clients_csv=clientes, invoices_csv=facturas)
        self.assertEqual(summary.clientes_creados, 1)
        self.assertEqual(summary.clientes_omitidos, 1)
        self.assertEqual(summary.clientes_con_error, 1)
        self.assertEqual(summary.facturas_creadas, 1)
        self.assertEqual(summary.facturas_con_error, 1)
        self.assertIsNotNone(get_invoice("F-OK"))
        self.assertIsNone(get_invoice("F-BAD"))


if __name__ == "__main__":
    unittest.main()
