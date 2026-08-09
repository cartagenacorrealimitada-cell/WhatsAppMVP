"""Recepción de peticiones del webhook de WhatsApp Cloud."""

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config import WHATSAPP_VERIFY_TOKEN
from app.conversation import handle_conversation
from app.db import STATE_SHOW_INVOICES
from app.invoice_service import get_invoice_from_message
from app.parser import parse_invoice_number
from app.sessions import get_session
from app.whatsapp import send_message

router = APIRouter()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Verificación del webhook por parte de Meta."""
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    """Recibe el mensaje, consulta factura o gestiona la conversación de saldos."""
    body = await request.json()

    try:
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return {"status": "ok"}

    # Si el usuario está eligiendo factura, F-#### alimenta la conversación
    session = get_session(sender)
    if (
        session is not None
        and session["state"] == STATE_SHOW_INVOICES
        and parse_invoice_number(text) is not None
    ):
        reply = handle_conversation(sender, text)
        send_message(sender, reply)
        return {"status": "ok"}

    # Conservar consulta directa por número de factura (F-####)
    if parse_invoice_number(text) is not None:
        invoice = get_invoice_from_message(text)
        if invoice is not None:
            reply = (
                f"Factura {invoice['number']}: {invoice['status']} "
                f"({invoice['customer']})"
            )
        else:
            reply = "Factura no encontrada"
        send_message(sender, reply)
        return {"status": "ok"}

    reply = handle_conversation(sender, text)
    send_message(sender, reply)
    return {"status": "ok"}
