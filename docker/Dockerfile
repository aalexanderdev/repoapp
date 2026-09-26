# syntax=docker/dockerfile:1.7

# ---------- Etapa 1: build de dependencias ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# Dependencias del sistema mínimas para compilar wheels si hiciera falta
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .

# Instala en un prefix aislado para copiar solo lo necesario a la imagen final
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Etapa 2: imagen final, mínima ----------
FROM python:3.12-slim AS runtime

# Usuario no root por seguridad
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Copiamos solo las dependencias instaladas (no build tools, no cache)
COPY --from=builder /install /usr/local

COPY app/main.py .

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_VERSION=1.0.0

EXPOSE 8080

USER app

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# gunicorn como servidor de producción (1 worker + 4 threads para mantener métricas de Prometheus consistentes en memoria)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "main:app"]
