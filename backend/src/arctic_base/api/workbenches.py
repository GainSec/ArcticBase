import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arctic_base.api.deps import get_storage
from arctic_base.models import Banner, WorkbenchMeta
from arctic_base.storage.filesystem import FilesystemStorage

router = APIRouter(prefix="/workbenches", tags=["workbenches"])


class WorkbenchCreate(BaseModel):
    title: str
    slug: str | None = None
    description: str = ""
    url: str | None = None
    ip: str | None = None
    local_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    banner: Banner | None = None
    custom_fields: dict[str, str] = Field(default_factory=dict)


class WorkbenchPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    ip: str | None = None
    local_path: str | None = None
    tags: list[str] | None = None
    banner: Banner | None = None
    custom_fields: dict[str, str] | None = None


def _slugify(title: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in title)
    while "--" in out:
        out = out.replace("--", "-")
    out = out.strip("-")
    return out[:64] or "workbench"


@router.get("", response_model=list[WorkbenchMeta], operation_id="listWorkbenches")
def list_workbenches(
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> list[WorkbenchMeta]:
    return storage.list_workbenches()


@router.post("", response_model=WorkbenchMeta, status_code=201, operation_id="createWorkbench")
def create_workbench(
    body: WorkbenchCreate,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> WorkbenchMeta:
    slug = body.slug or _slugify(body.title)
    now = datetime.now(UTC)
    meta = WorkbenchMeta(
        slug=slug,
        title=body.title,
        description=body.description,
        url=body.url,
        ip=body.ip,
        local_path=body.local_path,
        tags=body.tags,
        banner=body.banner,
        custom_fields=body.custom_fields,
        created_at=now,
        updated_at=now,
    )
    created = storage.create_workbench(meta)
    # Bootstrap a default theme so the workbench is browsable immediately. Agents that want their
    # own theme can PUT one any time after.
    try:
        storage.put_theme(slug, _DEFAULT_THEME_MD)
    except Exception:
        # Don't fail workbench creation if the default theme can't be written.
        pass
    return created


_DEFAULT_THEME_MD = """\
---
name: Arctic Default
core:
  bg: '#0e1322'
  surface: '#171d2e'
  ink: '#e8eaf2'
  muted: '#8b91a8'
  rule: '#22293a'
  accent: '#5ed1ff'
  accent-2: '#9cf17e'
  success: '#7be07b'
  error: '#ff7470'
typography:
  body: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif', fontSize: '15px', fontWeight: '500', lineHeight: '1.55' }
  mono: { fontFamily: 'JetBrains Mono, ui-monospace, monospace', fontSize: '13px', fontWeight: '500', lineHeight: '1.4' }
rounded: { sm: '0.25rem', md: '0.375rem', lg: '0.5rem' }
spacing: { unit: '8px', gutter: '20px', margin: '28px' }
custom: {}
layout:
  density: comfortable
  corners: rounded
  shadow: soft
  card-style: floating
  motif: none
  banner-shape: rect
  hero-style: cover
---

# Arctic Default

Sane out-of-the-box theme. Cool slate background, sky-blue accent, mint highlight. Replace via PUT
/api/workbenches/{slug}/theme to make it your own.
"""


@router.get("/{slug}", response_model=WorkbenchMeta, operation_id="getWorkbench")
def get_workbench(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> WorkbenchMeta:
    # Touch first so the response reflects the current last_accessed_at.
    try:
        storage.touch_workbench(slug)
    except Exception:
        pass
    return storage.get_workbench(slug)


class WorkbenchReorderBody(BaseModel):
    slugs: list[str]


@router.post("/_reorder", status_code=204, operation_id="reorderWorkbenches")
def reorder_workbenches(
    body: WorkbenchReorderBody,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    if body.slugs:
        storage.set_workbench_order(body.slugs)
    else:
        storage.clear_workbench_order()
    return Response(status_code=204)


@router.patch(
    "/{slug}",
    response_model=WorkbenchMeta,
    operation_id="patchWorkbench",
    summary="Update mutable workbench fields",
    description=(
        "Patch any subset of: `title`, `description`, `url`, `ip`, `local_path`, "
        "`tags`, `banner`, `custom_fields`. The `custom_fields` map is free-form "
        "(string→string) — agents can set things like `deploy_cmd`, `ci_url`, "
        "`secrets_path` and read them back later."
    ),
)
def patch_workbench(
    slug: str,
    body: Annotated[
        WorkbenchPatch,
        Body(
            openapi_examples={"default": {"value": {
                "description": "Test workbench for the Arctic-Base agent round-trip.",
                "url": "https://example.com",
                "ip": "192.168.13.37",
                "local_path": "/home/you/code/project",
                "tags": ["test", "pilot"],
                "custom_fields": {
                    "deploy_cmd": "./deploy.sh",
                    "ci_url": "https://ci.example/sectortest",
                    "secrets_path": "/home/you/.config/sectortest",
                },
            }}},
        ),
    ],
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> WorkbenchMeta:
    patch = body.model_dump(exclude_unset=True)
    return storage.update_workbench(slug, patch)


class ArchiveResponse(BaseModel):
    archive: str


@router.delete("/{slug}", response_model=ArchiveResponse, operation_id="archiveWorkbench")
def archive_workbench(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ArchiveResponse:
    return ArchiveResponse(archive=storage.archive_workbench(slug))


class TrashEntry(BaseModel):
    archive: str


@router.get("/_trash/list", response_model=list[TrashEntry], operation_id="listTrash")
def list_trash(
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> list[TrashEntry]:
    return [TrashEntry(archive=name) for name in storage.list_trash()]


class RestoreBody(BaseModel):
    archive: str


class RestoreResponse(BaseModel):
    slug: str


@router.post("/_trash/restore", response_model=RestoreResponse, operation_id="restoreWorkbench")
def restore_workbench(
    body: RestoreBody,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> RestoreResponse:
    return RestoreResponse(slug=storage.restore_workbench(body.archive))


@router.get("/_trash/{archive}/download", operation_id="downloadTrashArchive")
def download_trash(
    archive: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    data = storage.get_trash_archive(archive)
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"content-disposition": f'attachment; filename="{archive}"'},
    )


@router.delete("/_trash/{archive}", status_code=204, operation_id="purgeTrashArchive")
def purge_trash(
    archive: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    storage.purge_trash(archive)
    return Response(status_code=204)


class DuplicateBody(BaseModel):
    new_slug: str | None = None


@router.post("/{slug}/duplicate", response_model=WorkbenchMeta, status_code=201, operation_id="duplicateWorkbench")
def duplicate_workbench(
    slug: str,
    body: DuplicateBody,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> WorkbenchMeta:
    new_slug = body.new_slug or _unique_slug(slug, storage)
    return storage.duplicate_workbench(slug, new_slug)


def _unique_slug(base: str, storage) -> str:
    existing = {w.slug for w in storage.list_workbenches()}
    candidate = f"{base}-copy"
    if candidate not in existing:
        return candidate
    i = 2
    while f"{candidate}-{i}" in existing:
        i += 1
    return f"{candidate}-{i}"


@router.get("/{slug}/export", operation_id="exportWorkbench")
def export_workbench(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    data, filename = storage.export_workbench(slug)
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Snapshots ----------


class SnapshotMeta(BaseModel):
    name: str
    label: str = ""
    size_bytes: int
    created_at: str


class SnapshotCreate(BaseModel):
    label: str = "snapshot"


@router.post(
    "/{slug}/snapshot",
    response_model=SnapshotMeta,
    status_code=201,
    operation_id="createSnapshot",
)
def create_snapshot(
    slug: str,
    body: SnapshotCreate,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> SnapshotMeta:
    return SnapshotMeta(**storage.snapshot_workbench(slug, body.label))


@router.get(
    "/{slug}/snapshots",
    response_model=list[SnapshotMeta],
    operation_id="listSnapshots",
)
def list_snapshots(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> list[SnapshotMeta]:
    return [SnapshotMeta(**s) for s in storage.list_snapshots(slug)]


@router.get(
    "/{slug}/snapshots/{name}/download",
    operation_id="downloadSnapshot",
)
def download_snapshot(
    slug: str,
    name: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    data = storage.get_snapshot_bytes(slug, name)
    return Response(
        content=data,
        media_type="application/gzip",
        headers={"content-disposition": f'attachment; filename="{name}"'},
    )


class SnapshotRestoreBody(BaseModel):
    new_slug: str


@router.post(
    "/{slug}/snapshots/{name}/restore",
    response_model=WorkbenchMeta,
    operation_id="restoreSnapshot",
)
def restore_snapshot(
    slug: str,
    name: str,
    body: SnapshotRestoreBody,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> WorkbenchMeta:
    new_slug = storage.restore_snapshot(slug, name, body.new_slug)
    return storage.get_workbench(new_slug)


@router.delete(
    "/{slug}/snapshots/{name}",
    status_code=204,
    operation_id="deleteSnapshot",
)
def delete_snapshot(
    slug: str,
    name: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    storage.delete_snapshot(slug, name)
    return Response(status_code=204)


# ---------- Audit log ----------


@router.get("/{slug}/audit", operation_id="auditLog")
def audit_log(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    since: str | None = None,
    until: str | None = None,
    download: bool = False,
) -> Response:
    storage.get_workbench(slug)  # 404 if missing
    events = storage.read_audit(slug, since=since, until=until)
    if download:
        body = "\n".join(json.dumps(e, default=str) for e in events) + "\n"
        return Response(
            content=body,
            media_type="application/x-ndjson",
            headers={"content-disposition": f'attachment; filename="{slug}-audit.jsonl"'},
        )
    return Response(
        content=json.dumps({"slug": slug, "events": events}, indent=2),
        media_type="application/json",
    )


# ---------- Static export ----------


@router.get("/{slug}/static-export", operation_id="staticExport")
def static_export(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    """Build a self-contained static-site zip of a workbench (no API dependency)."""
    import io as _io
    import zipfile

    from arctic_base.api.render import build_theme_style_block

    wb = storage.get_workbench(slug)
    objects = storage.list_objects(slug, include_archived=True)
    try:
        theme = storage.get_theme(slug)
        theme_style = build_theme_style_block(theme)
    except Exception:
        theme = None
        theme_style = ""

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Manifest
        zf.writestr(f"{slug}/manifest.json", wb.model_dump_json(indent=2))
        # CSS
        zf.writestr(
            f"{slug}/style.css",
            "/* Generated theme tokens */\n"
            + (theme_style.replace("<style data-arctic-base=\"theme\">", "")
                .replace("</style>", "")
               if theme_style else ""),
        )

        # Index: list of objects with links
        index_links: list[str] = []
        for o in objects:
            link_target = ""
            if o.kind.value == "md":
                link_target = f"md/{o.id}.html"
            elif o.kind.value in ("html", "approval-html", "qa-form"):
                link_target = f"html/{o.id}.html"
            elif o.kind.value == "image":
                ext = (o.filename.rsplit(".", 1)[-1] or "bin") if o.filename else "bin"
                link_target = f"images/{o.id}.{ext}"
            elif o.kind.value == "runbook":
                link_target = f"runbooks/{o.id}.json"
            else:
                fname = o.filename or f"{o.id}.bin"
                link_target = f"files/{o.id}/{fname}"
            tags = (
                f' <small>· {", ".join(o.tags) if hasattr(o, "tags") and o.tags else ""}</small>'
            )
            archived = " [archived]" if o.archived else ""
            pinned = "📌 " if o.pinned else ""
            index_links.append(
                f'<li><span class="kind">{o.kind.value}</span> {pinned}'
                f'<a href="{link_target}">{o.title or o.filename or o.id}</a>{archived}{tags}</li>'
            )

        index_html = (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{wb.title} — Arctic Base static export</title>"
            "<link rel=\"stylesheet\" href=\"style.css\">"
            "<style>"
            "body{font-family:var(--wb-font-body,system-ui);background:var(--wb-bg,#fff);"
            "color:var(--wb-ink,#111);margin:0;padding:2rem;max-width:920px;margin:0 auto;}"
            "h1{font-family:var(--wb-font-headline-md,inherit);}"
            ".meta{color:var(--wb-muted,#666);font-size:.9em;margin-bottom:1.5rem;}"
            ".meta .kv{margin-right:1rem;}"
            ".meta b{color:var(--wb-accent);font-size:.7em;letter-spacing:.1em;text-transform:uppercase;}"
            "ul{list-style:none;padding:0;}"
            "li{padding:.6rem .8rem;background:var(--wb-surface,#f5f5f5);border:1px solid var(--wb-rule,#ddd);border-radius:4px;margin-bottom:.4rem;}"
            ".kind{display:inline-block;font-family:var(--wb-font-mono,monospace);font-size:.7em;letter-spacing:.06em;text-transform:uppercase;padding:.1em .5em;background:var(--wb-bg);border:1px solid var(--wb-rule);border-radius:2px;margin-right:.6rem;color:var(--wb-muted);}"
            "a{color:var(--wb-accent);}"
            "</style></head><body>"
            f"<h1>{wb.title}</h1>"
            f"<p>{wb.description}</p>"
            "<div class=\"meta\">"
            + (f'<span class="kv"><b>URL</b> <a href="{wb.url}">{wb.url}</a></span>' if wb.url else "")
            + (f'<span class="kv"><b>IP</b> <code>{wb.ip}</code></span>' if wb.ip else "")
            + (f'<span class="kv"><b>PATH</b> <code>{wb.local_path}</code></span>' if wb.local_path else "")
            + "</div>"
            f"<h2>Objects ({len(objects)})</h2>"
            f"<ul>{''.join(index_links)}</ul>"
            "<footer style=\"margin-top:3rem;padding-top:1rem;border-top:1px solid var(--wb-rule,#ddd);"
            "color:var(--wb-muted,#666);font-size:.8em;\">"
            f"// Static export of <code>{slug}</code> from Arctic Base"
            "</footer>"
            "</body></html>"
        )
        zf.writestr(f"{slug}/index.html", index_html)

        # Per-object content
        for o in objects:
            try:
                content, _ = storage.get_object_content(slug, o.id)
            except Exception:
                content = b""
            if o.kind.value == "md":
                from markdown_it import MarkdownIt
                try:
                    from mdit_py_plugins.tasklists import tasklists_plugin
                    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(
                        ["table", "strikethrough"]
                    ).use(tasklists_plugin)
                except Exception:
                    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(
                        ["table", "strikethrough"]
                    )
                rendered = md.render(content.decode("utf-8", errors="replace"))
                page = (
                    "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
                    f"<title>{o.title}</title>"
                    "<link rel=\"stylesheet\" href=\"../style.css\">"
                    "<style>body{font-family:var(--wb-font-body,system-ui);background:var(--wb-bg);"
                    "color:var(--wb-ink);margin:0;padding:2rem;max-width:760px;margin:0 auto;}"
                    "code,pre{font-family:var(--wb-font-mono);}"
                    "a{color:var(--wb-accent);}</style></head><body>"
                    f"{rendered}"
                    "<hr><a href=\"../index.html\">← back to index</a>"
                    "</body></html>"
                )
                zf.writestr(f"{slug}/md/{o.id}.html", page)
            elif o.kind.value in ("html", "approval-html", "qa-form"):
                # Inject theme + a "back to index" footer.
                text = content.decode("utf-8", errors="replace")
                injection = theme_style + (
                    "<style>body::after{content:\"← back to index\";"
                    "display:block;text-align:center;padding:1rem;}</style>"
                )
                lower = text.lower()
                head_end = lower.find("</head>")
                if head_end != -1:
                    text = text[:head_end] + injection + text[head_end:]
                else:
                    text = injection + text
                zf.writestr(f"{slug}/html/{o.id}.html", text)
            elif o.kind.value == "image":
                ext = (o.filename.rsplit(".", 1)[-1] or "bin") if o.filename else "bin"
                zf.writestr(f"{slug}/images/{o.id}.{ext}", content)
            elif o.kind.value == "runbook":
                zf.writestr(f"{slug}/runbooks/{o.id}.json", content)
            else:
                fname = o.filename or f"{o.id}.bin"
                zf.writestr(f"{slug}/files/{o.id}/{fname}", content)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "content-disposition": f'attachment; filename="{slug}-static.zip"',
        },
    )


@router.get("/{slug}/banner", operation_id="getWorkbenchBanner")
def get_workbench_banner(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    """Return the workbench banner. If `banner` is null, generate an SVG from theme tokens.

    For `kind: upload`, redirects to the theme asset. For `kind: url`, returns a 302 redirect.
    """

    wb = storage.get_workbench(slug)
    if wb.banner:
        if wb.banner.kind.value == "upload":
            asset_path = wb.banner.ref.removeprefix("theme/")
            data, _ = storage.get_theme_asset(slug, asset_path)
            return Response(content=data, media_type="image/png")
        # url — let the browser follow.
        return Response(
            status_code=302,
            headers={"location": wb.banner.ref},
        )
    # Generate an SVG from theme tokens.
    try:
        theme = storage.get_theme(slug)
        bg = theme.tokens.core.get("bg", "#0e1322")
        accent = theme.tokens.core.get("accent", "#5ed1ff")
        accent2 = theme.tokens.core.get("accent-2", "#9cf17e")
        ink = theme.tokens.core.get("ink", "#e8eaf2")
    except Exception:
        bg, accent, accent2, ink = "#0e1322", "#5ed1ff", "#9cf17e", "#e8eaf2"
    title = wb.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 400" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{accent}" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="{accent2}" stop-opacity="0.15"/>
    </linearGradient>
    <pattern id="p" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M0 40 L40 0" stroke="{ink}" stroke-opacity="0.05" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="1280" height="400" fill="{bg}"/>
  <rect width="1280" height="400" fill="url(#g)"/>
  <rect width="1280" height="400" fill="url(#p)"/>
  <text x="640" y="220" text-anchor="middle" font-family="Black Ops One, Bungee, Impact, sans-serif" font-size="120" fill="{ink}" font-weight="700" letter-spacing="-2">{title.upper()}</text>
  <text x="640" y="290" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="22" fill="{accent}" letter-spacing="6">// SECTOR_{wb.slug.upper()}</text>
</svg>"""
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")
