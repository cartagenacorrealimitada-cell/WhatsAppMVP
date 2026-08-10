"""Motor de conversación: clientes, facturas pendientes y selección de monto."""

from __future__ import annotations

import re

from app.clients import get_client_by_whatsapp
from app.db import (
    STATE_CONFIRM_AMOUNT,
    STATE_SELECT_INVOICE,
    STATE_SHOW_INVOICES,
    STATE_START,
)
from app.invoices import get_invoice_by_id, get_pending_invoices
from app.payments import create_payment, get_payments_by_cliente_id
from app.sessions import get_or_create_session, reset_session, update_session

_MENU_WORDS = {"menu", "menú", "hola", "hi", "inicio", "facturas", "deudas"}
_CANCEL_WORDS = {"cancelar", "cancel", "salir", "abortar"}
_PAYMENTS_WORDS = {"mis pagos", "pagos", "mispagos"}


def _ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    """Tabla ASCII simple (estilo MySQL CLI)."""
    cols = list(headers)
    width = [len(h) for h in cols]
    norm_rows: list[list[str]] = []
    for row in rows:
        cells = [str(row[i]) if i < len(row) else "" for i in range(len(cols))]
        norm_rows.append(cells)
        for i, cell in enumerate(cells):
            width[i] = max(width[i], len(cell))

    def sep() -> str:
        return "+" + "+".join("-" * (w + 2) for w in width) + "+"

    def line(cells: list[str]) -> str:
        parts = [f" {cells[i].ljust(width[i])} " for i in range(len(cols))]
        return "|" + "|".join(parts) + "|"

    out = [sep(), line(cols), sep()]
    for row in norm_rows:
        out.append(line(row))
    out.append(sep())
    return "\n".join(out)


def _whatsapp_table_block(table: str) -> str:
    """
    WhatsApp alinea columnas solo en monoespaciado.
    Un bloque multilínea a menudo falla en el celular; una línea = un ```...```.
    """
    lines = table.strip("\n").split("\n")
    return "\n".join(f"```{line}```" for line in lines)


def _format_invoice_list(invoices: list[dict]) -> str:
    rows: list[list[str]] = []
    for idx, inv in enumerate(invoices, start=1):
        estado = str(inv["estado"])
        if estado == "PAGADA_PARCIAL":
            estado = "PARCIAL"
        rows.append(
            [
                str(idx),
                str(inv["number"]),
                f"{float(inv['saldo']):.2f}",
                str(inv["fecha_vencimiento"]),
                estado,
            ]
        )
    table = _ascii_table(["#", "Factura", "Saldo", "Vence", "Estado"], rows)
    return (
        "*Tus facturas pendientes*\n"
        f"{_whatsapp_table_block(table)}\n"
        "Responde con el *#* (ej. 1) o el código (ej. F-B001).\n"
        "También: *mis pagos* | *cancelar* | *hola*"
    )


def _format_payments_list(payments: list[dict]) -> str:
    if not payments:
        return (
            "No tienes solicitudes de pago registradas.\n"
            "Escribe *hola* para ver tus facturas."
        )
    rows: list[list[str]] = []
    for pay in payments:
        number = pay.get("factura_number") or f"#{pay['factura_id']}"
        rows.append(
            [
                str(pay["id"]),
                str(number),
                f"{float(pay['monto']):.2f}",
                str(pay["estado"]),
            ]
        )
    table = _ascii_table(["Id", "Factura", "Monto", "Estado"], rows)
    return (
        "*Tus últimos pagos*\n"
        f"{_whatsapp_table_block(table)}\n"
        "Escribe *hola* para ver facturas, o *cancelar* para salir."
    )


def _parse_amount(text: str, balance: float) -> float | None:
    cleaned = text.strip().lower().replace(",", ".")
    if cleaned in {"total", "todo", "saldo"}:
        return balance
    match = re.fullmatch(r"\d+(?:\.\d{1,2})?", cleaned)
    if match is None:
        return None
    amount = float(match.group(0))
    if amount <= 0 or amount > balance:
        return None
    return amount


def _resolve_invoice_choice(text: str, invoices: list[dict]) -> dict | None:
    cleaned = text.strip().upper().replace(" ", "")
    # índice 1..n
    if re.fullmatch(r"\d+", text.strip()):
        idx = int(text.strip())
        if 1 <= idx <= len(invoices):
            return invoices[idx - 1]
    # por número de factura
    for inv in invoices:
        if inv["number"].upper().replace(" ", "") == cleaned:
            return inv
        if cleaned == inv["number"].upper():
            return inv
    # F-1001 con espacios
    compact = re.sub(r"\s+", "", text.strip().upper())
    for inv in invoices:
        if inv["number"].upper() == compact:
            return inv
    return None


