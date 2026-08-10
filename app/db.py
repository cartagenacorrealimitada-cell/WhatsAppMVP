"""Acceso compartido a SQLite, constantes y migración del esquema."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import DATABASE_PATH

_DB_PATH = Path(__file__).resolve().parent.parent / DATABASE_PATH

# Estados de conversación WhatsApp
STATE_START = "START"
STATE_SHOW_INVOICES = "SHOW_INVOICES"
STATE_SELECT_INVOICE = "SELECT_INVOICE"
STATE_CONFIRM_AMOUNT = "CONFIRM_AMOUNT"

# Estados de factura
INV_PENDIENTE = "PENDIENTE"
INV_PAGADA_PARCIAL = "PAGADA_PARCIAL"
INV_PAGADA = "PAGADA"
INV_VENCIDA = "VENCIDA"
INV_ANULADA = "ANULADA"

# Estados de pago (tabla preparada; sin proveedor externo)
PAY_PENDIENTE = "PENDIENTE"
PAY_CONFIRMADO = "CONFIRMADO"
PAY_RECHAZADO = "RECHAZADO"
PAY_ANULADO = "ANULADO"

_STATUS_MAP = {
    "pendiente": INV_PENDIENTE,
    "pagada": INV_PAGADA,
    "vencida": INV_VENCIDA,
    "anulada": INV_ANULADA,
    "pagada_parcial": INV_PAGADA_PARCIAL,
    "parcial": INV_PAGADA_PARCIAL,
    INV_PENDIENTE: INV_PENDIENTE,
    INV_PAGADA: INV_PAGADA,
    INV_VENCIDA: INV_VENCIDA,
    INV_ANULADA: INV_ANULADA,
    INV_PAGADA_PARCIAL: INV_PAGADA_PARCIAL,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        return set()
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _needs_clients_migration(conn: sqlite3.Connection) -> bool:
    cols = _table_columns(conn, "clients")
    if not cols:
        return False
    required = {"nit", "documento", "telefono", "email", "created_at", "updated_at"}
    return not required.issubset(cols)


def _needs_invoices_migration(conn: sqlite3.Connection) -> bool:
    cols = _table_columns(conn, "invoices")
    if not cols:
        return False
    required = {
        "cliente_id",
        "descripcion",
        "monto_original",
        "saldo",
        "fecha_emision",
        "fecha_vencimiento",
        "estado",
        "created_at",
        "updated_at",
    }
    return not required.issubset(cols)


def _normalize_invoice_status(raw: str | None, saldo: float, monto: float) -> str:
    if raw:
        mapped = _STATUS_MAP.get(str(raw).strip(), None)
        if mapped:
            return mapped
    if saldo <= 0:
        return INV_PAGADA
    if saldo < monto:
        return INV_PAGADA_PARCIAL
    return INV_PENDIENTE


def _migrate_clients(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "clients")
    if not cols:
        return
    rows = conn.execute("SELECT * FROM clients").fetchall()
    now = utc_now()
    conn.execute("ALTER TABLE clients RENAME TO clients_legacy_mig")
    conn.execute(
        """
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whatsapp_id TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            nit TEXT,
            documento TEXT,
            telefono TEXT,
            email TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    for row in rows:
        data = dict(row)
        conn.execute(
            """
            INSERT INTO clients
                (id, whatsapp_id, nombre, nit, documento, telefono, email,
                 activo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                data["whatsapp_id"],
                data["nombre"],
                data.get("nit"),
                data.get("documento"),
                data.get("telefono") or data["whatsapp_id"],
                data.get("email"),
                int(data.get("activo", 1)),
                data.get("created_at") or now,
                data.get("updated_at") or now,
            ),
        )
    conn.execute("DROP TABLE clients_legacy_mig")
    # SQLite reescribe FKs de invoices/payments hacia clients_legacy_mig al renombrar.
    _repair_client_foreign_keys(conn)


def _table_sql(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row[0] if row else None


def _needs_client_fk_repair(conn: sqlite3.Connection) -> bool:
    for table in ("invoices", "payments"):
        sql = _table_sql(conn, table) or ""
        if "clients_legacy_mig" in sql:
            return True
        fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        for fk in fks:
            # fk[2] = referenced table
            if fk[2] not in {"clients", "invoices"} and "cliente" in (fk[3] or ""):
                return True
            if fk[2] == "clients_legacy_mig":
                return True
    return False


def _rebuild_table_with_sql(
    conn: sqlite3.Connection,
    table: str,
    create_sql: str,
) -> None:
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    conn.execute(f"DROP TABLE {table}")
    conn.execute(create_sql)
    if not rows:
        return
    placeholders = ",".join("?" * len(cols))
    col_list = ",".join(cols)
    conn.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        [tuple(row[c] for c in cols) for row in rows],
    )


def _repair_client_foreign_keys(conn: sqlite3.Connection) -> None:
    """Recrea invoices/payments si sus FK apuntan a clients_legacy_mig."""
    if not _needs_client_fk_repair(conn):
        return

    session_rows = []
    if _table_columns(conn, "sessions"):
        session_rows = [dict(r) for r in conn.execute("SELECT * FROM sessions").fetchall()]
        conn.execute("DROP TABLE IF EXISTS sessions")

    payment_rows = []
    if _table_columns(conn, "payments"):
        payment_rows = [dict(r) for r in conn.execute("SELECT * FROM payments").fetchall()]
        conn.execute("DROP TABLE IF EXISTS payments")

    if _table_columns(conn, "invoices"):
        _rebuild_table_with_sql(
            conn,
            "invoices",
            """
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT NOT NULL UNIQUE,
                cliente_id INTEGER NOT NULL,
                descripcion TEXT,
                monto_original REAL NOT NULL,
                saldo REAL NOT NULL,
                fecha_emision TEXT NOT NULL,
                fecha_vencimiento TEXT NOT NULL,
                estado TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (saldo >= 0),
                CHECK (saldo <= monto_original),
                FOREIGN KEY (cliente_id) REFERENCES clients(id)
            )
            """,
        )

    conn.execute(
        """
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            factura_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            referencia_externa TEXT,
            estado TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            fecha_pago TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (monto > 0),
            FOREIGN KEY (cliente_id) REFERENCES clients(id),
            FOREIGN KEY (factura_id) REFERENCES invoices(id)
        )
        """
    )
    if payment_rows:
        cols = list(payment_rows[0].keys())
        placeholders = ",".join("?" * len(cols))
        col_list = ",".join(cols)
        conn.executemany(
            f"INSERT INTO payments ({col_list}) VALUES ({placeholders})",
            [tuple(row[c] for c in cols) for row in payment_rows],
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            whatsapp_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            selected_invoice_id INTEGER,
            selected_amount REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (selected_invoice_id) REFERENCES invoices(id)
        )
        """
    )
    for s in session_rows:
        conn.execute(
            """
            INSERT INTO sessions
                (whatsapp_id, state, selected_invoice_id, selected_amount, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                s["whatsapp_id"],
                s["state"],
                s.get("selected_invoice_id"),
                s.get("selected_amount"),
                s.get("updated_at") or utc_now(),
            ),
        )



def _migrate_invoices(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "invoices")
    if not cols:
        return

    # Liberar FK de sessions hacia invoices
    sessions_cols = _table_columns(conn, "sessions")
    session_rows = []
    if sessions_cols:
        session_rows = [dict(r) for r in conn.execute("SELECT * FROM sessions").fetchall()]
        conn.execute("DROP TABLE IF EXISTS sessions")

    rows = [dict(r) for r in conn.execute("SELECT * FROM invoices").fetchall()]
    conn.execute("DROP TABLE invoices")
    conn.execute(
        """
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            cliente_id INTEGER NOT NULL,
            descripcion TEXT,
            monto_original REAL NOT NULL,
            saldo REAL NOT NULL,
            fecha_emision TEXT NOT NULL,
            fecha_vencimiento TEXT NOT NULL,
            estado TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (saldo >= 0),
            CHECK (saldo <= monto_original),
            FOREIGN KEY (cliente_id) REFERENCES clients(id)
        )
        """
    )

    now = utc_now()
    for data in rows:
        if "cliente_id" in data:
            cliente_id = data["cliente_id"]
            monto = float(data.get("monto_original", data.get("amount", 0)))
            saldo = float(data.get("saldo", data.get("balance", monto)))
            fecha_venc = data.get("fecha_vencimiento") or data.get("due_date") or now[:10]
            fecha_emi = data.get("fecha_emision") or fecha_venc
            estado_raw = data.get("estado") or data.get("status")
            descripcion = data.get("descripcion")
        else:
            cliente_id = data["customer_id"]
            monto = float(data["amount"])
            saldo = float(data["balance"])
            fecha_venc = data["due_date"]
            fecha_emi = data["due_date"]
            estado_raw = data["status"]
            descripcion = f"Factura {data['number']}"

        if saldo < 0:
            saldo = 0.0
        if saldo > monto:
            saldo = monto

        estado = _normalize_invoice_status(estado_raw, saldo, monto)
        conn.execute(
            """
            INSERT INTO invoices
                (id, number, cliente_id, descripcion, monto_original, saldo,
                 fecha_emision, fecha_vencimiento, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                data["number"],
                cliente_id,
                descripcion,
                monto,
                saldo,
                fecha_emi,
                fecha_venc,
                estado,
                data.get("created_at") or now,
                data.get("updated_at") or now,
            ),
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            whatsapp_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            selected_invoice_id INTEGER,
            selected_amount REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (selected_invoice_id) REFERENCES invoices(id)
        )
        """
    )
    for s in session_rows:
        conn.execute(
            """
            INSERT INTO sessions
                (whatsapp_id, state, selected_invoice_id, selected_amount, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                s["whatsapp_id"],
                s["state"],
                s.get("selected_invoice_id"),
                s.get("selected_amount"),
                s.get("updated_at") or now,
            ),
        )


