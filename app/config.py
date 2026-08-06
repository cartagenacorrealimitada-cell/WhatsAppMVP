"""Configuración del proyecto."""

import os

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "invoices.db")
