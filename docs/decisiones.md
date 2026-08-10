# Decisiones

## D1 — WhatsApp es canal, no identidad
La identidad vive en `clients` (nit, documento, nombre, teléfono, email).  
`whatsapp_id` solo enlaza el canal con el cliente.

## D2 — NIT opcional
No todos los clientes tienen NIT al inicio. Columna nullable + índice `idx_clients_nit`.  
No se muestra ni se pide NIT en cada conversación de WhatsApp.

## D3 — Pagos en dos tiempos
1. Chat crea `payments` en `PENDIENTE` (intención).  
2. Solo `CONFIRMADO` reduce saldo.  
Así el lunes se enchufa el proveedor sin rehacer el diálogo.

## D4 — Sin QR/bancos hasta tener proveedor
La tabla y funciones existen; no hay APIs externas inventadas.

## D5 — SQLite + migración segura
Se preservan filas existentes; si SQLite reescribe FK a tablas `*_legacy_mig`, `init_db` las repara.

## D6 — Comandos globales de chat
`cancelar` reinicia la sesión en cualquier estado.  
`mis pagos` / `pagos` lista las últimas solicitudes sin crear endpoints HTTP nuevos.

## D7 — Formato único de tablas WhatsApp
Saldos y pagos se muestran siempre con el mismo patrón ASCII (Cliente + título + tabla monospace).
Columna `Doc`: prefijo **F** = factura (cliente con NIT), **R** = recibo (cliente sin NIT), sin guion en pantalla (`F1001`, `RB001`).
