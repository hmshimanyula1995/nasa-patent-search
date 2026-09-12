"""Tests for utils.refresh cooldown logic and transfer-run status parsing."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils import refresh


def _now():
    return datetime.now(timezone.utc)


def test_days_since_handles_none_and_naive_datetimes():
    assert refresh.days_since(None) is None
    assert refresh.days_since(_now() - timedelta(days=3)) == 3
    assert refresh.days_since((_now() - timedelta(days=2)).replace(tzinfo=None)) == 2


@pytest.mark.parametrize(
    "age_days, expected",
    [(None, 0), (8, 0), (7, 0), (6.5, 1), (0.5, 7)],
)
def test_cooldown_remaining(age_days, expected):
    last = None if age_days is None else _now() - timedelta(days=age_days)
    assert refresh.cooldown_remaining(last) == expected


def test_get_last_refresh_reports_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("REFRESH_TRANSFER_CONFIG", raising=False)
    refresh.get_last_refresh.clear()
    status = refresh.get_last_refresh()
    assert status.configured is False
    assert status.last_run_time is None


def _run(name, state, when, error=None):
    return SimpleNamespace(
        name=f"projects/p/locations/us/transferConfigs/c/runs/{name}",
        state=SimpleNamespace(name=state),
        run_time=when,
        error_status=SimpleNamespace(message=error) if error else None,
    )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("REFRESH_TRANSFER_CONFIG", "projects/p/locations/us/transferConfigs/c")
    refresh.get_last_refresh.clear()
    refresh._get_transfer_client.clear()
    yield
    refresh.get_last_refresh.clear()


def test_get_last_refresh_uses_latest_run_and_last_success_separately(configured, monkeypatch):
    latest = _run("r2", "FAILED", _now() - timedelta(days=1), error="boom")
    older = _run("r1", "SUCCEEDED", _now() - timedelta(days=10))
    client = SimpleNamespace(list_transfer_runs=lambda request: [latest, older])
    monkeypatch.setattr(refresh, "_get_transfer_client", lambda: client)
    status = refresh.get_last_refresh()
    assert status.configured is True
    assert status.last_run_state == "FAILED"
    assert status.last_run_error == "boom"
    assert status.last_run_id == "r2"
    assert status.last_successful_run_time == older.run_time
    assert refresh.cooldown_remaining(status.last_successful_run_time) == 0


def test_get_last_refresh_survives_api_errors(configured, monkeypatch):
    def _boom(request):
        raise RuntimeError("permission denied")
    client = SimpleNamespace(list_transfer_runs=_boom)
    monkeypatch.setattr(refresh, "_get_transfer_client", lambda: client)
    status = refresh.get_last_refresh()
    assert status.configured is True
    assert status.last_run_time is None
    assert status.last_run_error == "permission denied"


def test_trigger_refresh_returns_sanitized_failure(configured, monkeypatch):
    def _boom(request):
        raise RuntimeError("403 projects/secret")
    client = SimpleNamespace(start_manual_transfer_runs=_boom)
    monkeypatch.setattr(refresh, "_get_transfer_client", lambda: client)
    ok, msg = refresh.trigger_refresh()
    assert ok is False
    assert "projects/secret" not in msg


def test_trigger_refresh_reports_started_run(configured, monkeypatch):
    response = SimpleNamespace(runs=[_run("r9", "PENDING", _now())])
    client = SimpleNamespace(start_manual_transfer_runs=lambda request: response)
    monkeypatch.setattr(refresh, "_get_transfer_client", lambda: client)
    ok, msg = refresh.trigger_refresh()
    assert ok is True
    assert "Refresh started" in msg


def test_trigger_refresh_without_config(monkeypatch):
    monkeypatch.delenv("REFRESH_TRANSFER_CONFIG", raising=False)
    assert refresh.trigger_refresh() == (False, "Refresh is not configured for this deployment.")
