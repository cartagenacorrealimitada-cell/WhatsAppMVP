"""Formato único de tablas ASCII para WhatsApp (saldos y pagos)."""

from __future__ import annotations

_ESTADO_CORTO = {
    "PENDIENTE": "PEND",
    "PAGADA_PARCIAL": "PARC",
    "PAGADA": "PAG",
    "VENCIDA": "VENC",
    "ANULADA": "ANUL",
    "CONFIRMADO": "OK",
    "RECHAZADO": "RECH",
    "ANULADO": "ANUL",
}


def doc_prefix_for_client(*, nit: str | None) -> str:
    """F = factura (con NIT); R = recibo (sin NIT)."""
    if nit and str(nit).strip():
        return "F"
    return "R"


def doc_corto(number: str) -> str:
    """F-1007 / R-B001 -> F1007 / RB001 (compacto, sin guion)."""
    return str(number).replace("-", "").replace(" ", "")


def estado_corto(estado: str) -> str:
    return _ESTADO_CORTO.get(str(estado), str(estado)[:4])


def _pad(text: str, width: int, *, align: str = "left") -> str:
    t = str(text)
    if len(t) > width:
        t = t[:width]
    if align == "right":
        return t.rjust(width)
    if align == "center":
        return t.center(width)
    return t.ljust(width)


def ascii_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    aligns: list[str] | None = None,
) -> str:
    n = len(headers)
    aligns = aligns or ["left"] * n
    width = [len(h) for h in headers]
    norm: list[list[str]] = []
    for row in rows:
        cells = [str(row[i]) if i < len(row) else "" for i in range(n)]
        norm.append(cells)
        for i, cell in enumerate(cells):
            width[i] = max(width[i], len(cell))

    def sep() -> str:
        return "+" + "+".join("-" * (w + 2) for w in width) + "+"

    def line(cells: list[str], *, header: bool = False) -> str:
        parts: list[str] = []
        for i, cell in enumerate(cells):
            a = "center" if header else aligns[i]
            parts.append(f" {_pad(cell, width[i], align=a)} ")
        return "|" + "|".join(parts) + "|"

    out = [sep(), line(headers, header=True), sep()]
    for row in norm:
        out.append(line(row))
    out.append(sep())
    return "\n".join(out)


def mono_block(table: str) -> str:
    return f"```{table.strip()}```"


def format_saldos_table(
    invoices: list[dict],
    *,
    cliente_nombre: str,
) -> str:
    """Formato único: Cliente + Saldos pendientes + tabla Doc/Saldo/Est + Total."""
    rows: list[list[str]] = []
    total = 0.0
    for idx, inv in enumerate(invoices, start=1):
        saldo = float(inv["saldo"])
        total += saldo
        rows.append(
            [
                str(idx),
                doc_corto(inv["number"]),
                f"{saldo:.2f}",
                estado_corto(str(inv["estado"])),
            ]
        )
    if invoices:
        rows.append(["", "TOTAL", f"{total:.2f}", ""])
    table = ascii_table(
        ["#", "Doc", "Saldo", "Est"],
        rows,
        aligns=["center", "left", "right", "left"],
    )
    lines = [
        f"Cliente: {cliente_nombre}",
        "Saldos pendientes:",
        "F=factura (con NIT) · R=recibo (sin NIT)",
        mono_block(table),
    ]
    if not invoices:
        lines.append("Sin documentos pendientes.")
    else:
        lines.append("Responde # (ej. 1) o codigo (ej. F1001 / R1001).")
    lines.append("Tambien: mis pagos | cancelar | hola")
    return "\n".join(lines)


def format_pagos_table(
    payments: list[dict],
    *,
    cliente_nombre: str,
) -> str:
    """Formato único para historial de pagos + Total."""
    rows: list[list[str]] = []
    total = 0.0
    for pay in payments:
        number = pay.get("factura_number") or f"#{pay['factura_id']}"
        monto = float(pay["monto"])
        total += monto
        rows.append(
            [
                str(pay["id"]),
                doc_corto(str(number)),
                f"{monto:.2f}",
                estado_corto(str(pay["estado"])),
            ]
        )
    if payments:
        rows.append(["", "TOTAL", f"{total:.2f}", ""])
    table = ascii_table(
        ["#", "Doc", "Monto", "Est"],
        rows,
        aligns=["center", "left", "right", "left"],
    )
    lines = [
        f"Cliente: {cliente_nombre}",
        "Historial de pagos:",
        "F=factura (con NIT) · R=recibo (sin NIT)",
        mono_block(table),
    ]
    if not payments:
        lines.append("Sin pagos registrados.")
    lines.append("Escribe hola para saldos, o cancelar para salir.")
    return "\n".join(lines)
