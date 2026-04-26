"""Filesystem-backed Storage implementation.

Layout:
    data/
      workbenches/{slug}/
        .lock                       advisory lock for manifest/object-meta writes
        manifest.json
        theme.md
        theme/
        objects/{id}/
          .lock                     advisory lock for response monotonicity
          meta.json
          content
        responses/{id}/
          {version}.json
          latest.json
      trash/{slug}-{ts}.tar.gz
      tmp/uploads/
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from arctic_base.models import (
    ObjectMeta,
    ResponseEvent,
    Theme,
    WorkbenchMeta,
)
from arctic_base.storage.errors import (
    AlreadyExists,
    NotFound,
    StaleETag,
)
from arctic_base.theme import parse_theme_md

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _slug_ok(slug: str) -> bool:
    return bool(SLUG_RE.match(slug))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _dump_model(m: BaseModel) -> bytes:
    # `view_url` on WorkbenchMeta is a computed_field — derived from `slug`, never stored.
    # Other models are unaffected (the exclude is silent for missing keys).
    return (m.model_dump_json(indent=2, exclude={"view_url"}) + "\n").encode("utf-8")


@contextlib.contextmanager
def _flock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class FilesystemStorage:
    """The v1 storage backend. Single-process file-locked writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        (self.root / "workbenches").mkdir(parents=True, exist_ok=True)
        (self.root / "trash").mkdir(parents=True, exist_ok=True)
        (self.root / "tmp" / "uploads").mkdir(parents=True, exist_ok=True)

    # --- paths ---
    def _wb_dir(self, slug: str) -> Path:
        return self.root / "workbenches" / slug

    def _wb_lock(self, slug: str) -> Path:
        return self._wb_dir(slug) / ".lock"

    def _wb_manifest(self, slug: str) -> Path:
        return self._wb_dir(slug) / "manifest.json"

    def _theme_md(self, slug: str) -> Path:
        return self._wb_dir(slug) / "theme.md"

    def _theme_dir(self, slug: str) -> Path:
        return self._wb_dir(slug) / "theme"

    def _objects_dir(self, slug: str) -> Path:
        return self._wb_dir(slug) / "objects"

    def _object_dir(self, slug: str, oid: str) -> Path:
        return self._objects_dir(slug) / oid

    def _object_meta_path(self, slug: str, oid: str) -> Path:
        return self._object_dir(slug, oid) / "meta.json"

    def _object_content_path(self, slug: str, oid: str) -> Path:
        return self._object_dir(slug, oid) / "content"

    def _responses_dir(self, slug: str, oid: str) -> Path:
        return self._wb_dir(slug) / "responses" / oid

    def _responses_lock(self, slug: str, oid: str) -> Path:
        return self._responses_dir(slug, oid) / ".lock"

    # --- workbenches ---
    def list_workbenches(self) -> list[WorkbenchMeta]:
        out: list[WorkbenchMeta] = []
        wb_root = self.root / "workbenches"
        if not wb_root.is_dir():
            return out
        for entry in sorted(wb_root.iterdir()):
            manifest = entry / "manifest.json"
            if manifest.is_file():
                out.append(WorkbenchMeta.model_validate_json(manifest.read_bytes()))
        # Apply manual order override if present.
        order = self._read_workbench_order()
        if order:
            ranked = {slug: i for i, slug in enumerate(order)}
            out.sort(key=lambda w: (ranked.get(w.slug, 10_000_000), w.slug))
        else:
            # Default: most recently accessed first; falls back to updated_at, then slug.
            out.sort(
                key=lambda w: (
                    -(w.last_accessed_at.timestamp() if w.last_accessed_at else 0),
                    -(w.updated_at.timestamp()),
                    w.slug,
                )
            )
        return out

    def _read_workbench_order(self) -> list[str]:
        path = self.root / "workbench_order.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text())
            return [str(s) for s in data.get("slugs", [])]
        except Exception:
            return []

    def set_workbench_order(self, slugs: list[str]) -> None:
        path = self.root / "workbench_order.json"
        _atomic_write(path, json.dumps({"slugs": slugs}, indent=2).encode("utf-8") + b"\n")

    def clear_workbench_order(self) -> None:
        path = self.root / "workbench_order.json"
        if path.is_file():
            path.unlink()

    def touch_workbench(self, slug: str) -> None:
        """Update last_accessed_at without bumping updated_at."""
        path = self._wb_manifest(slug)
        if not path.is_file():
            raise NotFound(f"workbench {slug!r} not found")
        with _flock(self._wb_lock(slug)):
            current = WorkbenchMeta.model_validate_json(path.read_bytes())
            updated = current.model_copy(update={"last_accessed_at": _utcnow()})
            _atomic_write(path, _dump_model(updated))

    def get_workbench(self, slug: str) -> WorkbenchMeta:
        path = self._wb_manifest(slug)
        if not path.is_file():
            raise NotFound(f"workbench {slug!r} not found")
        return WorkbenchMeta.model_validate_json(path.read_bytes())

    def create_workbench(self, meta: WorkbenchMeta) -> WorkbenchMeta:
        if not _slug_ok(meta.slug):
            raise ValueError(f"invalid slug: {meta.slug!r}")
        target = self._wb_dir(meta.slug)
        if target.exists():
            raise AlreadyExists(f"workbench {meta.slug!r} already exists")
        target.mkdir(parents=True)
        with _flock(self._wb_lock(meta.slug)):
            now = _utcnow()
            meta = meta.model_copy(
                update={"created_at": now, "updated_at": now, "last_accessed_at": now}
            )
            _atomic_write(self._wb_manifest(meta.slug), _dump_model(meta))
            self._objects_dir(meta.slug).mkdir(exist_ok=True)
            self._theme_dir(meta.slug).mkdir(exist_ok=True)
        return meta

    def update_workbench(self, slug: str, patch: dict) -> WorkbenchMeta:
        with _flock(self._wb_lock(slug)):
            current = self.get_workbench(slug)
            mutable = {
                "title", "description", "url", "ip", "local_path", "tags", "banner",
                "custom_fields",
            }
            for k in patch:
                if k not in mutable:
                    raise ValueError(f"field {k!r} is not patchable")
            updated = current.model_copy(update={**patch, "updated_at": _utcnow()})
            _atomic_write(self._wb_manifest(slug), _dump_model(updated))
            self.audit(slug, "workbench.update", fields=list(patch.keys()))
            return updated

    def archive_workbench(self, slug: str) -> str:
        wb = self._wb_dir(slug)
        if not wb.is_dir():
            raise NotFound(f"workbench {slug!r} not found")
        ts = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"{slug}-{ts}.tar.gz"
        archive_path = self.root / "trash" / archive_name
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(wb, arcname=slug)
        shutil.rmtree(wb)
        return archive_name

    def restore_workbench(self, archive_name: str) -> str:
        archive_path = self.root / "trash" / archive_name
        if not archive_path.is_file():
            raise NotFound(f"archive {archive_name!r} not found")
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getmembers()
            top = {Path(m.name).parts[0] for m in members if m.name}
            if len(top) != 1:
                raise ValueError(f"archive {archive_name!r} has unexpected layout")
            slug = top.pop()
            target = self._wb_dir(slug)
            if target.exists():
                raise AlreadyExists(f"workbench {slug!r} already exists; cannot restore")
            tar.extractall(self.root / "workbenches", filter="data")
        archive_path.unlink()
        return slug

    def list_trash(self) -> list[str]:
        return sorted(p.name for p in (self.root / "trash").iterdir() if p.is_file())

    # --- snapshots (proactive labeled backups) ---
    def _snapshots_dir(self, slug: str) -> Path:
        d = self.root / "snapshots" / slug
        d.mkdir(parents=True, exist_ok=True)
        return d

    def snapshot_workbench(self, slug: str, label: str) -> dict:
        if not self._wb_dir(slug).is_dir():
            raise NotFound(f"workbench {slug!r} not found")
        ts = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", label)[:60] or "snapshot"
        name = f"{ts}-{safe}.tar.gz"
        path = self._snapshots_dir(slug) / name
        with tarfile.open(path, "w:gz") as tar:
            tar.add(self._wb_dir(slug), arcname=slug)
        st = path.stat()
        return {"name": name, "label": label, "size_bytes": st.st_size,
                "created_at": _utcnow().isoformat()}

    def list_snapshots(self, slug: str) -> list[dict]:
        d = self.root / "snapshots" / slug
        if not d.is_dir():
            return []
        out: list[dict] = []
        for p in sorted(d.iterdir(), reverse=True):
            if not p.is_file():
                continue
            # Filename format: {ts}-{label}.tar.gz
            stem = p.name.removesuffix(".tar.gz")
            parts = stem.split("-", 1)
            label = parts[1] if len(parts) > 1 else ""
            out.append({
                "name": p.name,
                "label": label,
                "size_bytes": p.stat().st_size,
                "created_at": parts[0] if parts else "",
            })
        return out

    def get_snapshot_bytes(self, slug: str, snapshot_name: str) -> bytes:
        p = self.root / "snapshots" / slug / snapshot_name
        if not p.is_file():
            raise NotFound(f"snapshot {snapshot_name!r} not found")
        return p.read_bytes()

    def restore_snapshot(self, slug: str, snapshot_name: str, new_slug: str) -> str:
        if not _slug_ok(new_slug):
            raise ValueError(f"invalid slug: {new_slug!r}")
        src = self.root / "snapshots" / slug / snapshot_name
        if not src.is_file():
            raise NotFound(f"snapshot {snapshot_name!r} not found")
        target = self._wb_dir(new_slug)
        if target.exists():
            raise AlreadyExists(f"workbench {new_slug!r} already exists")
        # Extract into a tmp location then rename the inner directory.
        tmp = self.root / "tmp" / f"restore-{new_slug}-{_utcnow().strftime('%H%M%S')}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(src, "r:gz") as tar:
                tar.extractall(tmp, filter="data")
            inner = next(tmp.iterdir())
            inner.rename(target)
            # Update the manifest's slug to the new slug.
            manifest_path = self._wb_manifest(new_slug)
            if manifest_path.is_file():
                wb = WorkbenchMeta.model_validate_json(manifest_path.read_bytes())
                _atomic_write(manifest_path, _dump_model(wb.model_copy(update={"slug": new_slug})))
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        return new_slug

    def delete_snapshot(self, slug: str, snapshot_name: str) -> None:
        p = self.root / "snapshots" / slug / snapshot_name
        if not p.is_file():
            raise NotFound(f"snapshot {snapshot_name!r} not found")
        p.unlink()

    # --- audit log ---
    def _audit_path(self, slug: str) -> Path:
        return self._wb_dir(slug) / "audit.jsonl"

    def audit(self, slug: str, event_type: str, **fields: object) -> None:
        """Append an audit event for content-level mutations. Best-effort; never raises."""
        try:
            wb_dir = self._wb_dir(slug)
            if not wb_dir.is_dir():
                return
            event = {"ts": _utcnow().isoformat(), "event": event_type, **fields}
            path = self._audit_path(slug)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass

    def read_audit(
        self, slug: str, *, since: str | None = None, until: str | None = None
    ) -> list[dict]:
        path = self._audit_path(slug)
        if not path.is_file():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts = ev.get("ts", "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            out.append(ev)
        return out

    def duplicate_workbench(self, slug: str, new_slug: str) -> WorkbenchMeta:
        """Clone a workbench: copy theme + objects + content. Responses are NOT cloned (they
        belong to the original conversation; clones start fresh at state_version=0)."""
        if not _slug_ok(new_slug):
            raise ValueError(f"invalid slug: {new_slug!r}")
        src = self._wb_dir(slug)
        if not src.is_dir():
            raise NotFound(f"workbench {slug!r} not found")
        dst = self._wb_dir(new_slug)
        if dst.exists():
            raise AlreadyExists(f"workbench {new_slug!r} already exists")
        shutil.copytree(src, dst)
        # Drop any cloned response history.
        responses_dir = dst / "responses"
        if responses_dir.is_dir():
            shutil.rmtree(responses_dir)
        # Reset state_version on every cloned object.
        objects_dir = dst / "objects"
        if objects_dir.is_dir():
            for entry in objects_dir.iterdir():
                meta_path = entry / "meta.json"
                if meta_path.is_file():
                    om = ObjectMeta.model_validate_json(meta_path.read_bytes())
                    _atomic_write(meta_path, _dump_model(om.model_copy(update={"state_version": 0})))
        # Update workbench manifest.
        manifest_path = dst / "manifest.json"
        original = WorkbenchMeta.model_validate_json(manifest_path.read_bytes())
        now = _utcnow()
        cloned = original.model_copy(
            update={
                "slug": new_slug,
                "title": f"{original.title} (copy)",
                "created_at": now,
                "updated_at": now,
            }
        )
        _atomic_write(manifest_path, _dump_model(cloned))
        return cloned

    def export_workbench(self, slug: str) -> tuple[bytes, str]:
        """Return tar.gz bytes of a workbench (without deleting it).

        Returns (data, filename). Useful for user-side backups.
        """
        wb = self._wb_dir(slug)
        if not wb.is_dir():
            raise NotFound(f"workbench {slug!r} not found")
        ts = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"{slug}-{ts}.tar.gz"
        # Build in-memory tar.
        import io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(wb, arcname=slug)
        return buf.getvalue(), filename

    def get_trash_archive(self, archive_name: str) -> bytes:
        path = self.root / "trash" / archive_name
        if not path.is_file():
            raise NotFound(f"archive {archive_name!r} not found")
        return path.read_bytes()

    def purge_trash(self, archive_name: str) -> None:
        path = self.root / "trash" / archive_name
        if not path.is_file():
            raise NotFound(f"archive {archive_name!r} not found")
        path.unlink()

    # --- theme ---
    def get_theme_raw(self, slug: str) -> str:
        path = self._theme_md(slug)
        if not path.is_file():
            raise NotFound(f"theme.md not found for {slug!r}")
        return path.read_text(encoding="utf-8")

    def get_theme(self, slug: str) -> Theme:
        raw = self.get_theme_raw(slug)
        theme = parse_theme_md(raw)
        return theme.model_copy(update={"assets": self.list_theme_assets(slug)})

    def put_theme(self, slug: str, raw_md: str) -> Theme:
        theme = parse_theme_md(raw_md)  # validates required tokens
        with _flock(self._wb_lock(slug)):
            _atomic_write(self._theme_md(slug), raw_md.encode("utf-8"))
        self.audit(slug, "theme.put")
        return theme.model_copy(update={"assets": self.list_theme_assets(slug)})

    def list_theme_assets(self, slug: str) -> list[str]:
        d = self._theme_dir(slug)
        if not d.is_dir():
            return []
        out: list[str] = []
        for p in sorted(d.rglob("*")):
            if p.is_file():
                out.append(str(p.relative_to(d)))
        return out

    def get_theme_asset(self, slug: str, path: str) -> tuple[bytes, str]:
        target = self._safe_theme_asset_path(slug, path)
        if not target.is_file():
            raise NotFound(f"theme asset {path!r} not found")
        data = target.read_bytes()
        return data, _hash(data)

    def put_theme_asset(self, slug: str, path: str, data: bytes) -> None:
        target = self._safe_theme_asset_path(slug, path)
        _atomic_write(target, data)

    def delete_theme_asset(self, slug: str, path: str) -> None:
        target = self._safe_theme_asset_path(slug, path)
        if not target.is_file():
            raise NotFound(f"theme asset {path!r} not found")
        target.unlink()

    def _safe_theme_asset_path(self, slug: str, rel: str) -> Path:
        d = self._theme_dir(slug).resolve()
        candidate = (d / rel).resolve()
        if d not in candidate.parents and candidate != d:
            raise ValueError(f"theme asset path {rel!r} escapes theme directory")
        return candidate

    # --- objects ---
    def list_objects(
        self,
        slug: str,
        *,
        kind: str | None = None,
        drawer: str | None = None,
        include_archived: bool = False,
    ) -> list[ObjectMeta]:
        d = self._objects_dir(slug)
        if not d.is_dir():
            return []
        out: list[ObjectMeta] = []
        for entry in sorted(d.iterdir()):
            mp = entry / "meta.json"
            if mp.is_file():
                m = ObjectMeta.model_validate_json(mp.read_bytes())
                if kind and m.kind.value != kind:
                    continue
                if drawer and m.drawer != drawer:
                    continue
                if not include_archived and m.archived:
                    continue
                out.append(m)
        # Pinned items first, then by manual order, then by created_at, then by id (stable).
        out.sort(key=lambda o: (not o.pinned, o.order, o.created_at.isoformat(), o.id))
        return out

    def reorder_objects(self, slug: str, oids: list[str]) -> None:
        """Apply a manual ordering by writing the order field on each object."""
        with _flock(self._wb_lock(slug)):
            for i, oid in enumerate(oids):
                meta_path = self._object_meta_path(slug, oid)
                if not meta_path.is_file():
                    continue  # object disappeared between client and server
                current = ObjectMeta.model_validate_json(meta_path.read_bytes())
                if current.order != i:
                    updated = current.model_copy(update={"order": i})
                    _atomic_write(meta_path, _dump_model(updated))

    def touch_object(self, slug: str, oid: str) -> None:
        """Update an object's last_accessed_at and the workbench's last_accessed_at."""
        path = self._object_meta_path(slug, oid)
        if not path.is_file():
            raise NotFound(f"object {oid!r} not found in workbench {slug!r}")
        with _flock(self._wb_lock(slug)):
            current = ObjectMeta.model_validate_json(path.read_bytes())
            now = _utcnow()
            _atomic_write(path, _dump_model(current.model_copy(update={"last_accessed_at": now})))
            # Bubble up to the workbench.
            wbm = self._wb_manifest(slug)
            if wbm.is_file():
                wb = WorkbenchMeta.model_validate_json(wbm.read_bytes())
                _atomic_write(wbm, _dump_model(wb.model_copy(update={"last_accessed_at": now})))

    def get_object(self, slug: str, oid: str) -> ObjectMeta:
        path = self._object_meta_path(slug, oid)
        if not path.is_file():
            raise NotFound(f"object {oid!r} not found in workbench {slug!r}")
        return ObjectMeta.model_validate_json(path.read_bytes())

    def create_object(
        self, slug: str, meta: ObjectMeta, content: bytes | None = None
    ) -> ObjectMeta:
        if not self._wb_manifest(slug).is_file():
            raise NotFound(f"workbench {slug!r} not found")
        target = self._object_dir(slug, meta.id)
        if target.exists():
            raise AlreadyExists(f"object {meta.id!r} already exists")
        target.mkdir(parents=True)
        now = _utcnow()
        meta_dict = {"created_at": now, "updated_at": now, "state_version": 0}
        if content is not None:
            meta_dict.update(etag=_hash(content), size_bytes=len(content))
            _atomic_write(self._object_content_path(slug, meta.id), content)
        meta = meta.model_copy(update=meta_dict)
        _atomic_write(self._object_meta_path(slug, meta.id), _dump_model(meta))
        self.audit(slug, "object.create", oid=meta.id, kind=meta.kind.value, title=meta.title)
        return meta

    def update_object_meta(self, slug: str, oid: str, patch: dict) -> ObjectMeta:
        with _flock(self._wb_lock(slug)):
            current = self.get_object(slug, oid)
            mutable = {"title", "description", "drawer", "pinned", "archived"}
            for k in patch:
                if k not in mutable:
                    raise ValueError(f"field {k!r} is not patchable on object meta")
            updated = current.model_copy(update={**patch, "updated_at": _utcnow()})
            _atomic_write(self._object_meta_path(slug, oid), _dump_model(updated))
            self.audit(slug, "object.update", oid=oid, fields=list(patch.keys()))
            return updated

    def delete_object(self, slug: str, oid: str) -> None:
        d = self._object_dir(slug, oid)
        if not d.is_dir():
            raise NotFound(f"object {oid!r} not found in workbench {slug!r}")
        shutil.rmtree(d)
        rd = self._responses_dir(slug, oid)
        if rd.is_dir():
            shutil.rmtree(rd)
        self.audit(slug, "object.delete", oid=oid)

    def get_object_content(self, slug: str, oid: str) -> tuple[bytes, str]:
        meta = self.get_object(slug, oid)
        path = self._object_content_path(slug, oid)
        data = path.read_bytes() if path.is_file() else b""
        return data, meta.etag

    def put_object_content(
        self, slug: str, oid: str, data: bytes, if_match: str | None = None
    ) -> tuple[ObjectMeta, str]:
        with _flock(self._wb_lock(slug)):
            current = self.get_object(slug, oid)
            if if_match is not None and if_match != current.etag:
                raise StaleETag(expected=current.etag, actual=if_match)
            new_etag = _hash(data)
            _atomic_write(self._object_content_path(slug, oid), data)
            updated = current.model_copy(
                update={
                    "etag": new_etag,
                    "size_bytes": len(data),
                    "updated_at": _utcnow(),
                }
            )
            _atomic_write(self._object_meta_path(slug, oid), _dump_model(updated))
            self.audit(slug, "object.content_write", oid=oid, size_bytes=len(data), etag=new_etag)
            return updated, new_etag

    # --- responses ---
    def list_responses(
        self, slug: str, oid: str, since_version: int = 0
    ) -> list[ResponseEvent]:
        d = self._responses_dir(slug, oid)
        if not d.is_dir():
            return []
        out: list[ResponseEvent] = []
        for path in sorted(d.glob("*.json")):
            if path.name == "latest.json":
                continue
            try:
                v = int(path.stem)
            except ValueError:
                continue
            if v <= since_version:
                continue
            out.append(ResponseEvent.model_validate_json(path.read_bytes()))
        return out

    def get_latest_response(self, slug: str, oid: str) -> ResponseEvent | None:
        latest = self._responses_dir(slug, oid) / "latest.json"
        if not latest.is_file():
            return None
        return ResponseEvent.model_validate_json(latest.read_bytes())

    def append_response(self, slug: str, oid: str, event: ResponseEvent) -> ResponseEvent:
        if not self._object_meta_path(slug, oid).is_file():
            raise NotFound(f"object {oid!r} not found in workbench {slug!r}")
        d = self._responses_dir(slug, oid)
        d.mkdir(parents=True, exist_ok=True)
        with _flock(self._responses_lock(slug, oid)):
            existing = sorted(
                int(p.stem)
                for p in d.glob("*.json")
                if p.name != "latest.json" and p.stem.isdigit()
            )
            next_version = (existing[-1] if existing else 0) + 1
            event = event.model_copy(
                update={"version": next_version, "object_id": oid, "submitted_at": _utcnow()}
            )
            _atomic_write(d / f"{next_version}.json", _dump_model(event))
            _atomic_write(d / "latest.json", _dump_model(event))
            self.audit(slug, "response.append", oid=oid, version=next_version,
                       kind=event.kind.value, by=event.submitted_by.value)
            # bump state_version on the object meta only on submit kind
            if event.kind.value == "submit":
                with _flock(self._wb_lock(slug)):
                    current = self.get_object(slug, oid)
                    bumped = current.model_copy(
                        update={
                            "state_version": current.state_version + 1,
                            "updated_at": _utcnow(),
                        }
                    )
                    _atomic_write(self._object_meta_path(slug, oid), _dump_model(bumped))
        return event


# Helper used by callers that need a fresh ULID-ish id for a new object.
def new_object_id() -> str:
    return f"obj_{uuid.uuid4().hex[:24]}"


__all__ = ["FilesystemStorage", "new_object_id", "json"]
