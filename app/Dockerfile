# Base image: official Python on Alpine, pinned by digest.
#
# Debian-based images (python:*-slim) carry critical/high CVEs in Essential
# packages such as perl-base and util-linux that Debian marks "no fix", so no
# Debian image can pass a critical/high vulnerability scan. Alpine patches its
# base packages promptly, and this app needs nothing from the OS beyond libc,
# OpenSSL and the Python runtime. Every Python dependency ships musl wheels or
# is pure Python.
#
# Dependabot proposes digest bumps weekly (.github/dependabot.yml). Merging one
# and running the deploy workflow is how OS-level fixes reach production.
ARG BASE_IMAGE=python:3.13-alpine3.24@sha256:7415fbc3c9e4979cc717d92377ab2bc7b2b4a2af1ac03cc52b5f3f88efedaf3a

# ---- build stage: install the pinned dependency set into a virtualenv -------
FROM ${BASE_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apk upgrade --no-cache

WORKDIR /build
COPY requirements.txt .
# The runtime image is immutable and has no package manager, so the
# virtualenv's own pip is removed once the install is done.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && rm -rf /opt/venv/bin/pip* \
              /opt/venv/lib/python3.13/site-packages/pip \
              /opt/venv/lib/python3.13/site-packages/pip-*.dist-info

# ---- runtime stage: no pip, no compilers, unprivileged user -----------------
FROM ${BASE_IMAGE}

# Apply Alpine security updates published since the base was built. Then remove
# pip and the wheel bundled for `python -m ensurepip`: nothing installs packages
# at runtime, and pip's vendored msgpack/setuptools copies are what scanners
# flag on an otherwise clean Alpine image.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/python3.13/ensurepip/_bundled \
              /usr/local/lib/python3.13/site-packages/pip \
              /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
              /usr/local/bin/pip* \
    && addgroup -S app \
    && adduser -S -G app -h /home/app app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    HOME=/home/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --chown=app:app . .

# Cloud Run does not need root. Streamlit only needs a writable HOME.
USER app

EXPOSE 8080

# Cloud Run ignores Dockerfile HEALTHCHECK, so none is declared; it probes the
# container port itself. fileWatcherType=none: the source never changes inside
# a running container, so there is nothing to watch.
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8080", "--server.address=0.0.0.0", \
    "--server.fileWatcherType=none"]
