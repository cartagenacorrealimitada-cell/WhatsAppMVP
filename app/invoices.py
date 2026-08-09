"""Consulta y gestión de facturas en SQLite."""

from __future__ import annotations

from app.db import (
    INV_ANULADA,
    INV_PAGADA,
    INV_PAGADA_PARCIAL,
    INV_PENDIENTE,
    INV_VENCIDA,
    get_connection,
    init_db,
    utc_now,
)

_PENDING_STATES = (INV_PENDIENTE, INV_PAGADA_PARCIAL, INV_VENCIDA)


def validate_saldo(monto_original: float, saldo: float) -> None:
    """Impide saldo negativo o mayor al monto original."""
    if monto_original < 0:
        raise ValueError("monto_original no puede ser negativo")
    if saldo < 0:
        raise ValueError("saldo no puede ser negativo")
    if saldo > monto_original:
        raise ValueError("saldo no puede superar monto_original")


def derive_estado(
    monto_original: float,
    saldo: float,
    fecha_vencimiento: str,
    *,
    today: str | None = None,
    anulado: bool = False,
) -> str:
    """Calcula estado a partir del saldo (y vencimiento si aplica)."""
    if anulado:
        return INV_ANULADA
    validate_saldo(monto_original, saldo)
    if saldo <= 0:
        return INV_PAGADA
    if saldo < monto_original:
        # Parcial tiene prioridad sobre vencida para reflejar pagos a cuenta
        return INV_PAGADA_PARCIAL
    ref = today or utc_now()[:10]
    if fecha_vencimiento < ref:
        return INV_VENCIDA
    return INV_PENDIENTE


def _row_to_invoice(row) -> dict:
    """Dict canónico + aliases para compatibilidad del flujo WhatsApp."""
    data = {
        "id": row["id"],
        "number": row["number"],
        "cliente_id": row["cliente_id"],
        "descripcion": row["descripcion"],
        "monto_original": row["monto_original"],
        "saldo": row["saldo"],
        "fecha_emision": row["fecha_emision"],
        "fecha_vencimiento": row["fecha_vencimiento"],
        "estado": row["estado"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "customer": row["nombre"] if "nombre" in row.keys() else None,
        # aliases legacy
        "customer_id": row["cliente_id"],
        "amount": row["monto_original"],
        "balance": row["saldo"],
        "due_date": row["fecha_vencimiento"],
        "status": row["estado"],
    }
    return data


def create_invoice(
    *,
    number: str,
    cliente_id: int,
    monto_original: float,
    saldo: float | None = None,
    descripcion: str | None = None,
    fecha_emision: str | None = None,
    fecha_vencimiento: str,
    estado: str | None = None,
) -> dict:
    """Crea factura con saldo validado."""
    init_db()
    if saldo is None:
        saldo = monto_original
    validate_saldo(monto_original, saldo)
    now = utc_now()
    emision = fecha_emision or now[:10]
    final_estado = estado or derive_estado(monto_original, saldo, fecha_vencimiento)

    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO invoices
                (number, cliente_id, descripcion, monto_original, saldo,
                 fecha_emision, fecha_vencimiento, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                number,
                cliente_id,
                descripcion or f"Factura {number}",
                float(monto_original),
                float(saldo),
                emision,
                fecha_vencimiento,
                final_estado,
                now,
                now,
            ),
        )
        conn.commit()
        invoice_id = cur.lastrowid
    finally:
        conn.close()

    invoice = get_invoice_by_id(invoice_id)
    assert invoice is not None
    return invoice


def get_invoice(number: str) -> dict | None:
    """Devuelve la factura por número (API legacy), o None."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT i.*, c.nombre
            FROM invoices i
            JOIN clients c ON c.id = i.cliente_id
            WHERE i.number = ?
            """,
            (number,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_invoice(row) if row else None


def get_invoice_by_id(invoice_id: int) -> dict | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT i.*, c.nombre
            FROM invoices i
            JOIN clients c ON c.id = i.cliente_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_invoice(row) if row else None


def get_invoices_by_cliente_id(cliente_id: int) -> list[dict]:
    """Todas las facturas del cliente (cualquier estado)."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT i.*, c.nombre
            FROM invoices i
            JOIN clients c ON c.id = i.cliente_id
            WHERE i.cliente_id = ?
            ORDER BY i.fecha_vencimiento ASC, i.number ASC
            """,
            (cliente_id,),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_invoice(row) for row in rows]


def get_invoices_by_whatsapp(whatsapp_id: str) -> list[dict]:
    """Todas las facturas del cliente identificado por WhatsApp."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT i.*, c.nombre
            FROM invoices i
            JOIN clients c ON c.id = i.cliente_id
            WHERE c.whatsapp_id = ?
            ORDER BY i.fecha_vencimiento ASC, i.number ASC
            """,
            (whatsapp_id,),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_invoice(row) for row in rows]


def get_pending_invoices(cliente_id: int) -> list[dict]:
    """Facturas con saldo > 0 (pendiente, parcial o vencida). Excluye anuladas/pagadas."""
    init_db()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(_PENDING_STATES))
        rows = conn.execute(
            f"""
            SELECT i.*, c.nombre
            FROM invoices i
            JOIN clients c ON c.id = i.cliente_id
            WHERE i.cliente_id = ?
              AND i.saldo > 0
              AND i.estado IN ({placeholders})
            ORDER BY i.fecha_vencimiento ASC, i.number ASC
            """,
            (cliente_id, *_PENDING_STATES),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_invoice(row) for row in rows]


def apply_saldo_reduction(invoice_id: int, monto: float) -> dict:
    """
    Reduce el saldo de una factura (para pagos confirmados futuros).
    No permite saldo negativo.
    """
    if monto <= 0:
        raise ValueError("monto debe ser mayor a 0")

    init_db()
    invoice = get_invoice_by_id(invoice_id)
    if invoice is None:
        raise ValueError("factura no encontrada")
    if invoice["estado"] == INV_ANULADA:
        raise ValueError("factura anulada")

    nuevo_saldo = float(invoice["saldo"]) - float(monto)
    validate_saldo(float(invoice["monto_original"]), nuevo_saldo)
    nuevo_estado = derive_estado(
        float(invoice["monto_original"]),
        nuevo_saldo,
        invoice["fecha_vencimiento"],
    )
    now = utc_now()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE invoices
            SET saldo = ?, estado = ?, updated_at = ?
            WHERE id = ?
            """,
            (nuevo_saldo, nuevo_estado, now, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()

    updated = get_invoice_by_id(invoice_id)
    assert updated is not None
    return updated
