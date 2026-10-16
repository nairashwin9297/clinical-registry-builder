# Full app (Django API + React UI) in one container, for running locally.
# The hosted demo is the static GitHub Pages build instead (see .github/workflows/pages.yml).
#
#   docker build -t registry-builder .
#   docker run --rm -p 8000:8000 registry-builder                     # demo mode, http://localhost:8000
#   docker run --rm -p 8000:8000 -e DEMO_MODE=false \
#     -e OLLAMA_URL=http://host.docker.internal:11434 registry-builder  # live mode, Ollama on the host

# Stage 1: build the React app.
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime. Django serves the built frontend through WhiteNoise.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=false \
    DEMO_MODE=true \
    ALLOWED_HOSTS=localhost,127.0.0.1 \
    SQLITE_PATH=/app/var/db.sqlite3 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/notes.csv data/results.json data/
COPY --from=frontend /app/frontend/dist frontend/dist
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
# Run as an unprivileged user; /app/var holds the SQLite database (mount a volume there to keep reviews).
RUN useradd --create-home app && mkdir -p /app/var && chown app /app/var && chmod +x /app/docker-entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
