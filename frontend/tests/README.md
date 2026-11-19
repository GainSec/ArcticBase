# Loading regressions

From `frontend/`, run `pnpm install --frozen-lockfile`, `pnpm test`, and `pnpm check`.

Tests use installed Google Chrome by default. To use Playwright's browser instead, run `pnpm exec playwright install chromium` and then `PLAYWRIGHT_CHANNEL=chromium pnpm test`.

The test runner starts a dedicated Vite server on `127.0.0.1:3939` with strict port selection. Every API request is intercepted with synthetic data; there is no backend proxy or production data dependency. Slow-response tests hold requests until assertions complete rather than depending on server speed.

Coverage includes progressive cards and totals, four concurrent statistics requests, abort-on-navigation, unknown/failed statistics, creation during enrichment, concurrent workbench resource loading, single metadata reads for each viewer kind, archive/pin/reorder/delete controls, stale route responses, same-workbench theme freshness, deterministic last-file selection, and equivalent object URLs.
