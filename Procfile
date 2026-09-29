web: gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 30
release: python manage.py migrate
