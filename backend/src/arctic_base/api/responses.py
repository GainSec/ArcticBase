import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arctic_base.api.deps import get_storage
from arctic_base.models import ResponseEvent, ResponseKind, Submitter
from arctic_base.storage.filesystem import FilesystemStorage

router = APIRouter(prefix="/workbenches/{slug}/objects/{oid}/responses", tags=["responses"])


class ResponseAppend(BaseModel):
    kind: ResponseKind = ResponseKind.submit
    submitted_by: Submitter = Submitter.user
    payload: dict = Field(default_factory=dict)


@router.get("", response_model=list[ResponseEvent], operation_id="listResponses")
def list_responses(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    since_version: int = 0,
) -> list[ResponseEvent]:
    return storage.list_responses(slug, oid, since_version=since_version)


@router.get("/latest", response_model=ResponseEvent | None, operation_id="getLatestResponse")
def latest_response(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ResponseEvent | None:
    return storage.get_latest_response(slug, oid)


@router.get("/latest/payload", operation_id="getLatestPayload")
def latest_payload(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> dict[str, Any]:
    """Convenience: returns ONLY the payload of the latest submission (or {} if none).

    Equivalent to `(GET .../responses/latest).payload` but cheaper for agents that just want
    the JSON the user sent — same shape the JSON-export button produces.
    """

    latest = storage.get_latest_response(slug, oid)
    return latest.payload if latest else {}


@router.get("/export", operation_id="exportResponses")
def export_responses(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> Response:
    """Download the full response history for an object as a JSON file.

    Useful for user-side backups and for agents that want every event including autosaves.
    """

    events = storage.list_responses(slug, oid, since_version=0)
    # Verify the object exists (list returns [] for nonexistent — distinguish from 'no events').
    storage.get_object(slug, oid)
    payload = {
        "slug": slug,
        "object_id": oid,
        "events": [json.loads(e.model_dump_json()) for e in events],
    }
    body = json.dumps(payload, indent=2).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"content-disposition": f'attachment; filename="{oid}-responses.json"'},
    )


@router.post(
    "",
    response_model=ResponseEvent,
    status_code=201,
    operation_id="appendResponse",
    summary="Append a response event (typically a user submit)",
    description=(
        "Append-only event log per object. The SPA writes here when the user "
        "hits the submit button on a review HTML; agents may also append "
        "`agent-edit` or `autosave` events. Read back via "
        "`GET .../responses?since_version=N` (poll cadence 2–5 s)."
    ),
)
def append_response(
    slug: str,
    oid: str,
    body: Annotated[
        ResponseAppend,
        Body(
            openapi_examples={"default": {"value": {
                "kind": "submit",
                "submitted_by": "user",
                "payload": {
                    "q1": {"choice": "ws", "note": "Use WebSocket for v1."},
                    "q2": {"choice": "skip", "note": "Per-titan keys deferred."},
                    "q3": {"choice": "jsonl", "note": "Append-only persistence approved."},
                },
            }}},
        ),
    ],
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ResponseEvent:
    event = ResponseEvent(
        version=0,
        object_id=oid,
        submitted_at=datetime.now(UTC),
        submitted_by=body.submitted_by,
        kind=body.kind,
        payload=body.payload,
    )
    return storage.append_response(slug, oid, event)
