# Arquitectura WhatsAppMVP

## Norte actual

```text
WhatsApp (canal)
  → webhook Meta
  → whatsapp_id
  → CLIENTE (identidad: nit, documento, nombre, teléfono, email)
  → FACTURAS (saldos)
  → SESIÓN (estado de conversación)
  → PAGOS (solicitud PENDIENTE; confirmación futura)
  → respuesta WhatsApp
```

WhatsApp **no** es la fuente de identidad: solo aporta `whatsapp_id`.

## Capas

| Pieza | Rol |
|-------|-----|
| `app/webhook.py` | Entrada Meta GET/POST |
| `app/conversation.py` | Estados + comandos `cancelar` / `mis pagos` |
| `app/clients.py` | Identidad del cliente |
| `app/invoices.py` | Facturas y saldos |
| `app/payments.py` | Solicitudes de pago |
| `app/payment_service.py` | Confirmación atómica / idempotente |
| `app/payments_api.py` | `POST /payments/confirm` |
| `app/csv_import.py` | Import CLI (no HTTP) |
| `app/sessions.py` | Estado del diálogo por `whatsapp_id` |
| `app/db.py` | SQLite, migraciones, seed |
| `app/whatsapp.py` | Envío Graph API |

## Modelo de datos

```text
clients 1 ─── N invoices
clients 1 ─── N payments
invoices 1 ─── N payments
whatsapp_id ─── sessions (1:1)
```

Base: SQLite (`invoices.db`).

## Fuera de alcance (hasta conectar proveedor)

- QR
- APIs bancarias / cooperativas / pasarelas
- Webhook de confirmación de terceros (se documenta en `docs/api.md` para el lunes)
