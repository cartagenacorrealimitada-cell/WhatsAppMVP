"""HTTP: confirmación de pagos (auth → validación → motor financiero)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.clients import get_client_by_id
from app.payments_auth import verify_payments_request
from app.payment_service import confirm_or_reject_payment, record_auth_failure
from app.whatsapp import send_message

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentConfirmBody(BaseModel):
    payment_id: int = Field(..., gt=0)
    resultado: str
    referencia_externa: str | None = None
    monto: float | None = None
    moneda: str | None = "BOB"
    # No se aceptan cliente_id / invoice_id del cliente externo (fuente de verdad = BD)
    notificar_whatsapp: bool = True


def _notify_client(payment: dict, invoice: dict | None, *, confirmed: bool) -> bool:
    client = get_client_by_id(payment["cliente_id"])
    if client is None:
        return False
    number = invoice["number"] if invoice else "?"
    saldo = float(invoice["saldo"]) if invoice else 0.0
    monto = float(payment["monto"])
    if confirmed:
        text = (
            f"Pago confirmado: factura {number} por {monto:.2f}.\n"
            f"Saldo restante: {saldo:.2f}.\n"
            "Escribe hola para ver tus facturas."
        )
    else:
        text = (
            f"Pago rechazado: factura {number} por {monto:.2f}.\n"
            "Tu saldo no cambió. Escribe hola para intentar de nuevo."
        )
    return send_message(client["whatsapp_id"], text)


def _public_error(http_status: int, code: str) -> dict:
    return {"status": "error", "code": code, "http_status": http_status}


@router.post("/confirm")
async def confirm_payment_endpoint(
    body: PaymentConfirmBody,
    request: Request,
) -> dict:
    """
    Confirma o rechaza un pago PENDIENTE.
    Requiere autenticación (Bearer o X-QRDNT-Payments-Token).
    No modifica el webhook de Meta (/webhook).
    """
    auth = verify_payments_request(request)
    if not auth.ok:
        record_auth_failure(
            payment_id=body.payment_id,
            auth_method=auth.method,
            referencia_externa=body.referencia_externa,
        )
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=401,
            content={"status": "error", "code": "unauthorized"},
        )

    outcome = confirm_or_reject_payment(
        payment_id=body.payment_id,
        resultado=body.resultado,
        referencia_externa=body.referencia_externa,
        monto=body.monto,
        moneda=body.moneda,
        auth_ok=True,
        auth_method=auth.method,
    )

    if outcome.http_status >= 400:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=outcome.http_status,
            content={"status": "error", "code": outcome.detail},
        )

    notified = False
    if (
        body.notificar_whatsapp
        and outcome.payment is not None
        and outcome.status in {"confirmed", "rejected"}
        and not outcome.already_processed
    ):
        notified = _notify_client(
            outcome.payment,
            outcome.invoice,
            confirmed=outcome.status == "confirmed",
        )

    return {
        "status": "ok",
        "result": outcome.status,
        "already_processed": outcome.already_processed,
        "payment": outcome.payment,
        "invoice": outcome.invoice,
        "whatsapp_notificado": notified,
    }
