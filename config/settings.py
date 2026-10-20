"""Configuración de Django. Todo lo sensible o que cambia por entorno se lee de variables de entorno."""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nombre, defecto=""):
    return os.environ.get(nombre, defecto)


def env_bool(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_lista(nombre, defecto=""):
    return [parte.strip() for parte in env(nombre, defecto).split(",") if parte.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Falta DJANGO_SECRET_KEY")
    SECRET_KEY = "solo-para-desarrollo-no-usar-en-produccion"

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_q",
    "apps.cuentas",
    "apps.whatsapp",
    "apps.recordatorios",
    "apps.asistente",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = "cuentas.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = env("ZONA_HORARIA_DEFECTO", "America/Santiago")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^salud/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": env("LOG_LEVEL", "INFO")},
}

# --- Negocio ---
NOMBRE_NEGOCIO = env("NOMBRE_NEGOCIO", "Monardez Soft")

# --- WhatsApp Cloud API ---
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN")
# Con token se usa la API real; sin token los mensajes solo se muestran en la terminal.
WHATSAPP_CLIENTE = env(
    "WHATSAPP_CLIENTE",
    "apps.whatsapp.cliente.ClienteGraph" if WHATSAPP_TOKEN else "apps.whatsapp.cliente.ClienteConsola",
)
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET")
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_PLANTILLA_RECORDATORIO = env("WHATSAPP_PLANTILLA_RECORDATORIO", "recordatorio")
WHATSAPP_PLANTILLA_AVISO = env("WHATSAPP_PLANTILLA_AVISO", "aviso")
WHATSAPP_PLANTILLA_IDIOMA = env("WHATSAPP_PLANTILLA_IDIOMA", "es")

# --- Claude ---
CLAUDE_MODEL = env("ASISTENTE_MODELO", "claude-opus-5-5")
CLAUDE_EFFORT = env("ASISTENTE_EFFORT", "low")

# --- Django-Q2: cola en la misma base de datos, sin Redis ---
Q_CLUSTER = {
    "name": "notificacion",
    "orm": "default",
    "workers": int(env("Q_WORKERS", "2")),
    "timeout": 120,
    "retry": 180,
    "max_attempts": 1,
    "catch_up": False,
    "sync": env_bool("Q_SYNC", False),
}
