# MediaHub (Python + ffmpeg + yt-dlp). Збірка з каталогу backend/.
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        unzip \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# Deno у PATH — для yt-dlp EJS/remote-components (див. config.YT_DLP_EXTRA_ARGS)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/opt/deno sh \
    && ln -sf /opt/deno/bin/deno /usr/local/bin/deno

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Скрипт генерується в образі — не потрібен окремий файл у git на сервері.
RUN useradd --create-home --uid 1000 mediahub \
    && printf '%s\n' \
        '#!/bin/sh' 'set -e' \
        'chown -R mediahub:mediahub /app/state' \
        'if [ -f /app/channels.txt ]; then' \
        '    chown mediahub:mediahub /app/channels.txt' \
        'fi' \
        'exec gosu mediahub "$@"' \
        > /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R mediahub:mediahub /app

# Старт як root лише для chown томів; робочий процес — gosu → mediahub
USER root

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-u", "app.py"]
