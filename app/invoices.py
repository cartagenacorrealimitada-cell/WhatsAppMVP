"""Consulta de facturas en SQLite."""

import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH

_DB_PATH = Path(__file__).resolve().parent.parent / DATABASE_PATH

_SEED = [
    ("F-1001", "pendiente", "Ana López"),
    ("F-1002", "pagada", "Carlos Ruiz"),
    ("F-1003", "vencida", "María Pérez"),
]


def init_db() -> None:
    """Crea la base, la tabla invoices y carga datos de prueba si está vacía."""
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                number TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                customer TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO invoices (number, status, customer) VALUES (?, ?, ?)",
                _SEED,
            )
        conn.commit()
    finally:
        conn.close()


def get_invoice(number: str) -> dict | None:
    """Devuelve la factura por número, o None si no existe."""
    conn = sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute(
            "SELECT number, status, customer FROM invoices WHERE number = ?",
            (number,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return {"number": row[0], "status": row[1], "customer": row[2]}
