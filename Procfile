web: python manage.py collectstatic --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 30
worker: python manage.py qcluster
