FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8004

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app

USER app

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8004\")}/health', timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn research_agent.server:create_app --factory --host 0.0.0.0 --port ${PORT:-8004}"]
