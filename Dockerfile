# Backend container (lane L2a). Production command by default;
# compose.yaml overrides it with --reload for development.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code edits do not reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# /data holds what must outlive a container: the climate response cache.
# It is created here and owned by the app user, so that a named volume
# mounted on it starts with that owner and the cache can write.
RUN useradd --create-home app && mkdir -p /data/climate-cache && chown -R app /app /data
USER app

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
