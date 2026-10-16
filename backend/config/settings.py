"""Django settings. Everything that differs between local and hosted comes from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # backend/
REPO_DIR = BASE_DIR.parent


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# DEMO_MODE=true (hosted): read-only precomputed results, live extraction endpoints disabled.
# DEMO_MODE=false (local): upload notes and run extraction against a local Ollama model.
# Defaults to true so a deployment never exposes live extraction by accident.
DEMO_MODE = env_bool("DEMO_MODE", True)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
README_URL = os.environ.get("README_URL", "https://github.com/ashwin-bb/clinical-registry-builder#readme")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "registry",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

REST_FRAMEWORK = {
    # No user accounts in this demo (see CLAUDE.md), so no authentication and no CSRF-protected sessions.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# Upload limits for live mode.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_UPLOAD_NOTES = 200
