FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY --from=ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_NO_CACHE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && mkdir /data && chown 10001:10001 /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/packages/core:/app"
COPY apps/api /app/apps/api
COPY packages/core /app/packages/core
COPY infra/alembic.ini /app/infra/alembic.ini
COPY infra/migrations /app/infra/migrations
COPY tests /app/tests
USER 10001:10001
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
