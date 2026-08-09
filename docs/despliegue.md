# Despliegue local estable (token + URL)

## 1. Token permanente de Meta (System User)

El token de **API Setup** caduca (horas/días) y provoca `SEND ok=False` / 401.

### Pasos (una sola vez)

1. Abre [Business Settings → System users](https://business.facebook.com/latest/settings/system-users).
2. **Add** → crea un system user (ej. `whatsappmvp-bot`). Rol: **Admin** (o el mínimo que Meta permita con WhatsApp).
3. Selecciona el usuario → **Assign assets**:
   - App **SALDOS DNT** (o la tuya) → control total / Manage app.
   - WhatsApp Business Account (WABA) → Manage WhatsApp Business accounts.
4. **Generate token** → elige la misma app.
5. Permisos mínimos:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `business_management` (si Meta lo pide en el flujo)
6. Copia el token **una vez** y guárdalo solo en `.env` (nunca en git ni en el chat).

### Aplicar en el proyecto

```env
WHATSAPP_TOKEN=EAAxxxxxxxx
PHONE_NUMBER_ID=1292640300591762
```

Reinicia uvicorn:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Prueba:

```powershell
python -c "from dotenv import load_dotenv; load_dotenv(override=True); from app.whatsapp import send_message; print(send_message('59176710767', 'Token permanente OK'))"
```

Debe imprimir `True` y llegar el mensaje.

---

## 2. URL estable (ngrok con dominio fijo)

Ya usamos el dominio reservado:

```text
https://backyard-overture-schilling.ngrok-free.dev
```

Callback en Meta (no cambia al reiniciar si usas el mismo `--url`):

```text
https://backyard-overture-schilling.ngrok-free.dev/webhook
```

### Arranque correcto de ngrok

No uses solo `ngrok http 8000` (puede asignar otra URL). Usa siempre:

```powershell
ngrok http 8000 --url https://backyard-overture-schilling.ngrok-free.dev
```

O el script del repo:

```powershell
.\scripts\start-ngrok.ps1
```

### Meta → Webhook

- Callback URL: `https://backyard-overture-schilling.ngrok-free.dev/webhook`
- Verify token: igual que `WHATSAPP_VERIFY_TOKEN` en `.env`
- Campo `messages` suscrito

Abrir `/webhook` en el navegador → `403 Forbidden` es **normal**.

---

## 3. Checklist al encender la PC

1. `.env` con token de **system user** (no el temporal de API Setup).
2. Arranque recomendado: `.\scripts\start-all.ps1` (uvicorn + ngrok).
   Alternativa: Terminal A uvicorn `127.0.0.1:8000` + Terminal B `.\scripts\start-ngrok.ps1`.
3. Meta ya apunta a esa URL (no hace falta reconfigurar si no cambió).
4. Prueba WhatsApp: `hola` (también `mis pagos`, `cancelar`).

## Seguridad

- Nunca commits de `.env`.
- Si el token se filtra: revócalo en System users y genera otro.
- `PUBLIC_BASE_URL` en `.env` es solo documentación local del dominio ngrok.
