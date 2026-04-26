"""Agent-facing endpoints.

Designed to minimize context cost: `/agent` is a redirect to the OpenAPI spec, the conventions
doc is tight and only covers what OpenAPI can't express, and the bootstrap endpoint replaces a
multi-step setup with one call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from arctic_base.logging_setup import get_recent_activity
from arctic_base.api.deps import get_storage
from arctic_base.api.templates_data import (
    get_template as _get_template,
    list_templates as _list_templates,
)
from arctic_base.models import Banner, WorkbenchMeta
from arctic_base.storage.errors import NotFound
from arctic_base.storage.filesystem import FilesystemStorage

router = APIRouter(prefix="/agent", tags=["agent"])

# Top-level redirect — registered separately on the app, not inside the /api router.
top_router = APIRouter()


@top_router.get("/agent", include_in_schema=False)
def agent_landing() -> RedirectResponse:
    """Convenience redirect: hand the agent this URL and it lands on the API contract."""

    return RedirectResponse(url="/openapi.json", status_code=302)


CONVENTIONS_MD = """\
# Arctic Base — Agent Conventions

You are talking to **Arctic Base**, a self-hosted workbench host. The user (a human) views and
responds via a browser; you (the agent) act via this HTTP API. The full machine-readable contract
is at `/openapi.json`. This document covers only what the OpenAPI spec cannot express.

## What a workbench is

A workbench is one project's themed workspace. It holds **objects** of these kinds:

- `md` — Markdown docs (rendered in-browser, themed; task-list checkboxes supported).
- `html` / `approval-html` — self-contained HTML you author for review or interactive forms.
- `qa-form` — short ad-hoc Q&A forms. (Authored as `html` in v1; the kind is for filing.)
- `runbook` — structured task list (JSON content). First-class state the agent reads + writes.
- `image` — images for the user to view.
- `file` — generic binary uploads.

Each object has `pinned: bool` (sticks to top of its drawer) and `archived: bool` (hidden from
default lists, restorable). Default `list_objects` excludes archived; pass
`?include_archived=true` to see them.

The user-visible **per-workbench dashboard** is themed by the workbench's `theme.md` file; so are
rendered MD, Q&A forms, and approval HTML. The Arctic Base **tools** (top-level dashboard, text
editor, file browser, image viewer) are always Arctic Base styled. The top nav adopts the
workbench theme when inside a workbench.

## Bootstrap (preferred path)

Hit `POST /api/agent/bootstrap` with `{project_title, suggested_slug?, local_path?}`. It returns
the created workbench plus a checklist of follow-up confirmations. Walk the user through the
checklist one item at a time. Don't pile on questions — one at a time, terse.

## Theme contract

Per-workbench `theme.md` has YAML frontmatter (machine-readable tokens) + Markdown prose body
(brand voice / component metaphors). Required `core` tokens every theme MUST define:

```
core: bg, surface, ink, muted, rule, accent, accent-2, success, error
typography: body, mono   (each: fontFamily, fontSize, fontWeight, lineHeight, letterSpacing?)
rounded: sm, md, lg
spacing: unit, gutter, margin
custom: { ... }   (freeform; per-workbench extras)
layout: { ... }   (optional; structural composition)
```

`layout:` is an optional block that drives composition of the per-workbench dashboard, not just
colours. All fields optional; sensible defaults when omitted.

```
layout:
  density:      compact | comfortable | spacious            # padding/gap scale
  corners:      sharp | soft | rounded | full               # card corner radius
  shadow:       hard-offset | soft | glow | none            # card shadow style
  card-style:   bolted | flat | floating | inset            # card decoration
  motif:        bolts | hex | tape | none                   # corner accent on cards
  banner-shape: rect | t-shape | circle | none              # banner clip-path
  hero-style:   cover | flat | crt-monitor | none           # how banner renders
```

Layout choices surface to served HTML as extra CSS variables: `--wb-card-radius`,
`--wb-card-shadow`, `--wb-layout-padding`, `--wb-layout-gap`. Reference them when authoring HTML
that should match the workbench's structural feel (not just its colours).

