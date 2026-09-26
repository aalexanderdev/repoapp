"""
Aplicación de ejemplo (Flask) usada para demostrar el pipeline
completo de CI/CD, contenedores, Kubernetes y monitoreo.

Endpoints:
- GET /            -> mensaje de bienvenida
- GET /health      -> healthcheck (usado por probes de Kubernetes)
- GET /metrics     -> métricas en formato Prometheus
"""

import os
import time

from flask import Flask, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

app = Flask(__name__)

REQUEST_COUNT = Counter(
    "app_requests_total", "Total de requests recibidos", ["endpoint", "method", "status"]
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds", "Latencia de requests", ["endpoint"]
)


@app.route("/")
def index():
    start = time.time()
    response = jsonify(
        {
            "message": "Hola! Esta es la app de demo del pipeline DevOps",
            "version": APP_VERSION,
        }
    )
    REQUEST_COUNT.labels(endpoint="/", method="GET", status=200).inc()
    REQUEST_LATENCY.labels(endpoint="/").observe(time.time() - start)
    return response


@app.route("/health")
def health():
    REQUEST_COUNT.labels(endpoint="/health", method="GET", status=200).inc()
    return jsonify({"status": "ok"}), 200


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
