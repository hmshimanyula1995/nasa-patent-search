"""Patent data refresh: trigger and status helpers for the in-app UI.

The app does not run the refresh MERGE itself. A BigQuery Scheduled Query
(a Data Transfer config) holds the SQL and is the only thing that performs
the refresh. The cron schedule on that config runs it automatically; the UI
button calls `start_manual_transfer_runs` to kick the same config off ad-hoc.

Set REFRESH_TRANSFER_CONFIG to the resource name of the Scheduled Query, e.g.
  projects/PROJECT/locations/REGION/transferConfigs/UUID
The button is hidden in deployments where this env var is unset.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import streamlit as st

logger = logging.getLogger(__name__)

COOLDOWN_DAYS = 7
STALE_WARNING_DAYS = 90
AGING_DAYS = 60


@dataclass
class RefreshStatus:
    configured: bool
    last_run_time: datetime | None
    last_run_state: str | None
    last_run_error: str | None
    last_run_id: str | None


def get_transfer_config() -> str | None:
    """Resource name of the Scheduled Query that performs the patent refresh."""
    return os.getenv("REFRESH_TRANSFER_CONFIG") or None


@st.cache_resource
def _get_transfer_client():
    from google.cloud import bigquery_datatransfer_v1

    return bigquery_datatransfer_v1.DataTransferServiceClient()


@st.cache_data(ttl=60, show_spinner=False)
def get_last_refresh() -> RefreshStatus:
    """Look up the most recent run of the configured Scheduled Query.

    Returns RefreshStatus with configured=False if the env var is unset, so
    callers can render a "not configured" message without try/except. Any
    API error is logged and surfaced as configured=True with last_run_time=None.
    """
    config_name = get_transfer_config()
    if not config_name:
        return RefreshStatus(False, None, None, None, None)

    try:
        from google.cloud import bigquery_datatransfer_v1

        client = _get_transfer_client()
        request = bigquery_datatransfer_v1.ListTransferRunsRequest(
            parent=config_name,
            page_size=5,
        )
        runs = list(client.list_transfer_runs(request=request))
    except Exception as exc:
        logger.error("Failed to list transfer runs for %s: %s", config_name, exc)
        return RefreshStatus(True, None, None, str(exc), None)

    if not runs:
        return RefreshStatus(True, None, None, None, None)

    latest = runs[0]
    run_time = latest.run_time
    if run_time and not isinstance(run_time, datetime):
        run_time = run_time.ToDatetime(tzinfo=timezone.utc)

    state = latest.state.name if latest.state else None
    error_msg = latest.error_status.message if latest.error_status else None
    run_id = latest.name.rsplit("/", 1)[-1] if latest.name else None

    return RefreshStatus(True, run_time, state, error_msg, run_id)


def days_since(ts: datetime | None) -> int | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).days


def cooldown_remaining(last_run_time: datetime | None) -> int:
    """Days the user must wait before the next manual refresh is allowed.

    Returns 0 when the cooldown has elapsed (or no prior successful run),
    so the button can be enabled. Returns a positive integer when the
    cooldown is still active.
    """
    if last_run_time is None:
        return 0
    if last_run_time.tzinfo is None:
        last_run_time = last_run_time.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - last_run_time
    remaining = timedelta(days=COOLDOWN_DAYS) - elapsed
    return max(0, remaining.days + (1 if remaining.seconds > 0 else 0))


def trigger_refresh() -> tuple[bool, str]:
    """Start a manual run of the configured Scheduled Query.

    Returns (success, message). The message is safe to surface in a toast.
    """
    config_name = get_transfer_config()
    if not config_name:
        return False, "Refresh is not configured for this deployment."

    try:
        from google.cloud import bigquery_datatransfer_v1
        from google.protobuf import timestamp_pb2

        client = _get_transfer_client()
        requested = timestamp_pb2.Timestamp()
        requested.FromDatetime(datetime.now(timezone.utc))
        request = bigquery_datatransfer_v1.StartManualTransferRunsRequest(
            parent=config_name,
            requested_run_time=requested,
        )
        response = client.start_manual_transfer_runs(request=request)
    except Exception as exc:
        logger.error("Failed to start manual transfer run: %s", exc)
        return False, (
            "The refresh could not be started. The Cloud Run service account "
            "may be missing the BigQuery Data Transfer permissions, or the "
            "Scheduled Query resource name in REFRESH_TRANSFER_CONFIG may be "
            "incorrect. Ask an admin to check the Cloud Run logs."
        )

    runs = list(response.runs) if response.runs else []
    if not runs:
        return False, (
            "The refresh request was accepted but no run was created. "
            "Check the BigQuery Scheduled Queries page in the GCP console."
        )

    run_id = runs[0].name.rsplit("/", 1)[-1]
    logger.info("Started manual transfer run: %s", run_id)
    get_last_refresh.clear()
    return True, (
        f"Refresh started successfully. Job ID: {run_id}. "
        "The refresh runs in BigQuery and typically completes in a few "
        "minutes. Reload this page after it finishes to see the updated "
        "last-refresh timestamp."
    )
