FROM node:22-alpine AS charts
WORKDIR /build
COPY package.json package-lock.json ./
COPY scripts/vendor.mjs scripts/vendor.mjs
RUN npm ci --omit=dev

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/data/accounts.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 statlab \
    && useradd --uid 10001 --gid statlab --no-create-home statlab \
    && mkdir /data && chown statlab:statlab /data
COPY server.py app_backend.py database.py statistics_engine.py reports.py hrml ./
COPY migrations migrations
COPY static static
COPY scripts/maintenance.py scripts/maintenance.py
COPY --from=charts /build/static/vendor static/vendor
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["python", "server.py"]
