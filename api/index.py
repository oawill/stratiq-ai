"""Vercel entrypoint / local `uvicorn api.index:app`. The app itself lives in stratiq/api.py."""
from stratiq.api import app  # noqa: F401
