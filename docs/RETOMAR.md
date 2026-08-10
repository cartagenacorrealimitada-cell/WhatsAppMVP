# Retomar aquí

**Fecha del punto de guardado:** 2026-08-09 ~13:40 (UTC-4)  
**Estado:** MVP **pre-QR cerrado** y validado en WhatsApp (`hola` / `cancelar` / `mis pagos`).  
**Esperando para mañana:**
1. Lista real de clientes/facturas (import CSV).
2. Cuenta / credenciales del proveedor QR-banco ([`docs/lunes-proveedor.md`](lunes-proveedor.md)).

**No implementar QR ni APIs de banco** hasta tener esa documentación.

---

## 1. Estado del proyecto (ya hecho)

| Área | Estado |
|------|--------|
| Flujo WhatsApp | `hola` → facturas → monto → `si` → pago `PENDIENTE` |
| Comandos chat | `cancelar`, `mis pagos` / `pagos` |
| DB | `clients`, `invoices`, `payments`, `sessions` |
| CSV admin (CLI) | `scripts/import_csv.py` — [`docs/importacion-csv.md`](importacion-csv.md) |
| Confirmación pagos | `POST /payments/confirm` (auth + idempotencia) |
| Arranque diario | `.\scripts\start-all.ps1` (si ExecutionPolicy bloquea: `powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1`) |
| Tests | `python -m unittest discover -s tests -v` → OK |
| URL estable | `https://backyard-overture-schilling.ngrok-free.dev` |
| Callback Meta | `https://backyard-overture-schilling.ngrok-free.dev/webhook` |
| Token permanente | **LISTO** (System User `METAQR`, caducidad Nunca) |

**Norte:** WhatsApp → cliente → facturas → saldos → pagos → WhatsApp.  
QR / bancos / cooperativa: **solo con doc real del proveedor**.

Resumen: [`docs/estado.md`](estado.md)

---

## 2. Meta (referencia; ya operativo)

- System User: **METAQR** (portafolio Oficina)  
- WhatsApp: **`15556592498`**  
- App: SALDOS DNT  
- Callback: `https://backyard-overture-schilling.ngrok-free.dev/webhook` + campo `messages`  
- Token solo en `.env` → `WHATSAPP_TOKEN=` (nunca en el chat)

Si envío falla con 401: regenerar token System User → `.env` → reiniciar uvicorn. Guía: [`docs/despliegue.md`](despliegue.md)

---

## 3. Checklist al encender el PC

```powershell
cd "c:\Users\dntkr\OneDrive\Escritorio\LAVORATORIO DAN\WhatsAppMVP"
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

Verificar `.env`: `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `PHONE_NUMBER_ID`, `PUBLIC_BASE_URL`, `PAYMENTS_CONFIRM_TOKEN`.

Prueba de humo en WhatsApp:

- Dante: `59176710767`
- Beatriz (lista real + facturas/pagos demo): `59162135555`

```text
hola
mis pagos
cancelar
```

**Meta:** cada número debe estar en la lista de destinatarios de prueba o el bot no podrá responder (`#131030`).

Cuando llegue la lista real:

```powershell
python scripts/import_csv.py --clientes data/clientes_reales.csv --facturas data/facturas_reales.csv
```

(Ver formatos en [`docs/importacion-csv.md`](importacion-csv.md).)

---

## 4. Datos útiles (no secretos)

| Dato | Valor |
|------|--------|
| Cliente prueba WhatsApp | `59176710767` (Dante) / `59162135555` (Beatriz) |
| Phone Number ID (env) | `1292640300591762` |
| Dominio ngrok | `backyard-overture-schilling.ngrok-free.dev` |
| DB | `invoices.db` |

---

## 5. Qué decirle al asistente al volver

```text
Retomamos desde docs/RETOMAR.md
MVP pre-QR cerrado. Pendiente: lista real (CSV) + cuenta QR/banco (docs/lunes-proveedor.md).
No implementar QR ni APIs de banco hasta tener doc del proveedor.
```

---

## 6. Qué NO hacer

- No borrar `.env` ni `invoices.db`
- No commitear tokens ni listas reales de clientes con datos sensibles
- No cambiar la Callback URL de Meta a otra URL random de ngrok
- No implementar QR/bancos/webhook de proveedor sin documentación real
- No exponer import CSV por FastAPI
