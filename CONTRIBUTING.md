# Contributing

Thanks for the interest. Arctic Base is a small project with a deliberate
v1 scope (single-user, no auth, polling-only, KND aesthetic). PRs welcome,
but please read the scope notes in [README.md](./README.md) first — features
explicitly marked out-of-scope likely won't be accepted.

## Local development

Requires Python 3.12+ with [`uv`](https://docs.astral.sh/uv/) and Node 20+
with [`pnpm`](https://pnpm.io/).

```sh
make sync        # install backend + frontend deps
make backend-dev # uvicorn with --reload on 0.0.0.0:2929
make frontend-dev # vite dev server with HMR
make test        # backend pytest + frontend svelte-check
make build       # production SPA build into frontend/dist/
```

The backend reads `ARCTIC_BASE_DATA` (default `./data`). For a clean dev
environment, point at a tmp dir: `ARCTIC_BASE_DATA=/tmp/arctic-dev make backend-dev`.

## Repo layout

```
backend/      FastAPI app (Python 3.12+, uv-managed)
  src/arctic_base/      package source
  tests/                pytest test suite (68 tests as of v1)
frontend/     Vite + Svelte 5 + TypeScript SPA (pnpm)
  src/lib/chrome/       Arctic Base shell components (always Arctic Base look)
  src/lib/themed/       per-workbench themed components (skin per workbench)
  src/App.svelte        router root
data/         workbench data (gitignored)
docs/         design specs and implementation plans
```

## Running tests

```sh
cd backend && uv run pytest -v       # 68 tests should pass
cd frontend && pnpm run check        # type-check + svelte-check
cd frontend && pnpm run build        # full production build
```

Tests use `tmp_path` fixtures and override the `get_storage` dependency, so
they do not touch `./data/`.

## Code style

- **Backend:** Pydantic v2, FastAPI, ruff for linting (`uv run ruff check`).
  Storage access goes through the `Storage` Protocol — never read/write files
  directly from API code.
- **Frontend:** Svelte 5 with scoped CSS. Theme tokens drive everything visual
  via `--wb-*` (per-workbench) and `--ab-*` (Arctic Base shell) custom
  properties. No CSS framework.

## Adding a new object kind

1. Add to `ObjectKind` enum in `backend/src/arctic_base/models.py`.
2. Wire a render path in `backend/src/arctic_base/api/render.py`.
3. Add a frontend viewer component under `frontend/src/lib/themed/` and
   route it in `frontend/src/App.svelte`.
4. Add an entry to `drawerOrder` in `WorkbenchDashboard.svelte`.
5. Optionally add a starter template in
   `backend/src/arctic_base/api/templates_data.py`.
6. Document in the conventions doc (`agent.py` `CONVENTIONS_MD` constant).
7. Add a backend test covering the round trip.

## Adding a new layout token

Layout tokens (density / corners / shadow / card-style / motif / banner-shape /
hero-style) live in `LayoutTokens` (`models.py`). To add a new axis:

1. Add the field with a default of `None` so existing themes don't break.
2. Map values to CSS in `_DENSITY_PADDING` / `_CORNER_RADIUS` / etc. in
   `render.py`'s `build_theme_style_block`.
3. Consume the value in `WorkbenchDashboard.svelte` via a `data-*` attribute.

## Before publishing your fork

If you're forking Arctic Base for your own deploy, check this list:

- [ ] `tar -czf data-backup-$(date +%F).tar.gz data/` if there's data to keep.
- [ ] Update `README.md` GitHub URL placeholder.
- [ ] Replace `LICENSE` copyright holder if you're not contributing back.
- [ ] Set `ARCTIC_BASE_DATA` to a real path in your deploy.
- [ ] Put Arctic Base behind a reverse proxy (Caddy / Tailscale / WireGuard).
      It has no auth and trusts the network.

## What's intentionally out of scope

These are explicit non-goals; PRs adding them will likely be closed:

- Auth, multi-tenant, RBAC.
- Real-time SSE / WebSockets for agents (polling-with-since-version is the
  v1 contract; the seam is there for a future upgrade).
- Server-side full-text search.
- A built-in chat panel (use Claude Code / Cursor; Arctic Base is for
  artifacts, not conversation).
- Anything that requires SMTP / external service configuration.

## Reporting issues

Please include:

- Arctic Base version (or commit hash if running from source).
- Python and Node versions.
- The relevant excerpt from `tail /tmp/arctic-base.log` (or wherever your
  process logs to) — Arctic Base emits structured JSON with request IDs.
- For UI bugs: browser, viewport size, and steps to reproduce.

## License

By contributing you agree your contributions are licensed under MIT (see
[LICENSE](./LICENSE)).
