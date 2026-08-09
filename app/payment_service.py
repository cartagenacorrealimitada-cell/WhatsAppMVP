"""
Motor de confirmación de pagos (lógica financiera).

Separado de la autenticación HTTP. Fuente de verdad: SQLite propia.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from app.db import (
    INV_ANULADA,
    PAY_CONFIRMADO,
    PAY_PENDIENTE,
    PAY_RECHAZADO,
    get_connection,
    init_db,
    utc_now,
)
from app.invoices import derive_estado, validate_saldo


class PaymentValidationError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass
class ConfirmOutcome:
    status: str  # confirmed | rejected | duplicate | error
    http_status: int
    payment: dict | None
    invoice: dict | None
    detail: str
    already_processed: bool = False


def _row_payment(row: sqlite3.Row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "cliente_id": row["cliente_id"],
        "factura_id": row["factura_id"],
        "monto": row["monto"],
        "moneda": row["moneda"] if "moneda" in keys else "BOB",
        "referencia_interna": row["referencia_interna"] if "referencia_interna" in keys else None,
        "referencia_externa": row["referencia_externa"],
        "estado": row["estado"],
        "fecha_creacion": row["fecha_creacion"],
        "fecha_pago": row["fecha_pago"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_invoice(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "number": row["number"],
        "cliente_id": row["cliente_id"],
        "saldo": row["saldo"],
        "monto_original": row["monto_original"],
        "estado": row["estado"],
        "fecha_vencimiento": row["fecha_vencimiento"],
    }


def _log_event(
    conn: sqlite3.Connection,
    *,
    payment_id: int | None,
    event_type: str,
    auth_ok: bool | None = None,
    auth_method: str | None = None,
    validation_ok: bool | None = None,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
    monto: float | None = None,
    moneda: str | None = None,
    referencia_interna: str | None = None,
    referencia_externa: str | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO payment_events (
            payment_id, event_type, auth_ok, auth_method, validation_ok,
            estado_anterior, estado_nuevo, monto, moneda,
            referencia_interna, referencia_externa, detail, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payment_id,
            event_type,
            None if auth_ok is None else (1 if auth_ok else 0),
            auth_method,
            None if validation_ok is None else (1 if validation_ok else 0),
            estado_anterior,
            estado_nuevo,
            monto,
            moneda,
            referencia_interna,
            referencia_externa,
            detail,
            utc_now(),
        ),
    )


def _amounts_equal(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.005


def confirm_or_reject_payment(
    *,
    payment_id: int,
    resultado: str,
    referencia_externa: str | None,
    monto: float | None,
    moneda: str | None,
    auth_ok: bool,
    auth_method: str,
) -> ConfirmOutcome:
    """
    Confirma o rechaza un pago con validación financiera + idempotencia + transacción.
    No realiza autenticación HTTP (debe hacerse antes).
    """
    init_db()
    resultado = resultado.strip().upper()
    moneda_in = (moneda or "BOB").strip().upper()
    ref_ext = (referencia_externa or "").strip() or None

    if not auth_ok:
        conn = get_connection()
        try:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="auth_failed",
                auth_ok=False,
                auth_method=auth_method,
                validation_ok=False,
                referencia_externa=ref_ext,
                detail="authentication_failed",
            )
            conn.commit()
        finally:
            conn.close()
        return ConfirmOutcome(
            status="error",
            http_status=401,
            payment=None,
            invoice=None,
            detail="unauthorized",
        )

    if resultado not in {PAY_CONFIRMADO, PAY_RECHAZADO}:
        return ConfirmOutcome(
            status="error",
            http_status=400,
            payment=None,
            invoice=None,
            detail="invalid_resultado",
        )

    conn = get_connection()
    try:
        # Bloqueo de escritura para concurrencia en SQLite
        conn.execute("BEGIN IMMEDIATE")

        # Idempotencia por referencia externa ya procesada
        if ref_ext:
            processed = conn.execute(
                """
                SELECT payment_id FROM payment_processed_refs
                WHERE referencia_externa = ?
                """,
                (ref_ext,),
            ).fetchone()
            if processed is not None:
                pay_row = conn.execute(
                    "SELECT * FROM payments WHERE id = ?",
                    (processed["payment_id"],),
                ).fetchone()
                inv_row = None
                if pay_row is not None:
                    inv_row = conn.execute(
                        "SELECT * FROM invoices WHERE id = ?",
                        (pay_row["factura_id"],),
                    ).fetchone()
                _log_event(
                    conn,
                    payment_id=processed["payment_id"],
                    event_type="duplicate",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=True,
                    estado_anterior=pay_row["estado"] if pay_row else None,
                    estado_nuevo=pay_row["estado"] if pay_row else None,
                    monto=pay_row["monto"] if pay_row else None,
                    moneda=pay_row["moneda"] if pay_row and "moneda" in pay_row.keys() else None,
                    referencia_interna=pay_row["referencia_interna"] if pay_row else None,
                    referencia_externa=ref_ext,
                    detail="duplicate_referencia_externa",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="duplicate",
                    http_status=200,
                    payment=_row_payment(pay_row) if pay_row else None,
                    invoice=_row_invoice(inv_row) if inv_row else None,
                    detail="already_processed",
                    already_processed=True,
                )

        pay_row = conn.execute(
            "SELECT * FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        if pay_row is None:
            _log_event(
                conn,
                payment_id=None,
                event_type="validation_failed",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=False,
                referencia_externa=ref_ext,
                detail="payment_not_found",
            )
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=404,
                payment=None,
                invoice=None,
                detail="payment_not_found",
            )

        payment = _row_payment(pay_row)
        estado_anterior = payment["estado"]

        inv_row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?",
            (payment["factura_id"],),
        ).fetchone()
        if inv_row is None:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="validation_failed",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=False,
                estado_anterior=estado_anterior,
                referencia_interna=payment["referencia_interna"],
                referencia_externa=ref_ext,
                detail="invoice_not_found",
            )
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=400,
                payment=payment,
                invoice=None,
                detail="invoice_not_found",
            )
        invoice = _row_invoice(inv_row)

        client_row = conn.execute(
            "SELECT id FROM clients WHERE id = ?",
            (payment["cliente_id"],),
        ).fetchone()
        if client_row is None:
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=400,
                payment=payment,
                invoice=invoice,
                detail="client_not_found",
            )

        if invoice["cliente_id"] != payment["cliente_id"]:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="validation_failed",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=False,
                estado_anterior=estado_anterior,
                detail="invoice_client_mismatch",
            )
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=400,
                payment=payment,
                invoice=invoice,
                detail="invoice_client_mismatch",
            )

        if invoice["estado"] == INV_ANULADA:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="validation_failed",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=False,
                estado_anterior=estado_anterior,
                detail="invoice_annulled",
            )
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=400,
                payment=payment,
                invoice=invoice,
                detail="invoice_annulled",
            )

        # Ya confirmado / rechazado (sin nueva ref o misma lógica)
        if payment["estado"] == PAY_CONFIRMADO and resultado == PAY_CONFIRMADO:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="duplicate",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=True,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_anterior,
                monto=payment["monto"],
                moneda=payment["moneda"],
                referencia_interna=payment["referencia_interna"],
                referencia_externa=ref_ext or payment["referencia_externa"],
                detail="payment_already_confirmed",
            )
            conn.commit()
            return ConfirmOutcome(
                status="duplicate",
                http_status=200,
                payment=payment,
                invoice=invoice,
                detail="already_processed",
                already_processed=True,
            )

        if payment["estado"] != PAY_PENDIENTE:
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="validation_failed",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=False,
                estado_anterior=estado_anterior,
                detail="invalid_payment_state",
            )
            conn.commit()
            return ConfirmOutcome(
                status="error",
                http_status=409,
                payment=payment,
                invoice=invoice,
                detail="invalid_payment_state",
            )

        # Validaciones de payload vs BD (fuente de verdad = BD)
        if resultado == PAY_CONFIRMADO:
            if not ref_ext:
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    estado_anterior=estado_anterior,
                    detail="missing_referencia_externa",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="missing_referencia_externa",
                )
            if payment["referencia_externa"] and payment["referencia_externa"] != ref_ext:
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    estado_anterior=estado_anterior,
                    referencia_externa=ref_ext,
                    detail="referencia_externa_mismatch",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="referencia_externa_mismatch",
                )
            if monto is None:
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    detail="missing_monto",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="missing_monto",
                )
            if not _amounts_equal(monto, payment["monto"]):
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    monto=float(monto),
                    detail="monto_mismatch",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="monto_mismatch",
                )
            if moneda_in != str(payment["moneda"]).upper():
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    moneda=moneda_in,
                    detail="moneda_mismatch",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="moneda_mismatch",
                )
            if float(payment["monto"]) > float(invoice["saldo"]):
                _log_event(
                    conn,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    detail="amount_exceeds_balance",
                )
                conn.commit()
                return ConfirmOutcome(
                    status="error",
                    http_status=400,
                    payment=payment,
                    invoice=invoice,
                    detail="amount_exceeds_balance",
                )

        now = utc_now()

        if resultado == PAY_RECHAZADO:
            cur = conn.execute(
                """
                UPDATE payments
                SET estado = ?, updated_at = ?
                WHERE id = ? AND estado = ?
                """,
                (PAY_RECHAZADO, now, payment_id, PAY_PENDIENTE),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return ConfirmOutcome(
                    status="error",
                    http_status=409,
                    payment=payment,
                    invoice=invoice,
                    detail="invalid_payment_state",
                )
            _log_event(
                conn,
                payment_id=payment_id,
                event_type="rejected",
                auth_ok=True,
                auth_method=auth_method,
                validation_ok=True,
                estado_anterior=estado_anterior,
                estado_nuevo=PAY_RECHAZADO,
                monto=payment["monto"],
                moneda=payment["moneda"],
                referencia_interna=payment["referencia_interna"],
                referencia_externa=ref_ext,
                detail="rejected",
            )
            conn.commit()
            pay2 = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
            return ConfirmOutcome(
                status="rejected",
                http_status=200,
                payment=_row_payment(pay2) if pay2 else payment,
                invoice=invoice,
                detail="rejected",
            )

        # CONFIRMADO — atómico
        try:
            conn.execute(
                """
                INSERT INTO payment_processed_refs (referencia_externa, payment_id, created_at)
                VALUES (?, ?, ?)
                """,
                (ref_ext, payment_id, now),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            conn2 = get_connection()
            try:
                processed = conn2.execute(
                    """
                    SELECT payment_id FROM payment_processed_refs
                    WHERE referencia_externa = ?
                    """,
                    (ref_ext,),
                ).fetchone()
                if processed is None:
                    return ConfirmOutcome(
                        status="error",
                        http_status=409,
                        payment=payment,
                        invoice=invoice,
                        detail="conflict",
                    )
                pay_row = conn2.execute(
                    "SELECT * FROM payments WHERE id = ?",
                    (processed["payment_id"],),
                ).fetchone()
                inv_row = None
                if pay_row is not None:
                    inv_row = conn2.execute(
                        "SELECT * FROM invoices WHERE id = ?",
                        (pay_row["factura_id"],),
                    ).fetchone()
                return ConfirmOutcome(
                    status="duplicate",
                    http_status=200,
                    payment=_row_payment(pay_row) if pay_row else None,
                    invoice=_row_invoice(inv_row) if inv_row else None,
                    detail="already_processed",
                    already_processed=True,
                )
            finally:
                conn2.close()

        nuevo_saldo = float(invoice["saldo"]) - float(payment["monto"])
        try:
            validate_saldo(float(invoice["monto_original"]), nuevo_saldo)
        except ValueError:
            conn.rollback()
            _conn2 = get_connection()
            try:
                _log_event(
                    _conn2,
                    payment_id=payment_id,
                    event_type="validation_failed",
                    auth_ok=True,
                    auth_method=auth_method,
                    validation_ok=False,
                    detail="saldo_invalid",
                )
                _conn2.commit()
            finally:
                _conn2.close()
            return ConfirmOutcome(
                status="error",
                http_status=400,
                payment=payment,
                invoice=invoice,
                detail="saldo_invalid",
            )

        nuevo_estado_inv = derive_estado(
            float(invoice["monto_original"]),
            nuevo_saldo,
            invoice["fecha_vencimiento"],
        )
        conn.execute(
            """
            UPDATE invoices
            SET saldo = ?, estado = ?, updated_at = ?
            WHERE id = ?
            """,
            (nuevo_saldo, nuevo_estado_inv, now, invoice["id"]),
        )
        cur = conn.execute(
            """
            UPDATE payments
            SET estado = ?,
                fecha_pago = ?,
                referencia_externa = ?,
                updated_at = ?
            WHERE id = ? AND estado = ?
            """,
            (PAY_CONFIRMADO, now, ref_ext, now, payment_id, PAY_PENDIENTE),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return ConfirmOutcome(
                status="error",
                http_status=409,
                payment=payment,
                invoice=invoice,
                detail="invalid_payment_state",
            )

        _log_event(
            conn,
            payment_id=payment_id,
            event_type="confirmed",
            auth_ok=True,
            auth_method=auth_method,
            validation_ok=True,
            estado_anterior=estado_anterior,
            estado_nuevo=PAY_CONFIRMADO,
            monto=payment["monto"],
            moneda=payment["moneda"],
            referencia_interna=payment["referencia_interna"],
            referencia_externa=ref_ext,
            detail="confirmed",
        )
        conn.commit()

        pay2 = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        inv2 = conn.execute(
            "SELECT * FROM invoices WHERE id = ?",
            (invoice["id"],),
        ).fetchone()
        return ConfirmOutcome(
            status="confirmed",
            http_status=200,
            payment=_row_payment(pay2) if pay2 else payment,
            invoice=_row_invoice(inv2) if inv2 else invoice,
            detail="confirmed",
        )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def record_auth_failure(
    *,
    payment_id: int | None,
    auth_method: str,
    referencia_externa: str | None = None,
) -> None:
    init_db()
    conn = get_connection()
    try:
        _log_event(
            conn,
            payment_id=payment_id,
            event_type="auth_failed",
            auth_ok=False,
            auth_method=auth_method,
            validation_ok=False,
            referencia_externa=referencia_externa,
            detail="authentication_failed",
        )
        conn.commit()
    finally:
        conn.close()
