"""Punto de entrada de WhatsAppMVP."""

from fastapi import FastAPI

from app.db import init_db
from app.payments_api import router as payments_router
from app.webhook import router as webhook_router

init_db()

app = FastAPI(title="WhatsAppMVP")
app.include_router(webhook_router)
app.include_router(payments_router)