Tokens are exposed as CSS variables prefixed `--wb-` on themed surfaces. When you author HTML for
a workbench, **reference `var(--wb-bg)` / `var(--wb-accent)` / `var(--wb-rounded-md)` /
`var(--wb-card-radius)` / `var(--wb-card-shadow)` / etc.** so your doc auto-themes. HTML that
doesn't reference `--wb-*` is served unchanged.

## Review-HTML rules (CRITICAL)

Approval/pitch HTML you author MUST stay self-contained:

- Inline CSS + inline JS. No external dependencies.
- `localStorage` is the canonical local cache.
- A JSON-export button captures recorded state.
- Mobile-safe (no horizontal overflow).
- Cards/sections collapsed by default for dense review sets.
- Decision vocabulary follows the workflow ("Approve / Needs changes / Reject / Defer …").

The Arctic Base API mirror is **additive**: feature-detect `window.workbench` and call
`saveAll()` / `submit()` in addition to `localStorage`. The HTML must still work when opened
standalone from disk.

## `window.workbench` JS runtime

Arctic Base injects this into served HTML:

```ts
window.workbench = {
  context: { workbench, object, objectKind, title, createdAt },
  theme:   { tokens: {core,typography,rounded,spacing,custom}, prose },
  save(key, value): Promise<void>,
  saveAll(state):   Promise<void>,    // POST autosave (no state_version bump)
  load(key):        Promise<unknown>,
  loadAll():        Promise<object>,  // returns latest payload
  submit(state):    Promise<{version: number}>,  // bumps state_version, wakes pollers
  onRemoteChange(cb): () => void,    // v1: stub; SSE upgrade later
};
```

Authoring rule:

```js
async function persist(state) {
  localStorage.setItem('doc-state-v1', JSON.stringify(state));
  if (window.workbench) await window.workbench.saveAll(state);
}
async function onUserSubmit(state) {
  await persist(state);
  if (window.workbench) await window.workbench.submit(state);
}
```

## Polling for user responses

After you create a Q&A form / approval HTML, poll for the user's submission:

```
GET /api/workbenches/{slug}/objects/{{oid}}/responses?since_version=N
```

- Cadence: 2–5s while actively waiting.
- Back off to 30s after a few minutes idle.
- A `submit` event bumps `state_version` on the object; an `autosave` does not.
- v1 returns immediately. The endpoint is shaped so a future long-poll/SSE upgrade is non-breaking.

Convenience reads:

- `GET .../responses/latest` — full ResponseEvent wrapper (version, kind, submitted_at, payload).
- `GET .../responses/latest/payload` — **just the JSON payload**, raw, same shape the user sees in
  the doc's "Export JSON" button. This is what most agents want.
- `GET .../responses/export` — full history as a downloadable JSON file (Content-Disposition).
  Useful for archiving / handing back to the user.

## Authoring objects — common gotchas

**`mime` must match `kind` or the iframe won't render.** `GET /content`
serves with `Content-Type: <meta.mime>`. Octet-stream → no render.

```
html | approval-html | qa-form  →  text/html
md                              →  text/markdown
runbook                         →  application/json
image                           →  image/png  (actual type)
```

**`PUT /content` body is RAW BYTES, never a JSON wrapper.** Don't PUT
`{{"content": "<html>..."}}` — that string gets stored verbatim and the
iframe loads JSON. Send the literal content with the matching Content-Type.
The optional `content` field in POST /objects examples IS unwrapped
server-side; that's the only place the envelope works.

**When unsure, check `/openapi.json`** — every authoring endpoint ships
an example body.

## File transfer (both directions)

- Upload (you → user): `POST /api/workbenches/{slug}/objects` multipart with `meta` JSON part
  (`kind: "file"` or `"image"`, `title`, `drawer`, **correct `mime`**) and `file` part. Returns
  the object's `id`.
