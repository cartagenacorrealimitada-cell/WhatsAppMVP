# WhatsAppMVP

MVP para consultar el estado de una factura desde WhatsApp.

## Norte

```text
WhatsApp → webhook → SQLite → estado de factura → respuesta WhatsApp
```

## Arquitectura

Detalle: [`docs/arquitectura.md`](docs/arquitectura.md). Piezas clave: `webhook` → `conversation` → clientes/facturas/pagos/sesiones (SQLite); confirmación en `POST /payments/confirm`; CSV solo por CLI.

## Arranque (cada vez que enciendes la PC)

Guía detallada de **token permanente** + **URL estable**: [`docs/despliegue.md`](docs/despliegue.md).

**Si reinicias el PC o retomas otro día:** abre primero [`docs/RETOMAR.md`](docs/RETOMAR.md) (punto de guardado + URLs de Meta).

### 1. Configurar `.env`

```powershell
cd "c:\Users\dntkr\OneDrive\Escritorio\LAVORATORIO DAN\WhatsAppMVP"
copy .env.example .env
```

Edita `.env` (sin comillas):

| Variable | Dónde sacarla |
|----------|----------------|
| `WHATSAPP_TOKEN` | **System User** permanente (Business Settings). No uses el token temporal de API Setup |
| `WHATSAPP_VERIFY_TOKEN` | El mismo que pones en el Webhook de Meta |
| `PHONE_NUMBER_ID` | Meta → API Setup → Phone number ID (no el teléfono) |
| `PUBLIC_BASE_URL` | Dominio ngrok fijo: `https://backyard-overture-schilling.ngrok-free.dev` |
| `DATABASE_PATH` | Dejar `invoices.db` |
| `PAYMENTS_CONFIRM_TOKEN` | Secreto para `POST /payments/confirm` (Bearer / header) |

Verificar:

```powershell
python -c "from app.config import WHATSAPP_TOKEN, PHONE_NUMBER_ID; print(bool(WHATSAPP_TOKEN), PHONE_NUMBER_ID)"
```

Debe imprimir: `True` y tu Phone Number ID.

### 2. Dependencias (solo la primera vez o si falta algo)

```powershell
pip install -r requirements.txt
```

### 3–4. Arranque rápido (recomendado)

Una sola orden abre uvicorn + ngrok en dos ventanas:

```powershell
.\scripts\start-all.ps1
```

### Alternativa manual — Terminal A (FastAPI)

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Probar local: http://127.0.0.1:8000/docs

### Alternativa manual — Terminal B (ngrok URL fija)

```powershell
.\scripts\start-ngrok.ps1
```

Equivale a:

```powershell
ngrok http 8000 --url https://backyard-overture-schilling.ngrok-free.dev
```

Callback estable: `https://backyard-overture-schilling.ngrok-free.dev/webhook`

### 5. Meta — Webhook

- Callback URL: `https://backyard-overture-schilling.ngrok-free.dev/webhook`
- Verify token: igual que `WHATSAPP_VERIFY_TOKEN`
- **Verificar y guardar**
- Campo `messages` → **Suscrito**

### 6. Prueba

Desde el celular autorizado, al número de prueba de Meta:

```text
hola
```

Comandos útiles en el chat:

```text
mis pagos
cancelar
```

O legado:

```text
Factura F-1001
```

## Carga CSV (admin)

Importación administrativa de clientes y facturas (CLI, no HTTP):

```powershell
python scripts/import_csv.py --clientes data/ejemplos/clientes.csv --facturas data/ejemplos/facturas.csv
```

Detalle de formatos y reglas: [`docs/importacion-csv.md`](docs/importacion-csv.md).

## Facturas de prueba

| Número | Estado (ejemplo seed) |
|--------|------------------------|
| F-1001 | PENDIENTE |
| F-1002 | PAGADA |
| F-1003 | VENCIDA |
| F-1005 | PAGADA_PARCIAL |
| F-1007 | VENCIDA |

## Si algo falla

| Síntoma | Qué revisar |
|---------|-------------|
| `SEND ok=False` / 401 | Token temporal → crear System User permanente (`docs/despliegue.md`) y reiniciar uvicorn |
| ngrok offline / otra URL | Arrancar con `.\scripts\start-ngrok.ps1` (dominio fijo) |
| POST no llega | Campo `messages` suscrito + app suscrita al WABA |
| `Forbidden` en `/webhook` en el navegador | Normal (GET sin verify de Meta) |

## Estado

MVP **pre-QR cerrado**: clientes, facturas, sesiones, chat (`hola` / `mis pagos` / `cancelar`), pagos `PENDIENTE`, `/payments/confirm`, CSV CLI, `start-all`.  
Pendiente solo lunes: QR / cooperativa — [`docs/estado.md`](docs/estado.md), [`docs/lunes-proveedor.md`](docs/lunes-proveedor.md).
