FROM node:24-slim AS web-build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY next.config.ts tsconfig.json next-env.d.ts ./
COPY src ./src
# Web app manifest, icons and service worker, so Sheltie can be installed as an app.
COPY public ./public
RUN npm run build


FROM python:3.12-slim

# MALLOC_ARENA_MAX: glibc gives every thread its own malloc arena by default, which
# leaves a threaded Python process holding far more memory than it uses.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    PORT=8710 \
    SHELTIE_API_PORT=8711 \
    SHELTIE_API_BASE=http://127.0.0.1:8711

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl iproute2 iputils-ping tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY monitors ./monitors
COPY config ./config
# The dashboard is static files (next build exports to ./out); app.py serves them.
COPY --from=web-build /app/out ./web
COPY scripts/entrypoint.sh ./entrypoint.sh

RUN mkdir -p /app/state

# /health on the API returns 503 when the check loop has stopped completing, not just when it is down.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8710}/" >/dev/null && curl -fsS "http://127.0.0.1:${SHELTIE_API_PORT:-8711}/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./entrypoint.sh"]