- Download (you ← user): `GET .../objects/{{oid}}/content` returns raw bytes with the right
  `Content-Type`. Use `If-None-Match: <etag>` for cheap revalidation.

The user can drop or paste images directly into the in-browser MD/HTML editor — those become
real `kind: image` objects. Don't be surprised if image objects you didn't create appear during
a session.

## Runbook objects (long-running task tracking)

`kind: runbook` persists a structured task list across sessions — the agent's project plan that
the user can tick/untick from the browser. Content is JSON:

```
{
  "title": "Comms module rollout",
  "description": "Multi-session tracker.",
  "steps": [
    {{"id": "s1", "title": "Wire WebSocket primitive", "status": "done",
     "started_at": "...", "completed_at": "..."}},
    {{"id": "s2", "title": "Per-titan keys", "status": "todo"}},
    {{"id": "s3", "title": "Ship to staging", "status": "blocked",
     "blocker": "Tailscale ACL"}}
  ]
}
```

`status` ∈ `todo | in-progress | done | blocked`. Read with `GET .../content` (returns parsed
JSON), write with `PUT .../content` (full-body replace). Recommended workflow: at session
start, GET the runbook to see what's `todo`/`blocked`; advance step status as you complete
work; PUT the updated runbook back. The user sees their checkbox UI auto-update.

## Pinning + archiving objects

Objects support `pinned: bool` (sticks to top of its drawer) and `archived: bool` (hidden from
default lists, recoverable). Set via `PATCH .../objects/{{oid}}` body `{{pinned, archived}}`.
Default `list_objects` excludes archived; pass `?include_archived=true` if you need the full
inventory.

## Snapshots, audit log, static export

For long-running workbenches, three operational endpoints worth knowing:

- `POST /api/workbenches/{{slug}}/snapshot` body `{{label}}` — labelled tar.gz checkpoint.
  `GET /snapshots`, `GET /snapshots/{{name}}/download`,
  `POST /snapshots/{{name}}/restore` body `{{new_slug}}`,
  `DELETE /snapshots/{{name}}`. Use before risky multi-file rewrites.
- `GET /api/workbenches/{{slug}}/audit[?since=&until=&download=true]` — chronological log of
  content-level mutations: object create/update/delete, content writes, theme writes, response
  appends. Useful for "what happened in this workbench?" reproducibility.
- `GET /api/workbenches/{{slug}}/static-export` — self-contained zip of the workbench (rendered
  MD, themed approval HTML, images, files, theme CSS, index page). Hosts on any static host;
  does not require Arctic Base running. Good for archival.

## Self-test

`POST /api/agent/self-test` runs a synthetic round-trip (create temp workbench → object →
content write → submit → read back → cleanup) and returns `{{pass, steps[name, ok, elapsed_ms,
detail], total_ms}}`. Call this at session start to confirm the workbench loop works before
you commit to a real task — much cheaper than discovering 20 minutes in.

## Editing files concurrently with the user

If you write to `objects/{{oid}}/content` while the user has the file open in the UI editor, the
editor will detect the change on save (ETag stale-check, returns 412) and prompt the user. Your
agent writes do NOT need to send `If-Match` — last-write-wins is fine for agent-side updates.

## HTML templates (start here when authoring approval/Q&A/pitch HTML)

Don't hand-write a doc from scratch. Hit:

- `GET /api/agent/templates` — lists templates with `id`, `suggested_kind`, `when_to_use`.
- `GET /api/agent/templates/{id}` — returns the raw HTML. Add `?fill_title=<your title>` to
  pre-fill `{{TITLE}}`, `{{SUBTITLE}}`, and `{{STATE_KEY}}`; otherwise you replace those yourself.

Templates are self-contained, reference `--wb-*` CSS variables (so they auto-theme when served
via Arctic Base), include `window.workbench` integration with `localStorage` fallback, and have
JSON export. Available templates: `approval-questions` (multi-question decision doc),
`qa-form` (short ad-hoc form), `pitch` (narrative + Approve/Defer/Reject footer), and
`runbook` (JSON content for the runbook kind — structured persistent task list).

