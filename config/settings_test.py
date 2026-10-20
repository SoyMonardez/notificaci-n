import os

os.environ.setdefault("DJANGO_SECRET_KEY", "clave-de-tests")

from .settings import *  # noqa: E402, F403
from .settings import MIDDLEWARE, Q_CLUSTER  # noqa: E402

DEBUG = False
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]
ALLOWED_HOSTS = ["testserver"]
SECURE_SSL_REDIRECT = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
TIME_ZONE = "America/Santiago"

WHATSAPP_CLIENTE = "apps.whatsapp.cliente.ClienteMemoria"
WHATSAPP_APP_SECRET = "secreto-de-prueba"
WHATSAPP_VERIFY_TOKEN = "token-de-verificacion"

Q_CLUSTER = {**Q_CLUSTER, "sync": True}