def handle_conversation(whatsapp_id: str, text: str) -> str:
    """
    Gestiona el diálogo de saldos y solicitudes PENDIENTE (sin QR/proveedor).
    Devuelve el texto a enviar al usuario.
    """
    client = get_client_by_whatsapp(whatsapp_id)
    if client is None:
        return (
            "No encontramos un cliente activo con este WhatsApp. "
            "Contacta a soporte para registrarte."
        )

    session = get_or_create_session(whatsapp_id)
    state = session["state"]
    pending = get_pending_invoices(client["id"])
    normalized = text.strip().lower()

    # Comandos globales (cualquier estado)
    if normalized in _CANCEL_WORDS:
        reset_session(whatsapp_id)
        return "Operación cancelada. Escribe hola para ver tus facturas."

    if normalized in _PAYMENTS_WORDS:
        payments = get_payments_by_cliente_id(client["id"], limit=10)
        return _format_payments_list(payments)

    if normalized in _MENU_WORDS or state == STATE_START:
        if not pending:
            reset_session(whatsapp_id)
            return (
                f"Hola {client['nombre']}. No tienes facturas pendientes.\n"
                "Puedes escribir mis pagos para ver solicitudes."
            )
        update_session(
            whatsapp_id,
            state=STATE_SHOW_INVOICES,
            selected_invoice_id=None,
            selected_amount=None,
        )
        return f"Hola {client['nombre']}.\n\n{_format_invoice_list(pending)}"

    if state == STATE_SHOW_INVOICES:
        if not pending:
            reset_session(whatsapp_id)
            return "No tienes facturas pendientes."
        chosen = _resolve_invoice_choice(text, pending)
        if chosen is None:
            return (
                "No entendí la selección.\n\n" + _format_invoice_list(pending)
            )
        update_session(
            whatsapp_id,
            state=STATE_SELECT_INVOICE,
            selected_invoice_id=chosen["id"],
            selected_amount=None,
        )
        return (
            f"Seleccionaste {chosen['number']} "
            f"(saldo {chosen['saldo']:.2f}).\n"
            "¿Cuánto deseas pagar? Escribe un monto o la palabra total.\n"
            "(O escribe cancelar)"
        )

    if state == STATE_SELECT_INVOICE:
        invoice_id = session["selected_invoice_id"]
        invoice = get_invoice_by_id(invoice_id) if invoice_id else None
        if invoice is None or invoice["saldo"] <= 0:
            reset_session(whatsapp_id)
            return "La factura seleccionada ya no está disponible. Escribe hola para ver el menú."
        amount = _parse_amount(text, float(invoice["saldo"]))
        if amount is None:
            return (
                f"Monto inválido. El saldo de {invoice['number']} es "
                f"{invoice['saldo']:.2f}. Escribe un monto, total o cancelar."
            )
        update_session(
            whatsapp_id,
            state=STATE_CONFIRM_AMOUNT,
            selected_amount=amount,
        )
        return (
            f"Confirmación:\n"
            f"- Factura: {invoice['number']}\n"
            f"- Monto a pagar: {amount:.2f}\n\n"
            "Responde SI para confirmar o NO / cancelar para cancelar.\n"
            "(El QR de pago se habilitará en una fase siguiente.)"
        )

    if state == STATE_CONFIRM_AMOUNT:
        if normalized in {"si", "sí", "s", "ok", "confirmar"}:
            invoice_id = session["selected_invoice_id"]
            amount = session["selected_amount"]
            invoice = get_invoice_by_id(invoice_id) if invoice_id else None
            number = invoice["number"] if invoice else "?"
            payment_id = None
            if invoice is not None and amount is not None:
                try:
                    payment = create_payment(
                        cliente_id=client["id"],
                        factura_id=invoice["id"],
                        monto=float(amount),
                    )
                    payment_id = payment["id"]
                except ValueError:
                    payment_id = None
            reset_session(whatsapp_id)
            ref = f" (pago #{payment_id})" if payment_id else ""
            return (
                f"Solicitud registrada: factura {number} por {float(amount):.2f}{ref}.\n"
                "El pago queda PENDIENTE hasta conectar el proveedor. "
                "Escribe hola para ver tus facturas o mis pagos para consultarlas."
            )
        if normalized in {"no", "n"} | _CANCEL_WORDS:
            reset_session(whatsapp_id)
            return "Operación cancelada. Escribe hola para ver tus facturas."
        return "Responde SI para confirmar o NO para cancelar."

    # Estado desconocido → reinicio amable
    reset_session(whatsapp_id)
    return "Escribe hola para ver tus facturas pendientes."
