"""Shared test setup.

The utils modules resolve the GCP project at import time, so the env var must
exist before any test module imports them. No test touches a real GCP API.
"""
import os

# Assigned unconditionally so a developer shell that exports real values
# (for example from .env) cannot change what the assertions expect.
os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["GEMINI_MODEL"] = "gemini-test-model"
os.environ["VERTEX_AI_LOCATION"] = "test-region"
os.environ.pop("REFRESH_TRANSFER_CONFIG", None)