def _ensure_payments(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            factura_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            moneda TEXT NOT NULL DEFAULT 'BOB',
            referencia_interna TEXT,
            referencia_externa TEXT,
            estado TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            fecha_pago TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (monto > 0),
            FOREIGN KEY (cliente_id) REFERENCES clients(id),
            FOREIGN KEY (factura_id) REFERENCES invoices(id)
        )
        """
    )
    _ensure_payment_security_schema(conn)


def _ensure_payment_security_schema(conn: sqlite3.Connection) -> None:
    """Columnas/índices/auditoría para confirmación segura e idempotente."""
    cols = _table_columns(conn, "payments")
    if not cols:
        return
    if "moneda" not in cols:
        conn.execute(
            "ALTER TABLE payments ADD COLUMN moneda TEXT NOT NULL DEFAULT 'BOB'"
        )
    if "referencia_interna" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN referencia_interna TEXT")

    # Backfill referencia_interna
    missing = conn.execute(
        """
        SELECT id FROM payments
        WHERE referencia_interna IS NULL OR referencia_interna = ''
        """
    ).fetchall()
    for row in missing:
        conn.execute(
            "UPDATE payments SET referencia_interna = ? WHERE id = ?",
            (f"QRDNT-PAY-{row[0]}", row[0]),
        )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_referencia_interna
        ON payments (referencia_interna)
        WHERE referencia_interna IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_referencia_externa
        ON payments (referencia_externa)
        WHERE referencia_externa IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id INTEGER,
            event_type TEXT NOT NULL,
            auth_ok INTEGER,
            auth_method TEXT,
            validation_ok INTEGER,
            estado_anterior TEXT,
            estado_nuevo TEXT,
            monto REAL,
            moneda TEXT,
            referencia_interna TEXT,
            referencia_externa TEXT,
            detail TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_processed_refs (
            referencia_externa TEXT PRIMARY KEY,
            payment_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
        """
    )


