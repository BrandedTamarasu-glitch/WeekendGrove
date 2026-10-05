FROM python:3.14-slim
WORKDIR /app
COPY server.py discovery.py discovery_providers.py weather.py ./
COPY static ./static
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home grove && mkdir /data && chown grove:grove /data
USER 10001:10001
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/state', timeout=2)"
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
