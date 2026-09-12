"""Shared test setup.

The utils modules resolve the GCP project at import time, so the env var must
exist before any test module imports them. No test touches a real GCP API.
"""
import os

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GEMINI_MODEL", "gemini-test-model")
os.environ.setdefault("VERTEX_AI_LOCATION", "test-region")
