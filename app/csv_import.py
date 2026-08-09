"""Importación administrativa CSV de clientes y facturas (no expuesto por HTTP/WhatsApp)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.clients import (
    create_client,
    get_client_by_id,
    get_client_by_nit,
    get_client_by_whatsapp,
)
from app.db import (
    INV_ANULADA,
    INV_PAGADA,
    INV_PAGADA_PARCIAL,
    INV_PENDIENTE,
    INV_VENCIDA,
    init_db,
)
from app.invoices import create_invoice, get_invoice, validate_saldo

_VALID_ESTADOS = {
    INV_PENDIENTE,
    INV_PAGADA_PARCIAL,
    INV_PAGADA,
    INV_VENCIDA,
    INV_ANULADA,
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class RowError:
    archivo: str
    fila: int
    campo: str
    motivo: str

    def __str__(self) -> str:
        return f"{self.archivo}:fila {self.fila}: campo '{self.campo}': {self.motivo}"


@dataclass
class ImportSummary:
    clientes_leidos: int = 0
    clientes_creados: int = 0
    clientes_omitidos: int = 0
    clientes_con_error: int = 0
    facturas_leidas: int = 0
    facturas_creadas: int = 0
    facturas_omitidas: int = 0
    facturas_con_error: int = 0
    errores: list[RowError] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)

    def print_report(self) -> None:
        print("=== Resumen importación CSV ===")
        print(f"Clientes leídos: {self.clientes_leidos}")
        print(f"Clientes creados: {self.clientes_creados}")
        print(f"Clientes omitidos: {self.clientes_omitidos}")
        print(f"Clientes con error: {self.clientes_con_error}")
        print()
        print(f"Facturas leídas: {self.facturas_leidas}")
        print(f"Facturas creadas: {self.facturas_creadas}")
        print(f"Facturas omitidas: {self.facturas_omitidas}")
        print(f"Facturas con error: {self.facturas_con_error}")
        if self.omitidos:
            print("\n--- Omitidos / conflictos ---")
            for line in self.omitidos:
                print(f"  - {line}")
        if self.errores:
            print("\n--- Errores ---")
            for err in self.errores:
                print(f"  - {err}")


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _parse_activo(raw: str, *, archivo: str, fila: int) -> bool:
    v = _norm(raw).lower()
    if v in {"", "1", "true", "si", "sí", "yes", "activo"}:
        return True
    if v in {"0", "false", "no", "inactivo"}:
        return False
    raise ValueError((archivo, fila, "activo", f"valor inválido '{raw}'"))


def _parse_float(raw: str, *, campo: str, archivo: str, fila: int) -> float:
    text = _norm(raw).replace(",", ".")
    if not text:
        raise ValueError((archivo, fila, campo, "obligatorio"))
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError((archivo, fila, campo, f"número inválido '{raw}'")) from exc


def _parse_date(raw: str, *, campo: str, archivo: str, fila: int) -> str:
    text = _norm(raw)
    if not text:
        raise ValueError((archivo, fila, campo, "obligatorio"))
    if not _DATE_RE.match(text):
        raise ValueError((archivo, fila, campo, "usar formato YYYY-MM-DD"))
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError((archivo, fila, campo, "fecha inválida")) from exc
    return text


def _client_conflict(existing: dict, row: dict, matched_by: str) -> str | None:
    """Si la fila CSV no coincide con el cliente existente, describe el conflicto."""
    mismatches: list[str] = []
    wa = _norm(row.get("whatsapp_id"))
    if wa and wa != existing["whatsapp_id"]:
        mismatches.append(
            f"whatsapp_id CSV={wa} != existente={existing['whatsapp_id']}"
        )
    nit = _norm(row.get("nit")) or None
    if nit and existing["nit"] and nit != existing["nit"]:
        mismatches.append(f"nit CSV={nit} != existente={existing['nit']}")
    nombre = _norm(row.get("nombre"))
    if nombre and nombre != existing["nombre"]:
        mismatches.append(
            f"nombre CSV={nombre} != existente={existing['nombre']}"
        )
    if not mismatches:
        return None
    return (
        f"conflicto (match por {matched_by}, cliente_id={existing['id']}): "
        + "; ".join(mismatches)
        + " — no se modifica el existente"
    )


def _find_existing_client(row: dict) -> tuple[dict | None, str | None]:
    """
    Detecta duplicados sin modificar.
    Prioridad: id → NIT → whatsapp_id
    """
    id_raw = _norm(row.get("id"))
    if id_raw:
        try:
            cid = int(id_raw)
        except ValueError as exc:
            raise ValueError(
                ("?", 0, "id", f"entero inválido '{id_raw}'")
            ) from exc
        existing = get_client_by_id(cid)
        if existing is not None:
            return existing, f"id={cid}"

    nit = _norm(row.get("nit")) or None
    if nit:
        existing = get_client_by_nit(nit, only_active=False)
        if existing is not None:
            return existing, f"nit={nit}"

    wa = _norm(row.get("whatsapp_id"))
    if wa:
        existing = get_client_by_whatsapp(wa, only_active=False)
        if existing is not None:
            return existing, f"whatsapp_id={wa}"

    return None, None


def import_clients_csv(path: Path, summary: ImportSummary) -> None:
    archivo = path.name
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            summary.errores.append(
                RowError(archivo, 0, "header", "CSV sin encabezados")
            )
            return
        for i, row in enumerate(reader, start=2):  # 1 = header
            summary.clientes_leidos += 1
            try:
                whatsapp_id = _norm(row.get("whatsapp_id"))
                nombre = _norm(row.get("nombre"))
                if not whatsapp_id:
                    raise ValueError((archivo, i, "whatsapp_id", "obligatorio"))
                if not nombre:
                    raise ValueError((archivo, i, "nombre", "obligatorio"))

                try:
                    existing, key = _find_existing_client(row)
                except ValueError as exc:
                    if (
                        isinstance(exc.args[0], tuple)
                        and len(exc.args[0]) == 4
                        and exc.args[0][2] == "id"
                    ):
                        _, _, campo, motivo = exc.args[0]
                        raise ValueError((archivo, i, campo, motivo)) from exc
                    raise
                if existing is not None:
                    summary.clientes_omitidos += 1
                    conflict = _client_conflict(existing, row, key or "?")
                    if conflict:
                        summary.omitidos.append(f"{archivo}:fila {i}: {conflict}")
                    else:
                        summary.omitidos.append(
                            f"{archivo}:fila {i}: cliente omitido (duplicado por {key}, "
                            f"cliente_id={existing['id']})"
                        )
                    continue

                nit = _norm(row.get("nit")) or None
                documento = _norm(row.get("documento")) or None
                telefono = _norm(row.get("telefono")) or None
                email = _norm(row.get("email")) or None
                activo = _parse_activo(row.get("activo") or "", archivo=archivo, fila=i)

                create_client(
                    whatsapp_id=whatsapp_id,
                    nombre=nombre,
                    nit=nit,
                    documento=documento,
                    telefono=telefono,
                    email=email,
                    activo=activo,
                )
                summary.clientes_creados += 1
            except ValueError as exc:
                summary.clientes_con_error += 1
                if isinstance(exc.args[0], tuple) and len(exc.args[0]) == 4:
                    a, f, c, m = exc.args[0]
                    summary.errores.append(RowError(a, f, c, m))
                else:
                    summary.errores.append(
                        RowError(archivo, i, "-", str(exc))
                    )
            except Exception as exc:  # noqa: BLE001 — fila a fila
                summary.clientes_con_error += 1
                summary.errores.append(RowError(archivo, i, "-", str(exc)))


def import_invoices_csv(path: Path, summary: ImportSummary) -> None:
    archivo = path.name
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            summary.errores.append(
                RowError(archivo, 0, "header", "CSV sin encabezados")
            )
            return
        for i, row in enumerate(reader, start=2):
            summary.facturas_leidas += 1
            try:
                number = _norm(row.get("number"))
                if not number:
                    raise ValueError((archivo, i, "number", "obligatorio"))

                existing_inv = get_invoice(number)
                if existing_inv is not None:
                    summary.facturas_omitidas += 1
                    summary.omitidos.append(
                        f"{archivo}:fila {i}: factura omitida "
                        f"(number={number} ya existe, id={existing_inv['id']})"
                    )
                    continue

                cid_raw = _norm(row.get("cliente_id"))
                if not cid_raw:
                    raise ValueError((archivo, i, "cliente_id", "obligatorio"))
                try:
                    cliente_id = int(cid_raw)
                except ValueError as exc:
                    raise ValueError(
                        (archivo, i, "cliente_id", f"entero inválido '{cid_raw}'")
                    ) from exc

                client = get_client_by_id(cliente_id)
                if client is None:
                    raise ValueError(
                        (archivo, i, "cliente_id", f"cliente {cliente_id} no existe")
                    )

                monto = _parse_float(
                    row.get("monto_original") or "",
                    campo="monto_original",
                    archivo=archivo,
                    fila=i,
                )
                saldo_raw = _norm(row.get("saldo"))
                saldo = (
                    monto
                    if not saldo_raw
                    else _parse_float(
                        saldo_raw, campo="saldo", archivo=archivo, fila=i
                    )
                )
                try:
                    validate_saldo(monto, saldo)
                except ValueError as exc:
                    raise ValueError((archivo, i, "saldo", str(exc))) from exc

                fecha_vencimiento = _parse_date(
                    row.get("fecha_vencimiento") or "",
                    campo="fecha_vencimiento",
                    archivo=archivo,
                    fila=i,
                )
                fecha_emision_raw = _norm(row.get("fecha_emision"))
                fecha_emision = (
                    None
                    if not fecha_emision_raw
                    else _parse_date(
                        fecha_emision_raw,
                        campo="fecha_emision",
                        archivo=archivo,
                        fila=i,
                    )
                )

                estado_raw = _norm(row.get("estado")).upper()
                estado = estado_raw or None
                if estado is not None and estado not in _VALID_ESTADOS:
                    raise ValueError(
                        (
                            archivo,
                            i,
                            "estado",
                            f"inválido '{estado_raw}' "
                            f"(usar {', '.join(sorted(_VALID_ESTADOS))})",
                        )
                    )

                descripcion = _norm(row.get("descripcion")) or None

                create_invoice(
                    number=number,
                    cliente_id=cliente_id,
                    monto_original=monto,
                    saldo=saldo,
                    descripcion=descripcion,
                    fecha_emision=fecha_emision,
                    fecha_vencimiento=fecha_vencimiento,
                    estado=estado,
                )
                summary.facturas_creadas += 1
            except ValueError as exc:
                summary.facturas_con_error += 1
                if isinstance(exc.args[0], tuple) and len(exc.args[0]) == 4:
                    a, f, c, m = exc.args[0]
                    summary.errores.append(RowError(a, f, c, m))
                else:
                    summary.errores.append(RowError(archivo, i, "-", str(exc)))
            except Exception as exc:  # noqa: BLE001
                summary.facturas_con_error += 1
                summary.errores.append(RowError(archivo, i, "-", str(exc)))


def run_import(
    *,
    clients_csv: Path | None = None,
    invoices_csv: Path | None = None,
) -> ImportSummary:
    """Importa clientes y luego facturas. No borra ni actualiza filas existentes."""
    init_db()
    summary = ImportSummary()
    if clients_csv is not None:
        if not clients_csv.is_file():
            summary.errores.append(
                RowError(str(clients_csv), 0, "archivo", "no encontrado")
            )
        else:
            import_clients_csv(clients_csv, summary)
    if invoices_csv is not None:
        if not invoices_csv.is_file():
            summary.errores.append(
                RowError(str(invoices_csv), 0, "archivo", "no encontrado")
            )
        else:
            import_invoices_csv(invoices_csv, summary)
    return summary
