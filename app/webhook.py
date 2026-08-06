"""Recepción de peticiones del webhook de WhatsApp Cloud."""

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config import WHATSAPP_VERIFY_TOKEN

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
    """Recibe notificaciones de WhatsApp. Solo confirma recepción."""
    await request.body()
    return {"status": "ok"}
