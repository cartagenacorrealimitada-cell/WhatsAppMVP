"""Autenticación pluggable para confirmación de pagos (no es la del banco)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Request

from app import config


@dataclass
class AuthResult:
    ok: bool
    method: str
    reason: str = ""


def verify_payments_request(request: Request) -> AuthResult:
    """
    Verifica autenticidad de la solicitud de confirmación.

    Hoy: shared secret interno (Bearer o header X-QRDNT-Payments-Token).
    El lunes: se podrá añadir un adaptador del proveedor (HMAC, etc.) sin
    mezclarlo con la lógica financiera.
    """
    expected = (config.PAYMENTS_CONFIRM_TOKEN or "").strip()
    if not expected:
        return AuthResult(ok=False, method="none", reason="token_not_configured")

    auth = request.headers.get("Authorization", "") or ""
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()

    header_token = (request.headers.get("X-QRDNT-Payments-Token") or "").strip()
    provided = bearer or header_token
    if not provided:
        return AuthResult(ok=False, method="missing", reason="missing_credentials")

    if hmac.compare_digest(provided, expected):
        method = "bearer" if bearer else "header"
        return AuthResult(ok=True, method=method)

    return AuthResult(ok=False, method="rejected", reason="invalid_credentials")
