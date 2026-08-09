"""
CLI administrativo: importar clientes y facturas desde CSV.
No está expuesto por FastAPI ni WhatsApp.

Uso:
  python scripts/import_csv.py --clientes data/ejemplos/clientes.csv --facturas data/ejemplos/facturas.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.csv_import import run_import  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importación administrativa CSV (clientes → facturas por cliente_id)."
    )
    parser.add_argument(
        "--clientes",
        type=Path,
        help="Ruta a clientes.csv",
    )
    parser.add_argument(
        "--facturas",
        type=Path,
        help="Ruta a facturas.csv (usar cliente_id, no whatsapp_id)",
    )
    args = parser.parse_args()
    if not args.clientes and not args.facturas:
        parser.error("Indica --clientes y/o --facturas")

    summary = run_import(clients_csv=args.clientes, invoices_csv=args.facturas)
    summary.print_report()
    if summary.clientes_con_error or summary.facturas_con_error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
