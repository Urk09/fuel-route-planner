FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

# Show logs immediately; prepare the libraries at build time so the app starts faster.
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

# Use the virtual environment uv just created.
ENV PATH="/app/.venv/bin:$PATH"

# Don't run as the all-powerful "root" user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]