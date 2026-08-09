"""Configuración del proyecto."""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "invoices.db")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
# Secreto interno para POST /payments/confirm (pluggable; el lunes se añade auth del proveedor)
PAYMENTS_CONFIRM_TOKEN = os.getenv("PAYMENTS_CONFIRM_TOKEN", "")
