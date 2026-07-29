FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system finalboss \
    && useradd --system --gid finalboss --home-dir /app finalboss \
    && python -m pip install --no-cache-dir uv==0.12.0

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY scripts ./scripts

RUN chown -R finalboss:finalboss /app
USER finalboss

ENTRYPOINT ["/app/.venv/bin/finalboss"]
CMD ["doctor"]
