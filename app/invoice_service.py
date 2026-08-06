"""Servicio de aplicación: coordina parser y consulta SQLite."""

from app.invoices import get_invoice
from app.parser import parse_invoice_number


def get_invoice_from_message(text: str) -> dict | None:
    """Extrae el número de factura del mensaje y consulta SQLite."""
    number = parse_invoice_number(text)
    if number is None:
        return None

    return get_invoice(number)
