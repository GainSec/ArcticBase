"""Bulk archive and import across all workbenches."""

from __future__ import annotations

import contextlib
import tarfile
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile

from arctic_base.api.deps import get_storage
from arctic_base.storage.errors import NotFound
from arctic_base.storage.filesystem import FilesystemStorage, _utcnow

router = APIRouter(prefix="/archive", tags=["archive"])


class ArchiveEntry(BaseModel):
    slug: str
    title: str
    content_bytes: int
    snapshot_bytes: int


class ArchiveManifest(BaseModel):
    workbenches: list[ArchiveEntry]
    total_content_bytes: int
    total_snapshot_bytes: int


class ImportCandidate(BaseModel):
    slug: str
    title: str
    exists: bool
    selected_by_default: bool


class ImportInspection(BaseModel):
    workbenches: list[ImportCandidate]


class ImportReport(BaseModel):
    imported: list[str]
    skipped: list[str]


def _parse_slugs(slugs: str | None) -> list[str] | None:
    if slugs is None:
        return None
    selected = [s.strip() for s in slugs.split(",") if s.strip()]
    if not selected:
        raise HTTPException(status_code=400, detail="no workbenches selected")
    return selected


async def _spool_upload(request: Request) -> tuple[Path, Path]:
    content_type = (request.headers.get("content-type") or "").lower()
    if not content_type.startswith("multipart/"):
        raise HTTPException(status_code=400, detail="expected multipart upload with 'file'")

    form = await request.form()
    part = form.get("file")
    if not isinstance(part, UploadFile):
        raise HTTPException(status_code=400, detail="missing 'file' part")

    tmpdir = Path(tempfile.mkdtemp(prefix="ab-archive-upload-"))
    tmp = tmpdir / "upload.tar.gz"
    with tmp.open("wb") as fh:
        while chunk := await part.read(1024 * 1024):
            fh.write(chunk)
    return tmpdir, tmp


def _cleanup_tmpdir(tmpdir: Path) -> None:
    for child in tmpdir.iterdir():
        child.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        tmpdir.rmdir()


@router.get("/manifest", response_model=ArchiveManifest, operation_id="archiveManifest")
def manifest(storage: Annotated[FilesystemStorage, Depends(get_storage)]) -> ArchiveManifest:
    rows = storage.archive_manifest()
    return ArchiveManifest(
        workbenches=[ArchiveEntry(**r) for r in rows],
        total_content_bytes=sum(r["content_bytes"] for r in rows),
        total_snapshot_bytes=sum(r["snapshot_bytes"] for r in rows),
    )


@router.get("", operation_id="archiveExport")
def export_all(
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    slugs: Annotated[
        str | None,
        Query(description="Comma-separated slugs. Omit to archive every workbench."),
    ] = None,
    include_snapshots: Annotated[
        bool, Query(description="Include snapshot history. Usually far larger than content.")
    ] = False,
) -> FileResponse:
    available = [r["slug"] for r in storage.archive_manifest()]
    selected = available if slugs is None else _parse_slugs(slugs) or []
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise HTTPException(status_code=404, detail=f"unknown workbench(es): {unknown}")
    if not selected:
        raise HTTPException(status_code=400, detail="no workbenches selected")

    tmpdir = Path(tempfile.mkdtemp(prefix="ab-archive-"))
    tmp = tmpdir / "archive.tar.gz"
    try:
        storage.export_bulk(selected, include_snapshots, tmp)
    except NotFound as e:
        _cleanup_tmpdir(tmpdir)
        raise HTTPException(status_code=404, detail=str(e)) from e

    filename = f"arctic-base-{_utcnow().strftime('%Y%m%dT%H%M%SZ')}.tar.gz"

    return FileResponse(
        tmp,
        media_type="application/gzip",
        filename=filename,
        background=BackgroundTask(lambda: _cleanup_tmpdir(tmpdir)),
    )


@router.post("/inspect", response_model=ImportInspection, operation_id="archiveInspect")
async def inspect_archive(
    request: Request,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
) -> ImportInspection:
    tmpdir, tmp = await _spool_upload(request)
    try:
        try:
            report = storage.inspect_bulk(tmp)
        except (ValueError, OSError, tarfile.TarError) as e:
            raise HTTPException(status_code=400, detail=f"could not read archive: {e}") from e

        entries: list[ImportCandidate] = []
        for row in report["workbenches"]:
            try:
                storage.get_workbench(row["slug"])
                exists = True
            except NotFound:
                exists = False
            entries.append(
                ImportCandidate(
                    slug=row["slug"],
                    title=row["title"],
                    exists=exists,
                    selected_by_default=True,
                )
            )
        return ImportInspection(workbenches=entries)
    finally:
        _cleanup_tmpdir(tmpdir)


@router.post("/import", response_model=ImportReport, operation_id="archiveImport")
async def import_all(
    request: Request,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    slugs: Annotated[
        str | None,
        Query(description="Comma-separated archive slugs to import. Omit to import all."),
    ] = None,
) -> ImportReport:
    selected = _parse_slugs(slugs)
    tmpdir, tmp = await _spool_upload(request)
    try:
        try:
            report = storage.import_bulk(tmp, selected_slugs=selected)
        except NotFound as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (ValueError, OSError, tarfile.TarError) as e:
            raise HTTPException(status_code=400, detail=f"could not read archive: {e}") from e
    finally:
        _cleanup_tmpdir(tmpdir)

    return ImportReport(**report)
