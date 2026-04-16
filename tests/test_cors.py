from fastapi.testclient import TestClient

from app.main import app, get_cors_origins


def test_rawtxt_origin_is_allowed_by_default():
    assert "https://rawtxt.in" in get_cors_origins()
    assert "https://www.rawtxt.in" in get_cors_origins()


def test_rawtxt_preflight_is_allowed():
    client = TestClient(app)

    response = client.options(
        "/entries",
        headers={
            "Origin": "https://rawtxt.in",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://rawtxt.in"


def test_unlisted_origin_preflight_is_rejected():
    client = TestClient(app)

    response = client.options(
        "/entries",
        headers={
            "Origin": "https://not-rawtxt.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 400
