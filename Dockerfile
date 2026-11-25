# Tonetool: the API and the built frontend in one image. Put an HTTPS proxy (Caddy, see
# docker-compose.yml) in front of it; the app itself speaks plain HTTP on port 8000.

# -- 1. build the frontend ----------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# -- 2. the app ---------------------------------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
WORKDIR /app

# dependencies first, so that changing the code does not reinstall them
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

COPY --from=frontend /build/dist /app/frontend/dist
COPY docker/server.toml /app/docker/server.toml

# the library (imported scores, edited pieces, the trash) lives on a volume and is not run as root
RUN useradd --uid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin tonetool \
    && mkdir /data && chown tonetool /data
USER tonetool
VOLUME /data

ENV PATH="/app/.venv/bin:$PATH" TONETOOL_CONFIG=/app/docker/server.toml
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# 0.0.0.0 is allowed because the server refuses it without a login. Trusting any X-Forwarded-For
# is fine only because nothing but the proxy can reach this port (see docker-compose.yml).
CMD ["tonetool", "serve", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
