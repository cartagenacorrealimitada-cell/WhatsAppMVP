"""Sesiones de conversación por WhatsApp."""

from __future__ import annotations

from app.db import STATE_START, get_connection, init_db, utc_now


def get_session(whatsapp_id: str) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT whatsapp_id, state, selected_invoice_id, selected_amount, updated_at
            FROM sessions
            WHERE whatsapp_id = ?
            """,
            (whatsapp_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return {
        "whatsapp_id": row["whatsapp_id"],
        "state": row["state"],
        "selected_invoice_id": row["selected_invoice_id"],
        "selected_amount": row["selected_amount"],
        "updated_at": row["updated_at"],
    }


def get_or_create_session(whatsapp_id: str) -> dict:
    session = get_session(whatsapp_id)
    if session is not None:
        return session

    init_db()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO sessions (whatsapp_id, state, selected_invoice_id, selected_amount, updated_at)
            VALUES (?, ?, NULL, NULL, ?)
            """,
            (whatsapp_id, STATE_START, utc_now()),
        )
        conn.commit()
    finally:
        conn.close()

    return get_session(whatsapp_id)  # type: ignore[return-value]


def update_session(
    whatsapp_id: str,
    *,
    state: str | None = None,
    selected_invoice_id: int | None | object = ...,
    selected_amount: float | None | object = ...,
) -> None:
    """Actualiza campos de sesión. Usa ... para 'no cambiar' invoice/amount."""
    init_db()
    current = get_or_create_session(whatsapp_id)
    new_state = state if state is not None else current["state"]
    new_invoice = (
        current["selected_invoice_id"]
        if selected_invoice_id is ...
        else selected_invoice_id
    )
    new_amount = (
        current["selected_amount"]
        if selected_amount is ...
        else selected_amount
    )

    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE sessions
            SET state = ?, selected_invoice_id = ?, selected_amount = ?, updated_at = ?
            WHERE whatsapp_id = ?
            """,
            (new_state, new_invoice, new_amount, utc_now(), whatsapp_id),
        )
        conn.commit()
    finally:
        conn.close()


def reset_session(whatsapp_id: str) -> None:
    update_session(
        whatsapp_id,
        state=STATE_START,
        selected_invoice_id=None,
        selected_amount=None,
    )
