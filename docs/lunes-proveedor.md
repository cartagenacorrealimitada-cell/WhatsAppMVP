# Pack lunes — conectar proveedor QR / cooperativa

**Objetivo:** el lunes enchufar el proveedor real **sin reinventar** el motor de pagos de QRDNT.

**Ya existe y no se toca para cobrar:**
- Chat WhatsApp → crea `payments` en `PENDIENTE`
- `payment_service` → valida, confirma atómico, idempotente
- `POST /payments/confirm` → puerta HTTP con auth interna

**Lo que falta del proveedor:** autenticación + formato de su webhook + envío del QR/link.

---

## 1. Qué pedir a la cooperativa / pasarela

Lleva esta lista a la reunión o al correo:

| # | Pregunta | Para qué |
|---|----------|----------|
| 1 | ¿Cómo nos autentican su webhook? (API Key, Bearer, HMAC, IP, certificado…) | Implementar `ProviderAuthAdapter` |
| 2 | ¿URL/método que debemos exponer? (ellos empujan a nosotros) | Nueva ruta p.ej. `/payments/provider` |
| 3 | ¿Formato exacto del JSON/XML del aviso de pago? | Mapper → `payment_id`, monto, moneda, ref |
| 4 | ¿Cómo viaja nuestra referencia interna? ¿Nos dejan enviar `QRDNT-…` / `payment_id` al generar el QR? | Relacionar cobro ↔ pago PENDIENTE |
| 5 | ¿Nombre del campo de referencia de ellos? (TXN, id operación, etc.) | `referencia_externa` UNIQUE |
| 6 | Moneda y formato de monto (BOB, centavos, string…) | Validación vs BD |
| 7 | ¿Reintentos? ¿Debemos responder 200 en duplicados? | Ya soportamos idempotencia |
| 8 | Cómo generar el QR/link (API nuestra → ellos, o panel) | Tras el `SI` del chat |
| 9 | Ambiente de pruebas (sandbox) y credenciales | No usar prod el primer día |
| 10 | Contacto técnico + horario de logs | Incidencias |

**No inventar** respuestas: copiar de su documentación oficial.

---

## 2. Flujo objetivo del lunes

```text
Usuario WhatsApp: SI
  → QRDNT crea payment PENDIENTE (referencia_interna = QRDNT-…)
  → (NUEVO) pedir QR/link al proveedor con esa referencia
  → enviar QR o link por WhatsApp

Cliente paga en el banco/cooperativa
  → Proveedor llama a QRDNT /payments/provider  (NUEVO, thin)
       1) ProviderAuth (según su doc)
       2) mapear payload → payment_id + referencia_externa + monto + moneda
       3) llamar payment_service.confirm_or_reject_payment(...)
       4) responder 200 (también en duplicado)

  → Cliente recibe “Pago confirmado” (ya implementado)
```

**Importante:** el proveedor **no** debe llamar a `/payments/confirm` a pelo con nuestro secreto, salvo que acordemos ese contrato. Lo ideal es `/payments/provider` que traduzca su formato.

---

## 3. Checklist técnico QRDNT (orden del lunes)

### Mañana temprano
- [ ] uvicorn + `.\scripts\start-ngrok.ps1`
- [ ] Callback Meta sigue en URL fija `/webhook`
- [ ] `PAYMENTS_CONFIRM_TOKEN` en `.env` (secreto interno; no es el del banco)
- [ ] Probar chat: `hola` → factura → monto → `si` → sale `pago #id`

### Con la doc del proveedor en la mano
- [ ] Anotar mecanismo de auth (una sola frase)
- [ ] Anotar ejemplo real de payload (sanitizado, sin secretos)
- [ ] Definir cómo viaja `referencia_interna` / `payment_id` en el QR
- [ ] Implementar **solo** `ProviderAuth` + mapper + ruta `/payments/provider`
- [ ] Tests: auth falla / payload ok / duplicado / monto mismatch
- [ ] Prueba sandbox de punta a punta

### No hacer el lunes (salvo que lo pidas)
- Refactors grandes
- Panel admin
- Cambiar el webhook de Meta
- Saltar la validación de monto/moneda

---

## 4. Mapeo mínimo al motor actual

| Dato proveedor | Campo QRDNT |
|----------------|-------------|
| Id operación / TXN | `referencia_externa` |
| Monto cobrado | `monto` (debe == `payments.monto`) |
| Moneda | `moneda` (hoy `BOB`) |
| Nuestra ref en el QR | buscar `payments.referencia_interna` o `payment_id` |
| Éxito / rechazo | `resultado` CONFIRMADO / RECHAZADO |

Función a llamar (ya existe):

```python
from app.payment_service import confirm_or_reject_payment

confirm_or_reject_payment(
    payment_id=...,
    resultado="CONFIRMADO",
    referencia_externa="TXN-DEL-BANCO",
    monto=...,
    moneda="BOB",
    auth_ok=True,          # solo tras ProviderAuth OK
    auth_method="provider", # o "hmac", etc.
)
```

---

## 5. Criterio de “lunes listo”

Se considera integrado cuando:

1. Un `SI` en WhatsApp genera pago `PENDIENTE` **y** el usuario recibe QR/link.
2. Un pago sandbox del proveedor confirma **una sola vez** el saldo.
3. Un webhook duplicado no vuelve a descontar.
4. Un webhook sin auth válida no mueve dinero.
5. Meta `/webhook` sigue respondiendo mensajes normales.

---

## 6. Referencias internas

- Contrato HTTP interno: `docs/api.md`
- Estado del producto: `docs/estado.md`
- Arranque / token / ngrok: `docs/despliegue.md`
- Retomar sesión: `docs/RETOMAR.md`
