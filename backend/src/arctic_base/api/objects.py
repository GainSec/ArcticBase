from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile
from pydantic import BaseModel, Field

from arctic_base.api.deps import get_storage
from arctic_base.config import get_settings
from arctic_base.models import ObjectKind, ObjectMeta
from arctic_base.storage.filesystem import FilesystemStorage, new_object_id

router = APIRouter(prefix="/workbenches/{slug}/objects", tags=["objects"])


class ObjectCreate(BaseModel):
    kind: ObjectKind
    title: str
    description: str = ""
    drawer: str = ""
    filename: str = ""
    mime: str = "application/octet-stream"
    # Optional inline content for one-shot create. UTF-8 string only — for binary
    # (image/file), use the multipart shape with a `file` part instead.
    content: str | None = None


class ObjectPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    drawer: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


@router.get("", response_model=list[ObjectMeta], operation_id="listObjects")
def list_objects(
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    kind: str | None = None,
    drawer: str | None = None,
    include_archived: bool = False,
) -> list[ObjectMeta]:
    return storage.list_objects(slug, kind=kind, drawer=drawer, include_archived=include_archived)


@router.post(
    "",
    response_model=ObjectMeta,
    status_code=201,
    operation_id="createObject",
    summary="Create an object inside a workbench",
    description=(
        "Accepts either pure JSON body (meta + optional inline `content`) or "
        "multipart with a `meta` JSON part and a `file` part. "
        "**Set `mime` to match the `kind`** — `text/html` for html / "
        "approval-html / qa-form, `text/markdown` for md, `application/json` "
        "for runbook. Octet-stream on a renderable kind means the iframe "
        "won't render.\n\n"
        "**Don't hand-write HTML from scratch** — start from `/api/agent/templates`. "
        "See `/api/agent/conventions` for the templates-first authoring rule, kind "
        "semantics (md / html / approval-html / qa-form / runbook / image / file), and "
        "the `window.workbench` runtime contract review-HTML must feature-detect."
    ),
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["kind", "title"],
                        "properties": {
                            "kind": {"type": "string", "enum": [k.value for k in ObjectKind]},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "drawer": {"type": "string"},
                            "filename": {"type": "string"},
                            "mime": {"type": "string"},
                            "content": {"type": "string", "description": "Raw text/HTML/JSON content for the object."},
                        },
                    },
                    "examples": {
                        "md": {
                            "summary": "Markdown doc (no separate content upload)",
                            "value": {
                                "kind": "md",
                                "title": "Field notes (agent scratchpad)",
                                "description": "Short ongoing log of decisions and unknowns.",
                                "drawer": "docs",
                                "filename": "FIELD-NOTES.md",
                                "content": "# Field Notes\n\n- [x] Read /api/agent/conventions\n- [ ] Wire WebSocket prototype\n",
                            },
                        },
                        "approvalHtml": {
                            "summary": "Agent-uploaded approval form (template-derived)",
                            "value": {
                                "kind": "approval-html",
                                "title": "Comms Module — Decisions",
                                "description": "Five questions for the comms-module rollout.",
                                "drawer": "approvals",
                                "filename": "COMMS-DECISIONS.html",
                                "mime": "text/html",
                                "content": "<!DOCTYPE html><html><head>...template-shaped HTML referencing var(--wb-*)...</head><body>...</body></html>",
                            },
                        },
                    },
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["meta", "file"],
                        "properties": {
                            "meta": {
                                "type": "string",
                                "description": "JSON-stringified ObjectMeta (kind, title, drawer, filename, mime).",
                            },
                            "file": {"type": "string", "format": "binary"},
                        },
                    },
                },
            },
        },
    },
)
async def create_object(
    request: Request,
    slug: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ObjectMeta:
    """Create an object. Accepts either pure JSON body (no content) or multipart with `meta` JSON
    part and a `file` part for content."""

    settings = get_settings()
    content_type = (request.headers.get("content-type") or "").lower()
    now = datetime.now(UTC)
    if content_type.startswith("multipart/"):
        form = await request.form()
        meta_json = form.get("meta")
        file_part = form.get("file")
        if meta_json is None:
            raise HTTPException(status_code=400, detail="missing 'meta' field in multipart")
        body = ObjectCreate.model_validate_json(str(meta_json))
        content_bytes: bytes | None = None
        if file_part is not None and isinstance(file_part, UploadFile):
            content_bytes = await file_part.read()
            if len(content_bytes) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail="upload exceeds size cap")
            if not body.filename:
                body.filename = file_part.filename or ""
            if file_part.content_type and body.mime == "application/octet-stream":
                body.mime = file_part.content_type
        meta = ObjectMeta(
            id=new_object_id(),
            kind=body.kind,
            title=body.title,
            description=body.description,
            drawer=body.drawer,
            filename=body.filename,
            mime=body.mime,
            created_at=now,
            updated_at=now,
        )
        return storage.create_object(slug, meta, content=content_bytes)

    # JSON path: meta + optional inline `content` (UTF-8 string only).
    body = ObjectCreate.model_validate(await request.json())
    meta = ObjectMeta(
        id=new_object_id(),
        kind=body.kind,
        title=body.title,
        description=body.description,
        drawer=body.drawer,
        filename=body.filename,
        mime=body.mime,
        created_at=now,
        updated_at=now,
    )
    content_bytes = body.content.encode("utf-8") if body.content is not None else None
    return storage.create_object(slug, meta, content=content_bytes)


