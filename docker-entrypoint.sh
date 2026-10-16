#!/bin/sh
set -e
cd /app/backend

# A local container doesn't need a fixed secret: generate one per start unless SECRET_KEY is given.
# (Django refuses to start with DEBUG=false and the built-in development key.)
if [ -z "$SECRET_KEY" ]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  export SECRET_KEY
fi

python manage.py migrate --noinput
# Load the bundled notes + Colab results on first start only, so restarts keep your reviews.
python manage.py import_results --if-empty

# Long timeout: in live mode one request runs a whole note through Ollama, which can take minutes on a CPU.
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 900
