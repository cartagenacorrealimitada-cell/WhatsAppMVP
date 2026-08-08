"""Recepción de peticiones del webhook de WhatsApp Cloud."""

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config import WHATSAPP_VERIFY_TOKEN
from app.invoice_service import get_invoice_from_message
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
    """Recibe el mensaje, consulta la factura y responde por WhatsApp."""
    body = await request.json()

    try:
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return {"status": "ok"}

    invoice = get_invoice_from_message(text)
    if invoice is not None:
        reply = (
            f"Factura {invoice['number']}: {invoice['status']} "
            f"({invoice['customer']})"
        )
    else:
        reply = "Factura no encontrada"

    ok = send_message(sender, reply)
    print(f"SEND ok={ok} to={sender} reply={reply!r}")
    return {"status": "ok"}
