"""Envío de respuestas a WhatsApp Cloud API."""

import json
import urllib.error
import urllib.request

from app.config import PHONE_NUMBER_ID, WHATSAPP_TOKEN


def send_message(to: str, text: str) -> bool:
    """Envía un mensaje de texto. True si OK, False si falla."""
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False
