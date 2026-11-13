# syntax=docker/dockerfile:1
# ---------------------------------------------------------------- build stage
FROM python:3.14-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------------------------------------------------------------- runtime stage
FROM python:3.14-slim AS runtime
LABEL org.opencontainers.image.title="coldguard-backend" \
      org.opencontainers.image.description="ColdGuard API / worker"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 coldguard && useradd --system --uid 10001 --gid coldguard --home /app coldguard
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=coldguard:coldguard app ./app
COPY --chown=coldguard:coldguard alembic ./alembic
COPY --chown=coldguard:coldguard alembic.ini .
COPY --chown=coldguard:coldguard ml ./ml
COPY --chown=coldguard:coldguard scripts ./scripts
RUN chmod +x scripts/docker-entrypoint.sh && mkdir -p /app/reports && chown coldguard:coldguard /app/reports
USER 10001
EXPOSE 8000 9101
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 CMD curl -fsS http://localhost:8000/health || exit 1
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["api"]
