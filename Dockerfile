FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.29 /uv /bin/uv

ARG PYPI_INDEX=https://pypi.org/simple
ENV UV_LINK_MODE=copy UV_INDEX_URL=${PYPI_INDEX} UV_HTTP_TIMEOUT=120 \
    VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv venv /opt/venv \
    && uv export --frozen --no-hashes --no-emit-project -o /tmp/requirements.txt \
    && uv pip install -r /tmp/requirements.txt

COPY . .
RUN uv pip install --no-deps .

CMD ["pytest", "-q"]
