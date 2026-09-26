import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app  # noqa: E402


def client():
    app.testing = True
    return app.test_client()


def test_index_returns_200():
    c = client()
    resp = c.get("/")
    assert resp.status_code == 200
    assert "message" in resp.get_json()


def test_health_returns_ok():
    c = client()
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_metrics_endpoint_exposes_prometheus_format():
    c = client()
    resp = c.get("/metrics")
    assert resp.status_code == 200
    assert b"app_requests_total" in resp.data
