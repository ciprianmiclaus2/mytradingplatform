from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence.data_dirs import DATA_SCHEMA_VERSION, DATA_SUBDIRECTORIES
from tests.fakes import FakeProvider


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["data_schema_version"] == DATA_SCHEMA_VERSION
    assert body["market_data_provider"] == "yfinance"
    assert "version" in body and "server_time" in body


def test_startup_creates_data_directories(client: TestClient, data_dir: Path) -> None:
    for sub in DATA_SUBDIRECTORIES:
        assert (data_dir / sub).is_dir(), sub


def test_openapi_served_under_api_prefix(client: TestClient) -> None:
    assert client.get("/api/openapi.json").status_code == 200


def test_data_directory_not_served(client: TestClient) -> None:
    assert client.get("/data/metadata/schema_version.json").status_code == 404
    assert client.get("/metadata/schema_version.json").status_code == 404


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_cors_allows_dev_frontend_origin(client: TestClient) -> None:
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    resp = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_unhandled_exception_hides_stack_trace(settings: Settings) -> None:
    app = create_app(settings, provider=FakeProvider())
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    app.include_router(router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/api/boom")

    assert resp.status_code == 500
    assert resp.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": None,
        }
    }
    assert "secret" not in resp.text


def test_validation_errors_use_error_envelope(settings: Settings) -> None:
    app = create_app(settings, provider=FakeProvider())
    router = APIRouter()

    @router.get("/echo")
    def echo(n: int) -> dict[str, int]:
        return {"n": n}

    app.include_router(router, prefix="/api")
    with TestClient(app) as c:
        resp = c.get("/api/echo", params={"n": "abc"})

    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["query", "n"]


def test_persistence_errors_map_to_clear_responses(settings: Settings) -> None:
    from app.persistence.errors import IncompatibleSchemaError, LockTimeoutError

    app = create_app(settings, provider=FakeProvider())
    router = APIRouter()

    @router.get("/incompatible")
    def incompatible() -> None:
        raise IncompatibleSchemaError("positions/positions.parquet is incompatible")

    @router.get("/locked")
    def locked() -> None:
        raise LockTimeoutError("Timed out waiting for the data write lock")

    app.include_router(router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as c:
        r1 = c.get("/api/incompatible")
        r2 = c.get("/api/locked")

    assert r1.status_code == 500
    assert r1.json()["error"] == {
        "code": "incompatible_schema",
        "message": "positions/positions.parquet is incompatible",
        "details": None,
    }
    assert r2.status_code == 503
    assert r2.json()["error"]["code"] == "persistence_lock_timeout"


def test_startup_takes_backup_and_exposes_persistence(settings: Settings, data_dir: Path) -> None:
    with TestClient(create_app(settings, provider=FakeProvider())) as c:
        assert c.app.state.persistence.store.data_dir == data_dir.resolve()  # type: ignore[attr-defined]
    assert len([p for p in (data_dir / "backups").iterdir() if p.name.endswith("-startup")]) == 1


def test_startup_fails_on_incompatible_data_schema(settings: Settings, data_dir: Path) -> None:
    import json

    import pytest

    (data_dir / "metadata").mkdir(parents=True)
    (data_dir / "metadata" / "schema_version.json").write_text(json.dumps({"schema_version": 99}))
    with pytest.raises(Exception, match="migration is required"):
        with TestClient(create_app(settings, provider=FakeProvider())):
            pass