@router.get("/{oid}", response_model=ObjectMeta, operation_id="getObject")
def get_object(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ObjectMeta:
    meta = storage.get_object(slug, oid)
    try:
        storage.touch_object(slug, oid)
    except Exception:
        pass
    return meta


class ObjectReorderBody(BaseModel):
    ids: list[str]


@router.post("/_reorder", status_code=204, operation_id="reorderObjects")
def reorder_objects(
    slug: str,
    body: ObjectReorderBody,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    storage.reorder_objects(slug, body.ids)
    return Response(status_code=204)


@router.patch(
    "/{oid}",
    response_model=ObjectMeta,
    operation_id="patchObject",
    summary="Update an object's mutable metadata",
    description=(
        "Updates any subset of `title`, `description`, `drawer`, `pinned`, "
        "`archived`. To replace content (raw bytes), use "
        "`PUT /api/workbenches/{slug}/objects/{oid}/content`."
    ),
)
def patch_object(
    slug: str,
    oid: str,
    body: Annotated[
        ObjectPatch,
        Body(
            openapi_examples={"default": {"value": {
                "title": "Comms Module — Decisions (FINAL)",
                "drawer": "archive",
                "pinned": False,
                "archived": True,
            }}},
        ),
    ],
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ObjectMeta:
    return storage.update_object_meta(slug, oid, body.model_dump(exclude_unset=True))


@router.delete("/{oid}", status_code=204, operation_id="deleteObject")
def delete_object(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    storage.delete_object(slug, oid)
    return Response(status_code=204)


@router.get("/{oid}/content", operation_id="getObjectContent")
def get_object_content(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    data, etag = storage.get_object_content(slug, oid)
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    meta = storage.get_object(slug, oid)
    headers = {"ETag": etag}
    return Response(
        content=data,
        media_type=meta.mime or "application/octet-stream",
        headers=headers,
    )


class ContentPutResponse(BaseModel):
    meta: ObjectMeta
    etag: str = Field(description="new etag after write")


@router.put(
    "/{oid}/content",
    response_model=ContentPutResponse,
    operation_id="putObjectContent",
    summary="Replace an object's raw content",
    description=(
        "**Body is RAW BYTES — never a JSON wrapper.** A common mistake is to "
        "PUT `{\"content\": \"<html>...\"}` thinking the server unwraps. It "
        "doesn't — the literal string ends up stored, and the iframe loads "
        "JSON instead of HTML. Send the actual content with the right "
        "`Content-Type` (`text/html` for html-ish kinds, `text/markdown` for "
        "md, `application/json` for runbook, the image mime for image, etc.).\n\n"
        "Optional `If-Match: <etag>` header for stale-check.\n\n"
        "**Examples:**\n\n"
        "**text** (kind=md / html / approval-html / qa-form):\n"
        "```\n# Field Notes — updated\n\n- [x] WebSocket primitive wired\n- [ ] Awaiting echo-filter design\n```\n\n"
        "**runbook** (kind=runbook — JSON content):\n"
        "```json\n{\n  \"title\": \"Comms module rollout\",\n  \"steps\": [\n"
        "    {\"id\": \"s1\", \"title\": \"Wire WebSocket primitive\", \"status\": \"done\"},\n"
        "    {\"id\": \"s2\", \"title\": \"JSONL persistence\", \"status\": \"in-progress\"},\n"
        "    {\"id\": \"s3\", \"title\": \"Shared-bus fan-out\", \"status\": \"blocked\","
        " \"blocker\": \"Need echo-filter design.\"}\n  ]\n}\n```\n\n"
        "Step `status` values: `todo` / `in-progress` / `done` / `blocked`."
    ),
)
async def put_object_content(
    slug: str,
    oid: str,
    request: Request,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ContentPutResponse:
    settings = get_settings()
    data = await request.body()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="upload exceeds size cap")
    meta, etag = storage.put_object_content(slug, oid, data, if_match=if_match)
    return ContentPutResponse(meta=meta, etag=etag)
