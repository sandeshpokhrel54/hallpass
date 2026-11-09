FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Dependencies first so they cache across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY hallpass/ hallpass/
ARG APP_VERSION=dev
ENV PORT=8080 APP_VERSION=$APP_VERSION PATH=/app/.venv/bin:$PATH
# Numeric user so the pod's runAsNonRoot check can verify it.
USER 1000
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn hallpass.api:app --host 0.0.0.0 --port ${PORT}"]
