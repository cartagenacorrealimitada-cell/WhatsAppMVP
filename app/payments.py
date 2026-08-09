"""Gestión de registros de pago (creación / consulta). Confirmación segura → payment_service."""

from __future__ import annotations

import uuid

from app.db import (
    PAY_ANULADO,
    PAY_CONFIRMADO,
    PAY_PENDIENTE,
    PAY_RECHAZADO,
    get_connection,
    init_db,
    utc_now,
)
from app.invoices import get_invoice_by_id, validate_saldo
from app.payment_service import confirm_or_reject_payment


def _row_to_payment(row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "cliente_id": row["cliente_id"],
        "factura_id": row["factura_id"],
        "monto": row["monto"],
        "moneda": row["moneda"] if "moneda" in keys else "BOB",
        "referencia_interna": (
            row["referencia_interna"] if "referencia_interna" in keys else None
        ),
        "referencia_externa": row["referencia_externa"],
        "estado": row["estado"],
        "fecha_creacion": row["fecha_creacion"],
        "fecha_pago": row["fecha_pago"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_payment(
    *,
    cliente_id: int,
    factura_id: int,
    monto: float,
    referencia_externa: str | None = None,
    moneda: str = "BOB",
    estado: str = PAY_PENDIENTE,
) -> dict:
    """
    Crea un registro de pago PENDIENTE.
    No modifica el saldo hasta confirmación autenticada.
    """
    if monto <= 0:
        raise ValueError("monto debe ser mayor a 0")

    init_db()
    invoice = get_invoice_by_id(factura_id)
    if invoice is None:
        raise ValueError("factura no encontrada")
    if invoice["cliente_id"] != cliente_id:
        raise ValueError("factura no pertenece al cliente")
    validate_saldo(float(invoice["monto_original"]), float(invoice["saldo"]))
    if monto > float(invoice["saldo"]):
        raise ValueError("monto supera el saldo de la factura")

    now = utc_now()
    moneda_n = (moneda or "BOB").strip().upper() or "BOB"
    ref_int = f"QRDNT-{uuid.uuid4().hex[:16].upper()}"
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO payments
                (cliente_id, factura_id, monto, moneda, referencia_interna,
                 referencia_externa, estado, fecha_creacion, fecha_pago,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                cliente_id,
                factura_id,
                float(monto),
                moneda_n,
                ref_int,
                referencia_externa,
                estado,
                now,
                now,
                now,
            ),
        )
        conn.commit()
        payment_id = cur.lastrowid
    finally:
        conn.close()

    payment = get_payment_by_id(payment_id)
    assert payment is not None
    return payment


def get_payment_by_id(payment_id: int) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_payment(row) if row else None


def get_payments_by_cliente_id(
    cliente_id: int,
    *,
    limit: int = 10,
) -> list[dict]:
    """Últimos pagos del cliente (más recientes primero), con número de factura."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.*, i.number AS factura_number
            FROM payments p
            JOIN invoices i ON i.id = p.factura_id
            WHERE p.cliente_id = ?
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (cliente_id, max(1, int(limit))),
        ).fetchall()
    finally:
        conn.close()

    result: list[dict] = []
    for row in rows:
        data = _row_to_payment(row)
        data["factura_number"] = row["factura_number"]
        result.append(data)
    return result


def confirm_payment(
    payment_id: int,
    *,
    referencia_externa: str | None = None,
    monto: float | None = None,
    moneda: str | None = "BOB",
) -> dict:
    """
    API de dominio (uso interno/tests).
    Requiere monto y referencia_externa para confirmación real.
    """
    payment = get_payment_by_id(payment_id)
    if payment is None:
        raise ValueError("pago no encontrado")
    if monto is None:
        monto = float(payment["monto"])
    if not referencia_externa:
        referencia_externa = f"INT-{payment_id}-{uuid.uuid4().hex[:8]}"
    outcome = confirm_or_reject_payment(
        payment_id=payment_id,
        resultado=PAY_CONFIRMADO,
        referencia_externa=referencia_externa,
        monto=monto,
        moneda=moneda or payment.get("moneda") or "BOB",
        auth_ok=True,
        auth_method="internal",
    )
    if outcome.payment is None or outcome.status not in {"confirmed", "duplicate"}:
        raise ValueError(outcome.detail)
    return outcome.payment


def reject_payment(payment_id: int) -> dict:
    outcome = confirm_or_reject_payment(
        payment_id=payment_id,
        resultado=PAY_RECHAZADO,
        referencia_externa=None,
        monto=None,
        moneda=None,
        auth_ok=True,
        auth_method="internal",
    )
    if outcome.payment is None or outcome.status != "rejected":
        raise ValueError(outcome.detail)
    return outcome.payment


def annul_payment(payment_id: int) -> dict:
    init_db()
    payment = get_payment_by_id(payment_id)
    if payment is None:
        raise ValueError("pago no encontrado")

    now = utc_now()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE payments
            SET estado = ?, updated_at = ?
            WHERE id = ?
            """,
            (PAY_ANULADO, now, payment_id),
        )
        conn.commit()
    finally:
        conn.close()
    updated = get_payment_by_id(payment_id)
    assert updated is not None
    return updated
