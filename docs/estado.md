# Estado y decisiones — WhatsAppMVP

**Actualizado:** 2026-08-09  
**Norte (no perder):**

```text
WhatsApp (canal)
  → whatsapp_id
  → CLIENTE (identidad: nit, documento, nombre, teléfono, email)
  → FACTURAS / SALDOS
  → PAGOS (PENDIENTE → CONFIRMADO)
  → confirmación por WhatsApp
```

QR / cooperativa / pasarela: **lunes** (no bloquea el resto).

---

## Alcanzado

| Bloque | Estado |
|--------|--------|
| Webhook Meta GET/POST | OK |
| Token permanente System User `METAQR` | OK |
| URL estable ngrok | OK (`backyard-overture-schilling.ngrok-free.dev/webhook`) |
| Clientes + NIT/documento | OK |
| Facturas multi-estado + saldo | OK |
| Sesiones conversación | OK |
| Flujo chat: listar → elegir → monto → SI | OK |
| Pago `PENDIENTE` al confirmar en chat | OK |
| Chat: `cancelar` / `mis pagos` | OK |
| `POST /payments/confirm` (auth + idempotencia + atómico) | OK |
| Tests automáticos | suite completa (CSV + comandos chat) |
| Docs (`arquitectura`, `api`, `decisiones`, `despliegue`, `RETOMAR`, `estado`, `importacion-csv`) | OK |
| Importación CSV clientes/facturas (CLI admin) | OK — `scripts/import_csv.py` |
| Script `start-all.ps1` (uvicorn + ngrok) | OK |

### Flujo que ya funciona de punta a punta

```text
hola → facturas con saldo>0 → elegir → monto → si
  → payments PENDIENTE
POST /payments/confirm {CONFIRMADO}
  → saldo baja → WhatsApp “Pago confirmado”
```

---

## Falta (solo lunes — QR / cooperativa)

**MVP admin + chat sin QR: cerrado.** A–D y token de `/payments/confirm` ya están hechos.

Ver checklist completo: [`docs/lunes-proveedor.md`](lunes-proveedor.md)

1. Cuenta / credenciales del proveedor QR.
2. Generar/enviar QR o link tras el `SI` del chat.
3. Webhook del proveedor → adaptar a `payment_service` (ruta `/payments/provider`).
4. Probar confirmación real (no `DEMO-LIVE`).

**Esperando para mañana:** lista real de clientes/facturas (CSV) + cuenta/credenciales del proveedor QR-banco.  
Ver [`docs/RETOMAR.md`](RETOMAR.md) y [`docs/lunes-proveedor.md`](lunes-proveedor.md).

### Después (escala / producto)

- Token/app en producción Meta (número real, no solo test).
- PostgreSQL si crece el volumen.
- Panel admin (solo si lo piden).
- Multi-empresa / roles.

---

## Decisiones ya tomadas (no reabrir sin motivo)

1. WhatsApp es **canal**, no identidad.
2. NIT opcional; no se muestra ni se pide en cada chat.
3. Pago en dos tiempos: `PENDIENTE` (intención) → `CONFIRMADO` (mueve saldo).
4. Webhook Meta (`/webhook`) separado de confirmación de pagos (`/payments/confirm`).
5. Sin inventar APIs de banco/QR hasta tener proveedor.

---

## Preguntas para decidir ahora

1. ¿El lunes el QR es de **cooperativa**, **pasarela** u otro? (define el adaptador).
2. ¿Seguimos solo con número de prueba Meta o ya hay fecha para número productivo?

---

## Arranque rápido

Ver `docs/RETOMAR.md` y `docs/despliegue.md`.
