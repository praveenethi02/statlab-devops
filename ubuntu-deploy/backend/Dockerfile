FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/data/accounts.sqlite3 SERVE_FRONTEND=false
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 statlab \
    && useradd --uid 10001 --gid statlab --no-create-home statlab \
    && mkdir /data && chown statlab:statlab /data
COPY server.py app_backend.py database.py statistics_engine.py reports.py ./
COPY migrations/ migrations/
COPY scripts/maintenance.py scripts/maintenance.py
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "server.py"]
