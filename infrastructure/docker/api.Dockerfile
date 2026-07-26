FROM python:3.12-slim

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY infrastructure ./infrastructure
ENV PYTHONPATH=packages/shared/src:apps/api/src
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "qforge_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

