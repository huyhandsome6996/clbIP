"""ASGI config cho CLB IP ĐHSP Huế 2.0 (dự phòng cho WebSocket tương lai)."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

application = get_asgi_application()