Workflow: pick a template → fetch → edit the marked region (a clearly-labelled `QS` array or
`<section>` block) → upload via `POST /api/workbenches/{slug}/objects` (multipart, kind set per
the template's `suggested_kind`). Don't bloat the template with extra dependencies — keep it
self-contained.

## Memory snippet

Hit `GET /api/agent/claude-md-snippet?slug=...&format=claude` (or `format=agents`) for a
copy-paste fragment to drop into the project's `CLAUDE.md` / `AGENTS.md`. The snippet captures
the workbench slug + the minimal-context rules above so future sessions auto-discover the
workbench without re-reading this whole doc.

## Recommended workflow (terse)

1. Bootstrap the workbench (`POST /api/agent/bootstrap`).
2. Walk the user through the returned checklist, one item at a time.
3. For approval/pitch decisions: author a self-contained HTML, upload as `kind=approval-html`,
   point the user at the URL, poll responses.
4. For quick yes/no: same, `kind=qa-form`, simpler form.
5. For file/image exchange: use objects with `kind=file`/`image`.
6. For long docs: write MD, upload as `kind=md`. The user reads it themed.
7. Offer to drop the memory snippet into `CLAUDE.md`/`AGENTS.md`.
"""


@router.get("/conventions", response_class=PlainTextResponse, operation_id="agentConventions")
def conventions(_: Request) -> str:
    return CONVENTIONS_MD


# ---------- Bootstrap ----------


class BootstrapBody(BaseModel):
    project_title: str = Field(min_length=1)
    suggested_slug: str | None = None
    description: str = ""
    url: str | None = None
    local_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    banner: Banner | None = None


class BootstrapChecklistItem(BaseModel):
    id: str
    prompt: str
    one_line_intent: str


class BootstrapResponse(BaseModel):
    workbench: WorkbenchMeta
    workbench_url: str
    checklist: list[BootstrapChecklistItem]
    next_steps: list[str]


def _slugify(t: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in t)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:64] or "workbench"


@router.post(
    "/bootstrap",
    response_model=BootstrapResponse,
    operation_id="agentBootstrap",
    summary="One-shot create a workbench + get a checklist of follow-ups",
    description=(
        "Creates the workbench and returns a structured checklist of next steps "
        "(theme, banner, tags, memory snippet) plus a hand-to-human `workbench_url`. "
        "Read `/api/agent/conventions` first if you haven't — it covers the runtime "
        "contract every other endpoint depends on."
    ),
)
def bootstrap(
    body: Annotated[
        BootstrapBody,
        Body(
            openapi_examples={"default": {"value": {
                "project_title": "TaskyTrack",
                "suggested_slug": "taskytrack",
                "description": "Lightweight task tracker — trial of the persistent runbook + approval-html flow.",
                "url": "https://taskytrack.example.com",
                "local_path": "/Users/you/code/taskytrack",
                "tags": ["personal", "side-project", "v1"],
            }}},
        ),
    ],
    request: Request,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> BootstrapResponse:
    slug = body.suggested_slug or _slugify(body.project_title)
    now = datetime.now(UTC)
    meta = WorkbenchMeta(
        slug=slug,
        title=body.project_title,
        description=body.description,
        url=body.url,
        local_path=body.local_path,
        tags=body.tags,
        banner=body.banner,
        created_at=now,
        updated_at=now,
    )
    created = storage.create_workbench(meta)
    base = str(request.base_url).rstrip("/")
    return BootstrapResponse(
        workbench=created,
        workbench_url=f"{base}/wb/{created.slug}",
        checklist=[
            BootstrapChecklistItem(
                id="theme",
                prompt="Want to set up the workbench theme now, or later?",
                one_line_intent="If now: ask user for vibe/colors and PUT /api/workbenches/{slug}/theme.",
            ),
            BootstrapChecklistItem(
                id="banner",
                prompt="Want a banner image for the workbench? Upload or URL?",
                one_line_intent="If yes: upload via PUT /theme/assets/banner.png or set banner.url.",
            ),
            BootstrapChecklistItem(
                id="local_path",
                prompt="Confirm the local path to the project on your machine.",
                one_line_intent="Decorative — Arctic Base never reads/writes that path.",
            ),
            BootstrapChecklistItem(
                id="tags",
                prompt="Any tags for filtering? (e.g., 'webapp', 'personal', 'research').",
                one_line_intent="PATCH /api/workbenches/{slug} with tags.",
            ),
            BootstrapChecklistItem(
                id="memory_snippet",
                prompt="Want me to drop a CLAUDE.md/AGENTS.md fragment into the project so future sessions auto-discover this workbench?",
                one_line_intent="GET /api/agent/claude-md-snippet?slug={slug}&format=claude (or agents).",
            ),
        ],
        next_steps=[
            "Read /api/agent/conventions for the runtime contract (window.workbench, polling, theme tokens).",
            "Use approval-html objects for big decisions; qa-form for quick yes/no; md for review docs; file/image for transfers.",
            "Poll GET /api/workbenches/{slug}/objects/{{oid}}/responses?since_version=N for user submissions.",
            "Don't hand-write HTML from scratch — start from /api/agent/templates (list) + /api/agent/templates/{{id}} (body).",
        ],
    )


# ---------- Memory snippet ----------


SNIPPET_TEMPLATES = {
    "claude": """\
## Arctic Base workbench

This project has an Arctic Base workbench at:
- Slug: `{slug}`
- URL: `{base_url}/wb/{slug}`
- API base: `{base_url}/api/workbenches/{slug}`

When you need user input that doesn't fit a quick chat exchange, use Arctic Base.

**Start every HTML doc from a template — don't hand-write from scratch:**

1. `GET {base_url}/api/agent/templates` to list available templates
   (`approval-questions`, `qa-form`, `pitch`).
2. `GET {base_url}/api/agent/templates/{{template_id}}?fill_title=<title>` to fetch the body with
   `{{TITLE}}` / `{{STATE_KEY}}` pre-filled.
3. Edit the marked region (a labelled `QS` array or `<section>` block).
4. Upload as an object: `POST {base_url}/api/workbenches/{slug}/objects` with
   `kind = template's suggested_kind`.

Common patterns:

- **Big decisions / multi-question reviews** → `approval-questions` template → kind=approval-html.
- **Quick free-form Q&A** → `qa-form` template → kind=qa-form.
- **One narrative pitch with Approve/Defer/Reject** → `pitch` template → kind=approval-html.
- **Multi-session task plan** → `runbook` template → kind=runbook (JSON content; agent reads
  + writes via /content; user ticks checkboxes).
- **File/image transfer (either direction)** → kind=file / kind=image objects.
- **Long docs to review** → kind=md; the user reads themed.

Pin important objects with `PATCH .../objects/{{oid}}` body `{{pinned: true}}`; archive
finished/stale ones with `{{archived: true}}` (default lists hide them).

Poll `GET {base_url}/api/workbenches/{slug}/objects/{{oid}}/responses?since_version=N` (2–5s
cadence) for the user's submission.

Templates already include the right behaviour (feature-detect `window.workbench`, fall back to
`localStorage` + JSON export, reference `var(--wb-*)` so they auto-theme). Don't strip those.

Read `{base_url}/api/agent/conventions` once at session start for the full runtime contract. Hit
`{base_url}/openapi.json` for the API schema.
""",
    "agents": """\
## Arctic Base

Workbench: `{slug}` — `{base_url}/wb/{slug}`

API entry: `{base_url}/openapi.json`. Conventions: `{base_url}/api/agent/conventions`.
Templates: `{base_url}/api/agent/templates` (then `/{{id}}?fill_title=…` for the body).

Workflow: pick template → fetch body → edit marked region → upload via
`POST /api/workbenches/{slug}/objects` (kind = template's suggested_kind) → poll
`/responses?since_version=N`. Templates already wire `window.workbench`, `localStorage` fallback,
JSON export, and `var(--wb-*)` auto-theming. Don't hand-write HTML from scratch.
""",
}


# Generic snippets returned when no `slug` is given — useful for project memory
# files written before any workbench exists. Tells future agents where the
# instance is and how to discover it.
SNIPPET_TEMPLATES_GLOBAL = {
    "claude": """\
## Arctic Base instance

This project uses an Arctic Base instance at `{base_url}` for out-of-band agent
↔ user surfaces (decisions, file handoff, document review, async signaling).

Bootstrap a workbench when you start work:

1. `POST {base_url}/api/agent/bootstrap` with `{{"project_title": "..."}}` —
   returns the new workbench, a `workbench_url`, and a checklist.
2. Read `{base_url}/api/agent/conventions` for the runtime contract
   (window.workbench bridge, polling, theme tokens, templates-first rule).
3. List existing workbenches: `GET {base_url}/api/workbenches`.

Hand the user `view_url` from any workbench response so they know where to look.
""",
    "agents": """\
## Arctic Base

Instance: `{base_url}`. Bootstrap a workbench: `POST /api/agent/bootstrap`.
Conventions: `{base_url}/api/agent/conventions`. Schema: `{base_url}/openapi.json`.
""",
}


# ---------- Self-test ----------


class SelfTestStep(BaseModel):
    name: str
    ok: bool
    elapsed_ms: float
    detail: str = ""


class SelfTestResult(BaseModel):
    pass_: bool = Field(alias="pass")
    steps: list[SelfTestStep]
    total_ms: float

    model_config = {"populate_by_name": True}


@router.post("/self-test", response_model=SelfTestResult, operation_id="agentSelfTest")
def self_test(
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> SelfTestResult:
    """Synthetic round-trip: create temp workbench → object → write → respond → read → cleanup.

    Each step is timed. Returns pass/fail per step. An agent can call this at session start to
    confirm the workbench loop works end-to-end before doing real work.
    """

    import time
    from datetime import UTC, datetime
    from arctic_base.models import (
        ObjectKind,
        ObjectMeta,
        ResponseEvent,
        ResponseKind,
        Submitter,
        WorkbenchMeta,
    )
    from arctic_base.storage.filesystem import new_object_id

    steps: list[SelfTestStep] = []
    total_start = time.perf_counter()
    slug = f"selftest-{int(time.time() * 1000)}"
    oid: str | None = None

    def step(name: str, fn) -> bool:
        t0 = time.perf_counter()
        try:
            fn()
            elapsed = (time.perf_counter() - t0) * 1000
            steps.append(SelfTestStep(name=name, ok=True, elapsed_ms=round(elapsed, 2)))
            return True
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            steps.append(
                SelfTestStep(name=name, ok=False, elapsed_ms=round(elapsed, 2), detail=str(e))
            )
            return False

    def s_create_workbench():
        now = datetime.now(UTC)
        storage.create_workbench(
            WorkbenchMeta(slug=slug, title="self-test", created_at=now, updated_at=now)
        )

    def s_create_object():
        nonlocal oid
        now = datetime.now(UTC)
        oid = new_object_id()
        storage.create_object(
            slug,
            ObjectMeta(
                id=oid, kind=ObjectKind.md, title="ping", created_at=now, updated_at=now,
            ),
            content=b"# ping\n",
        )

    def s_write_content():
        assert oid is not None
        storage.put_object_content(slug, oid, b"# ping\n\nhello\n")

    def s_append_response():
        assert oid is not None
        storage.append_response(
            slug,
            oid,
            ResponseEvent(
                version=0,
                object_id=oid,
                submitted_at=datetime.now(UTC),
                submitted_by=Submitter.system,
                kind=ResponseKind.submit,
                payload={"answer": "pong"},
            ),
        )

    def s_read_back():
        assert oid is not None
        latest = storage.get_latest_response(slug, oid)
        if not latest or latest.payload.get("answer") != "pong":
            raise RuntimeError("payload round-trip mismatch")

    def s_cleanup():
        archive = storage.archive_workbench(slug)
        # Purge the trash entry too so we don't leave behind self-test debris.
        storage.purge_trash(archive)

    ok = True
    ok = step("create_workbench", s_create_workbench) and ok
    if ok:
        ok = step("create_object", s_create_object) and ok
    if ok:
        ok = step("write_content", s_write_content) and ok
    if ok:
        ok = step("append_response", s_append_response) and ok
    if ok:
        ok = step("read_back", s_read_back) and ok
    # Always try cleanup, regardless.
    step("cleanup", s_cleanup)

    total = (time.perf_counter() - total_start) * 1000
    overall_pass = all(s.ok for s in steps)
    return SelfTestResult.model_validate(
        {"pass": overall_pass, "steps": [s.model_dump() for s in steps], "total_ms": round(total, 2)}
    )


# ---------- Activity timeline ----------


class ActivityResponse(BaseModel):
    events: list[dict]


@router.get("/activity", response_model=ActivityResponse, operation_id="agentActivity")
def activity(limit: int = 100, agent_only: bool = True) -> ActivityResponse:
    """Recent API requests, newest-first. Used by the Settings activity timeline.

    Defaults to agent-only (skips SPA asset/index serves) and the last 100.
    """

    return ActivityResponse(events=list(get_recent_activity(limit=limit, agent_only=agent_only)))


# ---------- Templates ----------


class TemplateListResponse(BaseModel):
    templates: list[dict]


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    operation_id="agentListTemplates",
)
def list_html_templates() -> TemplateListResponse:
    """List available starter HTML templates with metadata.

    Agents pick a template by `suggested_kind` and `when_to_use`, then GET the body via
    `/api/agent/templates/{id}`. Templates are self-contained, reference `--wb-*` CSS variables for
    auto-theming, and integrate `window.workbench` with localStorage fallback.
    """

    return TemplateListResponse(templates=[dict(t) for t in _list_templates()])


@router.get(
    "/templates/{template_id}",
    response_class=PlainTextResponse,
    operation_id="agentGetTemplate",
)
def get_html_template(template_id: str, fill_title: str | None = None) -> str:
    """Return the raw HTML body of a template.

    Optional `fill_title` query param substitutes `{{TITLE}}` and `{{SUBTITLE}}` placeholders, plus
    derives a `{{STATE_KEY}}` from the title. Otherwise placeholders are left in the output for the
    agent to substitute before upload.
    """

    found = _get_template(template_id)
    if found is None:
        raise NotFound(f"template {template_id!r} not found")
    _, body = found
    if fill_title:
        slug_key = "".join(c.lower() if c.isalnum() else "-" for c in fill_title).strip("-")[:60]
        return (
            body
            .replace("{{TITLE}}", fill_title)
            .replace("{{SUBTITLE}}", "")
            .replace("{{STATE_KEY}}", f"ab-{slug_key or 'doc'}-v1")
        )
    return body


@router.get(
    "/claude-md-snippet",
    response_class=PlainTextResponse,
    operation_id="agentMemorySnippet",
    summary="CLAUDE.md / AGENTS.md memory snippet",
    description=(
        "Paste-ready memory snippet. With `slug`, returns a workbench-specific "
        "snippet that names the workbench and its URL. Without `slug`, returns a "
        "generic snippet that points future agents at this Arctic Base instance "
        "(useful before any specific workbench exists)."
    ),
)
def memory_snippet(
    request: Request,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    slug: str | None = None,
    format: Literal["claude", "agents"] = "claude",
) -> str:
    base_url = str(request.base_url).rstrip("/")
    if slug is None:
        return SNIPPET_TEMPLATES_GLOBAL[format].format(base_url=base_url)
    storage.get_workbench(slug)  # raises NotFound if missing
    return SNIPPET_TEMPLATES[format].format(slug=slug, base_url=base_url)
