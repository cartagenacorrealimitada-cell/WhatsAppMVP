# WhatsAppMVP

MVP para consultar el estado de una factura desde WhatsApp.

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
    └── whatsapp.py
```

## Flujo objetivo

WhatsApp → webhook → consulta SQLite → respuesta WhatsApp

## Estado

Esqueleto del proyecto. Sin lógica de negocio implementada.
