FROM node:24-slim AS web-build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY next.config.ts tsconfig.json next-env.d.ts ./
COPY src ./src
RUN npm run build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    PORT=8710 \
    SHELTIE_API_PORT=8711 \
    SHELTIE_API_BASE=http://127.0.0.1:8711

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl iproute2 iputils-ping tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=web-build /usr/local/bin/node /usr/local/bin/node

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY monitors ./monitors
COPY config ./config
COPY package.json package-lock.json* ./
COPY --from=web-build /app/.next ./.next
COPY --from=web-build /app/node_modules ./node_modules
COPY scripts/entrypoint.sh ./entrypoint.sh

RUN mkdir -p /app/state

# /health on the API returns 503 when the check loop has stopped completing, not just when it is down.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8710}/" >/dev/null && curl -fsS "http://127.0.0.1:${SHELTIE_API_PORT:-8711}/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./entrypoint.sh"]
