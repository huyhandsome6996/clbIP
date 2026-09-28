"""WSGI config cho CLB IP ĐHSP Huế 2.0 — Render dùng `gunicorn core.wsgi:application`."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

application = get_wsgi_application()
