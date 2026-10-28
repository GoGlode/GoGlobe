"""Единственная основная точка входа сервера GoGlobe v0.3."""
from app.bff import create_app

app = create_app()
