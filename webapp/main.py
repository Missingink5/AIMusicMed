"""Uvicorn entrypoint: ``uvicorn webapp.main:app``."""

from .app import create_app

app = create_app()
