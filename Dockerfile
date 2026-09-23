# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .
RUN python -m pip wheel --wheel-dir /wheels --requirement requirements.txt


FROM python:3.12-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8000

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

COPY --chown=app:app . .
RUN mkdir -p /app/media /app/private_documents \
    && chown -R app:app /app/media /app/private_documents \
    && chmod +x /app/docker/entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()"]
