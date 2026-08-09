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


def _format_invoice_list(invoices: list[dict]) -> str:
    lines = ["Tus facturas pendientes:", ""]
    for idx, inv in enumerate(invoices, start=1):
        lines.append(
            f"{idx}) {inv['number']} — saldo {inv['saldo']:.2f} "
            f"(vence {inv['fecha_vencimiento']}, {inv['estado']})"
        )
    lines.append("")
    lines.append("Responde con el número de la lista (ej. 1) o el código (ej. F-1001).")
    lines.append("También: mis pagos | cancelar | hola")
    return "\n".join(lines)


def _format_payments_list(payments: list[dict]) -> str:
    if not payments:
        return (
            "No tienes solicitudes de pago registradas.\n"
            "Escribe hola para ver tus facturas."
        )
    lines = ["Tus últimos pagos:", ""]
    for pay in payments:
        number = pay.get("factura_number") or f"factura#{pay['factura_id']}"
        lines.append(
            f"#{pay['id']} — {number}: {float(pay['monto']):.2f} "
            f"({pay['estado']})"
        )
    lines.append("")
    lines.append("Escribe hola para ver facturas, o cancelar para salir.")
    return "\n".join(lines)


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
