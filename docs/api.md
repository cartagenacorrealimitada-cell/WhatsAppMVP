# API de pagos (segura)

La lógica financiera vive en `app/payment_service.py`.  
Autenticación HTTP pluggable: `app/payments_auth.py`.  
Endpoint: `POST /payments/confirm` (`app/payments_api.py`).

**Importante:** no usa ni modifica el webhook de Meta (`/webhook`).

## Autenticación (hoy)

Secreto interno en `.env`:

```env
PAYMENTS_CONFIRM_TOKEN=tu-secreto
```

Enviar en cada request:

```http
Authorization: Bearer tu-secreto
```

o

```http
X-QRDNT-Payments-Token: tu-secreto
```

El lunes se podrá añadir un adaptador del proveedor (HMAC, etc.) **sin** mezclarlo con el motor de saldos.

## Request

```json
{
  "payment_id": 4,
  "resultado": "CONFIRMADO",
  "referencia_externa": "TXN-123",
  "monto": 10.0,
  "moneda": "BOB",
  "notificar_whatsapp": true
}
```

- `payment_id`: referencia interna QRDNT (BD = verdad).
- `monto` / `moneda` / `referencia_externa`: se **comparan** con la BD; no se confía a ciegas.
- No se aceptan `cliente_id` ni `invoice_id` del body.

## Idempotencia

Misma `referencia_externa` → una sola vez impacto financiero (`payment_processed_refs` UNIQUE + `BEGIN IMMEDIATE`).

## Ejemplo PowerShell

```powershell
$headers = @{ Authorization = "Bearer $env:PAYMENTS_CONFIRM_TOKEN" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/payments/confirm `
  -Headers $headers -ContentType "application/json" `
  -Body '{"payment_id":4,"resultado":"CONFIRMADO","referencia_externa":"TXN-123","monto":10,"moneda":"BOB"}'
```

## Códigos de error (sin secretos)

| HTTP | code |
|------|------|
| 401 | unauthorized |
| 400 | monto_mismatch, moneda_mismatch, missing_*, … |
| 404 | payment_not_found |
| 409 | invalid_payment_state |

## Webhook del proveedor (lunes)

```text
Webhook banco/cooperativa
  → ProviderAuthAdapter (doc real)
  → mapear a payment_id + ref + monto + moneda
  → payment_service.confirm_or_reject_payment
```
