# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for Arctic Base.
# - Stage 1: build the Svelte SPA with Node + pnpm.
# - Stage 2: install Python runtime deps with uv into a venv.
# - Stage 3: minimal runtime image; non-root user, healthcheck, OCI labels.

ARG PYTHON_VERSION=3.13
ARG NODE_VERSION=24

##### Stage 1: build the SPA #####
FROM node:${NODE_VERSION}-alpine AS frontend-build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

##### Stage 2: install Python deps + build the project as a wheel into a venv #####
FROM python:${PYTHON_VERSION}-slim AS python-build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /build
RUN pip install --no-cache-dir uv

# Create a venv at a fixed path the runtime stage will copy verbatim.
RUN uv venv /opt/arctic-venv
ENV VIRTUAL_ENV=/opt/arctic-venv

# Copy the manifest first so dep resolution is layer-cached when only source changes.
COPY backend/pyproject.toml backend/uv.lock* ./
COPY backend/src ./src

# Install the project + all runtime deps as a real wheel install (non-editable).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache .

##### Stage 3: runtime #####
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=1.0.0
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Arctic Base" \
      org.opencontainers.image.description="Self-hosted workbench host for AI agents" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/yourname/arctic-base" \
      org.opencontainers.image.documentation="https://github.com/yourname/arctic-base#readme"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/arctic-venv/bin:${PATH}" \
    ARCTIC_BASE_DATA=/data \
    ARCTIC_BASE_PORT=2929 \
    ARCTIC_BASE_HOST=0.0.0.0 \
    ARCTIC_BASE_FRONTEND_DIST=/app/frontend/dist \
    ARCTIC_BASE_SEED_DATA=/app/seed

# Create a non-root user for runtime + the data volume mount point.
RUN groupadd --system --gid 1000 arctic \
 && useradd --system --gid arctic --uid 1000 --create-home --shell /bin/false arctic \
 && mkdir -p /data /app \
 && chown -R arctic:arctic /data /app

WORKDIR /app

# Copy the prebuilt venv (with the wheel-installed arctic_base package) from python-build.
COPY --from=python-build --chown=arctic:arctic /opt/arctic-venv /opt/arctic-venv

# Copy the prebuilt SPA.
COPY --from=frontend-build --chown=arctic:arctic /app/dist /app/frontend/dist

# Bundle the seed workbench (the recursive `arctic-base` overview). On first
# start, if /data is empty, this is copied into /data so a fresh container
# has something useful to look at.
COPY --chown=arctic:arctic backend/seed /app/seed

USER arctic

VOLUME ["/data"]
EXPOSE 2929

# Healthcheck hits /api/health every 30s.
HEALTHCHECK --interval=30s --timeout=4s --start-period=8s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:2929/api/health',timeout=3).status==200 else 1)" \
  || exit 1

CMD ["python", "-m", "arctic_base"]
