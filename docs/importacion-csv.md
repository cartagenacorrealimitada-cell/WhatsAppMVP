# Importación CSV (administrativa)

Herramienta de carga de datos **solo por CLI**. No está expuesta por FastAPI ni WhatsApp.

Flujo:

```text
clientes.csv → create/find cliente → cliente_id
facturas.csv → create_invoice(cliente_id=...)
```

## Requisitos

- Ejecutar desde la raíz del proyecto.
- Usa la misma SQLite que la app (`DATABASE_PATH`, por defecto `invoices.db`).
- No borra ni actualiza filas existentes. Duplicados/conflictos se reportan y se omiten.

## Detección de clientes duplicados

Prioridad:

1. Columna opcional `id` (si el cliente ya existe).
2. `nit` cuando viene informado.
3. `whatsapp_id`.

`whatsapp_id` identifica al cliente en el canal WhatsApp; **las facturas se relacionan solo por `cliente_id`**.

## Formato `clientes.csv`

Encabezados (UTF-8):

```text
whatsapp_id,nombre,nit,documento,telefono,email,activo
```

| Campo | Obligatorio | Notas |
|-------|-------------|--------|
| `whatsapp_id` | sí | ID canal WhatsApp |
| `nombre` | sí | |
| `nit` | no | vacío = sin NIT |
| `documento` | no | |
| `telefono` | no | |
| `email` | no | |
| `activo` | no | `1`/`0`, `true`/`false`, `si`/`no` (default activo) |
| `id` | no | solo para detectar duplicado existente |

Ejemplo: `data/ejemplos/clientes.csv`

## Formato `facturas.csv`

```text
number,cliente_id,descripcion,monto_original,saldo,fecha_emision,fecha_vencimiento,estado
```

| Campo | Obligatorio | Notas |
|-------|-------------|--------|
| `number` | sí | único; si ya existe → omitida |
| `cliente_id` | sí | FK a `clients.id` (no usar whatsapp_id) |
| `descripcion` | no | |
| `monto_original` | sí | `>= 0` |
| `saldo` | no | default = monto; `>= 0` y `<= monto_original` |
| `fecha_emision` | no | `YYYY-MM-DD` |
| `fecha_vencimiento` | sí | `YYYY-MM-DD` |
| `estado` | no | `PENDIENTE`, `PAGADA_PARCIAL`, `PAGADA`, `VENCIDA`, `ANULADA` |

Ejemplo: `data/ejemplos/facturas.csv` (ajusta `cliente_id` a los IDs reales tras importar clientes).

## Cómo ejecutar

Solo clientes:

```powershell
python scripts/import_csv.py --clientes data/ejemplos/clientes.csv
```

Clientes y facturas:

```powershell
python scripts/import_csv.py --clientes data/ejemplos/clientes.csv --facturas data/ejemplos/facturas.csv
```

Solo facturas (clientes ya cargados):

```powershell
python scripts/import_csv.py --facturas data/ejemplos/facturas.csv
```

Al finalizar imprime resumen:

```text
Clientes leídos / creados / omitidos / con error
Facturas leídas / creadas / omitidas / con error
```

Errores por fila: archivo, número de fila, campo, motivo. Una fila mala no detiene el resto.

Código de salida: `0` si no hay errores de fila; `1` si hubo al menos un error (aunque otras filas sí se importaron).

## Qué no hace

- No toca webhook Meta, WhatsApp, `/payments/confirm`, QR ni bancos.
- No es un endpoint HTTP.