def _ensure_clients_indexes(conn: sqlite3.Connection) -> None:
    """whatsapp_id ya es UNIQUE; índice en NIT para búsquedas (NIT puede ser NULL)."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_clients_nit ON clients (nit)"
    )


def _ensure_base_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whatsapp_id TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            nit TEXT,
            documento TEXT,
            telefono TEXT,
            email TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    _ensure_clients_indexes(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            cliente_id INTEGER NOT NULL,
            descripcion TEXT,
            monto_original REAL NOT NULL,
            saldo REAL NOT NULL,
            fecha_emision TEXT NOT NULL,
            fecha_vencimiento TEXT NOT NULL,
            estado TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (saldo >= 0),
            CHECK (saldo <= monto_original),
            FOREIGN KEY (cliente_id) REFERENCES clients(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            whatsapp_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            selected_invoice_id INTEGER,
            selected_amount REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (selected_invoice_id) REFERENCES invoices(id)
        )
        """
    )
    _ensure_payments(conn)


def _seed_if_needed(conn: sqlite3.Connection) -> None:
    """Completa datos de prueba sin borrar filas existentes."""
    now = utc_now()
    client_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    if client_count == 0:
        conn.executemany(
            """
            INSERT INTO clients
                (whatsapp_id, nombre, nit, documento, telefono, email,
                 activo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            [
                # nit opcional: Luis queda sin NIT a propósito
                ("59176710767", "Ana López", "1020304019", "CI-1001", "59176710767", "ana@example.com", now, now),
                ("59170000002", "Carlos Ruiz", "1020304027", "CI-1002", "59170000002", "carlos@example.com", now, now),
                ("59170000003", "María Pérez", "1020304035", "CI-1003", "59170000003", "maria@example.com", now, now),
                ("59170000004", "Luis Gómez", None, "CI-1004", "59170000004", "luis@example.com", now, now),
            ],
        )

    # No rellenar nit/documento/email con COALESCE: init_db() corre en cada
    # lectura/update y restauraría valores demo tras un clear intencional (NULL).

    # Asegurar Luis si no existe (sin NIT: no todos los clientes lo tienen)
    luis = conn.execute(
        "SELECT id FROM clients WHERE whatsapp_id = ?", ("59170000004",)
    ).fetchone()
    if luis is None:
        conn.execute(
            """
            INSERT INTO clients
                (whatsapp_id, nombre, nit, documento, telefono, email,
                 activo, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?, ?, 1, ?, ?)
            """,
            ("59170000004", "Luis Gómez", "CI-1004", "59170000004", "luis@example.com", now, now),
        )

    clients = {
        row["whatsapp_id"]: row["id"]
        for row in conn.execute("SELECT id, whatsapp_id FROM clients")
    }
    ana = clients["59176710767"]
    carlos = clients["59170000002"]
    maria = clients["59170000003"]
    luis_id = clients["59170000004"]

    def _ensure_invoice(
        number: str,
        cliente_id: int,
        descripcion: str,
        monto: float,
        saldo: float,
        emision: str,
        vencimiento: str,
        estado: str,
    ) -> None:
        exists = conn.execute(
            "SELECT id FROM invoices WHERE number = ?", (number,)
        ).fetchone()
        if exists:
            return
        conn.execute(
            """
            INSERT INTO invoices
                (number, cliente_id, descripcion, monto_original, saldo,
                 fecha_emision, fecha_vencimiento, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                number,
                cliente_id,
                descripcion,
                monto,
                saldo,
                emision,
                vencimiento,
                estado,
                now,
                now,
            ),
        )

    # Migrados: actualizar descripcion/estado canónico si faltan datos ricos
    conn.execute(
        """
        UPDATE invoices
        SET descripcion = COALESCE(descripcion, 'Factura ' || number),
            estado = CASE lower(estado)
                WHEN 'pendiente' THEN 'PENDIENTE'
                WHEN 'pagada' THEN 'PAGADA'
                WHEN 'vencida' THEN 'VENCIDA'
                WHEN 'anulada' THEN 'ANULADA'
                ELSE estado
            END,
            updated_at = ?
        """,
        (now,),
    )

    # Ana: varias facturas (pendiente, parcial, pagada, vencida)
    _ensure_invoice("F-1001", ana, "Servicio mensual", 150.0, 150.0, "2026-08-01", "2026-09-01", INV_PENDIENTE)
    _ensure_invoice("F-1004", ana, "Mantenimiento", 80.0, 80.0, "2026-09-01", "2026-10-01", INV_PENDIENTE)
    _ensure_invoice("F-1005", ana, "Instalación parcial", 300.0, 120.0, "2026-07-01", "2026-08-15", INV_PAGADA_PARCIAL)
    _ensure_invoice("F-1006", ana, "Cargo ya cancelado", 50.0, 0.0, "2026-05-01", "2026-06-01", INV_PAGADA)
    _ensure_invoice("F-1007", ana, "Cargo vencido", 90.0, 90.0, "2026-04-01", "2026-05-01", INV_VENCIDA)

    _ensure_invoice("F-1002", carlos, "Plan empresarial", 200.0, 0.0, "2026-07-01", "2026-08-01", INV_PAGADA)
    _ensure_invoice("F-1008", carlos, "Extras", 100.0, 100.0, "2026-08-01", "2026-09-15", INV_PENDIENTE)

    _ensure_invoice("F-1003", maria, "Consultoría", 320.0, 320.0, "2026-06-01", "2026-07-15", INV_VENCIDA)
    _ensure_invoice("F-1009", maria, "Soporte", 60.0, 30.0, "2026-08-01", "2026-09-20", INV_PAGADA_PARCIAL)

    _ensure_invoice("F-1010", luis_id, "Alta de servicio", 400.0, 400.0, "2026-08-01", "2026-09-30", INV_PENDIENTE)
    _ensure_invoice("F-1011", luis_id, "Anulada demo", 25.0, 25.0, "2026-01-01", "2026-02-01", INV_ANULADA)

    # Beatriz (pruebas con número real 59162135555): cliente + facturas espejo
    beatriz_wa = "59162135555"
    beatriz_row = conn.execute(
        "SELECT id FROM clients WHERE whatsapp_id = ?", (beatriz_wa,)
    ).fetchone()
    if beatriz_row is None:
        conn.execute(
            """
            INSERT INTO clients
                (whatsapp_id, nombre, nit, documento, telefono, email,
                 activo, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?, ?, 1, ?, ?)
            """,
            (
                beatriz_wa,
                "BEATRIZ MAMANI FLORES",
                "CI-6150994",
                beatriz_wa,
                "kira.mf7@gmail.com",
                now,
                now,
            ),
        )
        beatriz_id = conn.execute(
            "SELECT id FROM clients WHERE whatsapp_id = ?", (beatriz_wa,)
        ).fetchone()[0]
    else:
        beatriz_id = beatriz_row[0]
        # Mantener identidad real si el seed corre de nuevo (sin pisar otros campos)
        conn.execute(
            """
            UPDATE clients
            SET documento = COALESCE(documento, ?),
                email = COALESCE(email, ?),
                nombre = CASE
                    WHEN nombre LIKE 'BEATRIZ%' THEN nombre
                    ELSE ?
                END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                "CI-6150994",
                "kira.mf7@gmail.com",
                "BEATRIZ MAMANI FLORES",
                now,
                beatriz_id,
            ),
        )

    _ensure_invoice(
        "F-B001", beatriz_id, "Servicio mensual", 150.0, 150.0,
        "2026-08-01", "2026-09-01", INV_PENDIENTE,
    )
    _ensure_invoice(
        "F-B004", beatriz_id, "Mantenimiento", 80.0, 80.0,
        "2026-09-01", "2026-10-01", INV_PENDIENTE,
    )
    _ensure_invoice(
        "F-B005", beatriz_id, "Instalación parcial", 300.0, 120.0,
        "2026-07-01", "2026-08-15", INV_PAGADA_PARCIAL,
    )
    _ensure_invoice(
        "F-B006", beatriz_id, "Cargo ya cancelado", 50.0, 0.0,
        "2026-05-01", "2026-06-01", INV_PAGADA,
    )
    _ensure_invoice(
        "F-B007", beatriz_id, "Cargo vencido parcial", 90.0, 70.0,
        "2026-04-01", "2026-05-01", INV_PAGADA_PARCIAL,
    )
    _ensure_invoice(
        "F-B008", beatriz_id, "Servicio demo", 150.0, 150.0,
        "2026-08-01", "2026-09-15", INV_PENDIENTE,
    )
    _ensure_invoice(
        "F-B009", beatriz_id, "Mantenimiento parcial", 200.0, 80.0,
        "2026-07-01", "2026-08-20", INV_PAGADA_PARCIAL,
    )


def init_db() -> None:
    """Crea/migra clientes, facturas, pagos y sesiones de forma segura."""
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        if _needs_clients_migration(conn):
            _migrate_clients(conn)
        if _needs_invoices_migration(conn):
            _migrate_invoices(conn)
        _repair_client_foreign_keys(conn)
        conn.execute("PRAGMA foreign_keys = ON")

        _ensure_base_tables(conn)
        _seed_if_needed(conn)
        conn.commit()
    finally:
        conn.close()
