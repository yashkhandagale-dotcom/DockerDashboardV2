# ── Stage 1: build dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: lean runtime image ──────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="devops-dashboard"
LABEL description="DevOps Dashboard — Flask + Redis + Kubernetes"

# Non-root user — security best practice
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy only installed packages from builder (keeps image small)
COPY --from=builder /install /usr/local

# Copy application source
COPY app.py .

# Owned by non-root user
RUN chown -R appuser:appuser /app

# Docker-native health check (complements K8s probes)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')" || exit 1

USER appuser

EXPOSE 5000

CMD ["python", "app.py"]
