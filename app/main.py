"""Punto de entrada de WhatsAppMVP."""

from fastapi import FastAPI

from app.invoices import init_db
from app.webhook import router as webhook_router

init_db()

app = FastAPI(title="WhatsAppMVP")
app.include_router(webhook_router)
