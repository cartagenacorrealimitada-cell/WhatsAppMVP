# WhatsAppMVP

MVP para consultar el estado de una factura desde WhatsApp.

## Norte

```text
WhatsApp → webhook → SQLite → estado de factura → respuesta WhatsApp
```

## Arquitectura

```text
WhatsAppMVP/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
└── app/
    ├── main.py
    ├── config.py
    ├── webhook.py
    ├── invoices.py
    ├── parser.py
    ├── invoice_service.py
    └── whatsapp.py
```

## Arranque (cada vez que enciendes la PC)

### 1. Configurar `.env`

```powershell
cd "c:\Users\dntkr\OneDrive\Escritorio\LAVORATORIO DAN\WhatsAppMVP"
copy .env.example .env
```

Edita `.env` (sin comillas):

| Variable | Dónde sacarla |
|----------|----------------|
| `WHATSAPP_TOKEN` | Meta → WhatsApp → API Setup → token (si falla el envío con 401, genera uno nuevo) |
| `WHATSAPP_VERIFY_TOKEN` | El mismo que pones en el Webhook de Meta |
| `PHONE_NUMBER_ID` | Meta → API Setup → Phone number ID (no el teléfono) |
| `DATABASE_PATH` | Dejar `invoices.db` |

Verificar:

```powershell
python -c "from app.config import WHATSAPP_TOKEN, PHONE_NUMBER_ID; print(bool(WHATSAPP_TOKEN), PHONE_NUMBER_ID)"
```

Debe imprimir: `True` y tu Phone Number ID.

### 2. Dependencias (solo la primera vez o si falta algo)

```powershell
pip install -r requirements.txt
```

### 3. Terminal A — FastAPI

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Probar local: http://127.0.0.1:8000/docs

### 4. Terminal B — ngrok

```powershell
ngrok http 8000
```

Copia la URL `https://....ngrok-free.dev` (cambia al reiniciar ngrok).

### 5. Meta — Webhook

- Callback URL: `https://TU-URL-NGROK/webhook`
- Verify token: igual que `WHATSAPP_VERIFY_TOKEN`
- **Verificar y guardar**
- Campo `messages` → **Suscrito**

### 6. Prueba

Desde el celular autorizado, al número de prueba de Meta, envía:

```text
Factura F-1001
```

Respuesta esperada: estado de la factura (ej. pendiente / Ana López).

## Facturas de prueba

| Número | Estado |
|--------|--------|
| F-1001 | pendiente |
| F-1002 | pagada |
| F-1003 | vencida |

## Si algo falla

| Síntoma | Qué revisar |
|---------|-------------|
| `SEND ok=False` o no responde WhatsApp | Token caducado → generar otro y reiniciar uvicorn |
| ngrok offline / Not Found en raíz | Normal en `/`; usa `/docs`. Reinicia ngrok y actualiza Meta |
| POST no llega | Campo `messages` suscrito + app suscrita al WABA |
| `Forbidden` en `/webhook` en el navegador | Normal (GET sin verify de Meta) |

## Estado

MVP funcional. Flujo completo verificado.
