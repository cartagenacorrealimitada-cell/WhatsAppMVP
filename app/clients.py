"""Gestión de clientes (identidad). WhatsApp es solo el canal vía whatsapp_id."""

from __future__ import annotations

from app.db import get_connection, init_db, utc_now


def _row_to_client(row) -> dict:
    return {
        "id": row["id"],
        "whatsapp_id": row["whatsapp_id"],
        "nombre": row["nombre"],
        "nit": row["nit"],
        "documento": row["documento"],
        "telefono": row["telefono"],
        "email": row["email"],
        "activo": bool(row["activo"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_client(
    *,
    whatsapp_id: str,
    nombre: str,
    nit: str | None = None,
    documento: str | None = None,
    telefono: str | None = None,
    email: str | None = None,
    activo: bool = True,
) -> dict:
    """Crea un cliente. nit y documento son opcionales."""
    init_db()
    now = utc_now()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO clients
                (whatsapp_id, nombre, nit, documento, telefono, email,
                 activo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                whatsapp_id,
                nombre,
                nit,
                documento,
                telefono or whatsapp_id,
                email,
                1 if activo else 0,
                now,
                now,
            ),
        )
        conn.commit()
        client_id = cur.lastrowid
    finally:
        conn.close()

    client = get_client_by_id(client_id)
    assert client is not None
    return client


def get_client_by_id(client_id: int) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_client(row) if row else None


def get_client_by_whatsapp(whatsapp_id: str, *, only_active: bool = True) -> dict | None:
    """Identifica al cliente por el canal WhatsApp (whatsapp_id)."""
    init_db()
    conn = get_connection()
    try:
        if only_active:
            row = conn.execute(
                """
                SELECT * FROM clients
                WHERE whatsapp_id = ? AND activo = 1
                """,
                (whatsapp_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM clients WHERE whatsapp_id = ?",
                (whatsapp_id,),
            ).fetchone()
    finally:
        conn.close()

    return _row_to_client(row) if row else None


def get_client_by_nit(nit: str, *, only_active: bool = True) -> dict | None:
    """Búsqueda por NIT (índice idx_clients_nit). No se usa en el chat por defecto."""
    if not nit or not str(nit).strip():
        return None
    init_db()
    conn = get_connection()
    try:
        if only_active:
            row = conn.execute(
                """
                SELECT * FROM clients
                WHERE nit = ? AND activo = 1
                """,
                (nit.strip(),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM clients WHERE nit = ?",
                (nit.strip(),),
            ).fetchone()
    finally:
        conn.close()
    return _row_to_client(row) if row else None


def update_client(
    client_id: int,
    *,
    nombre: str | None = None,
    nit: str | object = ...,
    documento: str | object = ...,
    telefono: str | None = None,
    email: str | object = ...,
    activo: bool | None = None,
) -> dict:
    """
    Actualiza identidad del cliente (uso interno/admin, no WhatsApp).
    Para nit/documento/email: pasa None para borrar, omite el arg para no cambiar.
    """
    init_db()
    current = get_client_by_id(client_id)
    if current is None:
        raise ValueError("cliente no encontrado")

    new_nombre = nombre if nombre is not None else current["nombre"]
    new_nit = current["nit"] if nit is ... else nit
    new_documento = current["documento"] if documento is ... else documento
    new_telefono = telefono if telefono is not None else current["telefono"]
    new_email = current["email"] if email is ... else email
    new_activo = current["activo"] if activo is None else activo
    now = utc_now()

    if isinstance(new_nit, str):
        new_nit = new_nit.strip() or None
    if isinstance(new_documento, str):
        new_documento = new_documento.strip() or None
    if isinstance(new_email, str):
        new_email = new_email.strip() or None

    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE clients
            SET nombre = ?, nit = ?, documento = ?, telefono = ?, email = ?,
                activo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_nombre,
                new_nit,
                new_documento,
                new_telefono,
                new_email,
                1 if new_activo else 0,
                now,
                client_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    updated = get_client_by_id(client_id)
    assert updated is not None
    return updated
