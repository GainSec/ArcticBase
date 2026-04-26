.PHONY: dev backend-dev backend-run frontend-dev build test backend-test frontend-check sync clean \
        docker-build docker-run docker-stop docker-logs docker-push docker-clean

# ----- Native dev -----

backend-dev:
	cd backend && uv run uvicorn arctic_base.main:app --reload --port 2929 --host 0.0.0.0

backend-run:
	cd backend && uv run arctic-base

frontend-dev:
	cd frontend && pnpm dev

build:
	cd frontend && pnpm run build

sync:
	cd backend && uv sync
	cd frontend && pnpm install

test: backend-test frontend-check

backend-test:
	cd backend && uv run pytest -v

frontend-check:
	cd frontend && pnpm run check

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache
	rm -rf frontend/node_modules frontend/dist

# ----- Docker -----

# Override these on the command line, e.g.
#   make docker-build VERSION=1.0.1 IMAGE=ghcr.io/me/arctic-base
VERSION ?= 1.0.0
IMAGE   ?= arctic-base
TAG     ?= $(VERSION)
VCS_REF := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

docker-build:
	docker build \
	  --build-arg VERSION=$(VERSION) \
	  --build-arg VCS_REF=$(VCS_REF) \
	  --build-arg BUILD_DATE=$(BUILD_DATE) \
	  -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

docker-run:
	docker run -d --name arctic-base \
	  -p 2929:2929 \
	  -v $$PWD/data:/data \
	  --restart unless-stopped \
	  $(IMAGE):$(TAG)

docker-stop:
	-docker stop arctic-base
	-docker rm arctic-base

docker-logs:
	docker logs -f arctic-base

docker-push:
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

# Build a multi-arch image (amd64 + arm64) and push in one step.
# Requires `docker buildx create --use` once on the host.
docker-buildx-push:
	docker buildx build \
	  --platform linux/amd64,linux/arm64 \
	  --build-arg VERSION=$(VERSION) \
	  --build-arg VCS_REF=$(VCS_REF) \
	  --build-arg BUILD_DATE=$(BUILD_DATE) \
	  -t $(IMAGE):$(TAG) -t $(IMAGE):latest \
	  --push .

docker-clean:
	-docker rmi $(IMAGE):$(TAG) $(IMAGE):latest
