"""Punto de entrada de WhatsAppMVP."""

from fastapi import FastAPI

from app.webhook import router as webhook_router

app = FastAPI(title="WhatsAppMVP")
app.include_router(webhook_router)
