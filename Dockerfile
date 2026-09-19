FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY docs ./docs
COPY Dockerfile ./Dockerfile

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 interra \
    && mkdir -p /app/artifacts/traces \
    && chown -R interra:interra /app

USER interra

CMD ["python", "-m", "agent.demo"]
