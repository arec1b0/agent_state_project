FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 1. Install dependencies only (leverages Docker cache)
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Copy the actual application code
COPY . /app

# 3. Install the project itself
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "uvicorn", "src.agent_session.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]