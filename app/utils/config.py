"""Runtime configuration helpers shared across utils."""
import os


def get_project() -> str:
    """Return the active GCP project ID.

    Resolution order:
      1. GOOGLE_CLOUD_PROJECT env var (set by `gcloud run deploy --set-env-vars`)
      2. Application Default Credentials project (metadata server on Cloud Run)

    Raises RuntimeError if neither resolves so the app fails fast at startup
    instead of silently querying a project the caller does not own.
    """
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        return project

    import google.auth

    _, project = google.auth.default()
    if not project:
        raise RuntimeError(
            "GCP project not set. Provide GOOGLE_CLOUD_PROJECT env var or run "
            "with Application Default Credentials whose project is configured."
        )
    return project
