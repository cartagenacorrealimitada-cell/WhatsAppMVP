# Retomar aquí

**Fecha del punto de guardado:** 2026-08-09 ~22:58 (UTC-4)  
**Estado:** MVP **pre-QR** operativo + tablas WhatsApp unificadas (F/R + TOTAL) + clientes reales cargados.  
**Al volver:**
1. Arrancar stack (`start-all` / uvicorn + ngrok).
2. Seguir pruebas o importar más CSV reales.
3. **No QR/banco** hasta tener cuenta + doc del proveedor ([`docs/lunes-proveedor.md`](lunes-proveedor.md)).

---

## 1. Estado del proyecto (ya hecho)

| Área | Estado |
|------|--------|
| Flujo WhatsApp | `hola` → tabla saldos → monto → `si` → pago `PENDIENTE` |
| Tablas chat | Formato único `Doc/Saldo|Monto/Est` + fila **TOTAL** (`app/tables.py`) |
| Prefijos doc | **F** = factura (con NIT), **R** = recibo (sin NIT); sin guion en pantalla |
| Comandos | `cancelar`, `mis pagos`, `hola` |
| Clientes reales | CSV `data/clientes_reales.csv` (Dante, Beatriz, Rubén, etc.) |
| Beatriz | `59162135555`, CI-6150994, `kira.mf7@gmail.com`, docs `RB*` |
| Dante | `59176710767`, email `dantecartagena@icloud.com`, docs `F*` |
| CSV admin | `scripts/import_csv.py` |
| Pagos confirm | `POST /payments/confirm` (auth + idempotencia) |
| Arranque | `powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1` |
| Tests | `python -m unittest discover -s tests -v` → OK (44+) |
| URL / webhook | `https://backyard-overture-schilling.ngrok-free.dev/webhook` |
| Token Meta | System User `METAQR` (permanente) |

**Norte:** WhatsApp → cliente → facturas/recibos → saldos → pagos → WhatsApp.

---

## 2. Meta (operativo)

- App: SALDOS DNT · WhatsApp test `15556592498`
- Callback: URL fija ngrok + campo `messages`
- Token solo en `.env` (`WHATSAPP_TOKEN`)
- Si `#131030`: número no está en lista de destinatarios de prueba (máx. ~5)
- Si `WinError 10013` al arrancar uvicorn: puerto 8000 ya ocupado → no abrir segundo proceso

---

## 3. Checklist al encender el PC

```powershell
cd "c:\Users\dntkr\OneDrive\Escritorio\LAVORATORIO DAN\WhatsAppMVP"
powershell -ExecutionPolicy Bypass -File .\scripts\start-all.ps1
```

Verificar `.env`: `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `PHONE_NUMBER_ID`, `PUBLIC_BASE_URL`, `PAYMENTS_CONFIRM_TOKEN`.

**Importante:** `.env` e `invoices.db` **no** van en git — están solo en este PC/OneDrive. No los borres.

Humo WhatsApp:

```text
hola
mis pagos
cancelar
```

Números de prueba: Dante `59176710767` · Beatriz `59162135555` · Rubén `59177511597` (si están en Meta).

Más CSV:

```powershell
python scripts/import_csv.py --clientes data/clientes_reales.csv --facturas data/facturas_reales.csv
```

---

## 4. Datos útiles (no secretos)

| Dato | Valor |
|------|--------|
| Repo remoto | `origin/main` (hacer `git pull` al volver si hubo push) |
| Phone Number ID | `1292640300591762` |
| Dominio ngrok | `backyard-overture-schilling.ngrok-free.dev` |
| DB local | `invoices.db` |

---

## 5. Qué decirle al asistente al volver

```text
Retomamos desde docs/RETOMAR.md
Pre-QR OK: tablas F/R + TOTAL, clientes reales.
Pendiente: más pruebas / CSV / cuenta QR-banco (docs/lunes-proveedor.md).
No implementar QR hasta tener doc del proveedor.
```

---

## 6. Qué NO hacer

- No borrar `.env` ni `invoices.db`
- No commitear tokens ni Excel con datos sensibles
- No cambiar Callback URL de Meta a otra URL random de ngrok
- No implementar QR/bancos sin documentación real
- No exponer import CSV por FastAPI
- No abrir dos uvicorn a la vez (puerto 8000)
