"""Extracción del número de factura desde un mensaje de texto."""

import re

_INVOICE_PATTERN = re.compile(r"F\s*-\s*(\d+)", re.IGNORECASE)


def parse_invoice_number(text: str) -> str | None:
    """Devuelve el número de factura normalizado (ej. F-1001) o None."""
    if not text:
        return None

    match = _INVOICE_PATTERN.search(text)
    if match is None:
        return None

    return f"F-{match.group(1)}"
