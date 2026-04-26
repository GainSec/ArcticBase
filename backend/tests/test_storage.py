from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from arctic_base.models import (
    ObjectKind,
    ObjectMeta,
    ResponseEvent,
    ResponseKind,
    Submitter,
    WorkbenchMeta,
)
from arctic_base.storage.errors import AlreadyExists, NotFound, StaleETag
from arctic_base.storage.filesystem import FilesystemStorage, new_object_id

VALID_THEME = """\
---
name: Test Theme
core:
  bg: '#fff'
  surface: '#fafafa'
  ink: '#111'
  muted: '#555'
  rule: '#ccc'
  accent: '#06d'
  accent-2: '#d06'
  success: '#0a0'
  error: '#a00'
typography:
  body: { fontFamily: "Inter", fontSize: "16px", fontWeight: "400", lineHeight: "1.5" }
  mono: { fontFamily: "JetBrains Mono", fontSize: "13px", fontWeight: "400", lineHeight: "1.4" }
rounded:
  sm: '0.25rem'
  md: '0.5rem'
  lg: '1rem'
spacing:
  unit: '8px'
  gutter: '24px'
  margin: '32px'
custom:
  pop: '#f0c'
---

# Test theme prose

Use rounded-md for cards.
"""

NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def fs(tmp_path: Path) -> FilesystemStorage:
    return FilesystemStorage(tmp_path / "data")


def make_wb(slug: str = "demo") -> WorkbenchMeta:
    return WorkbenchMeta(slug=slug, title=slug.title(), created_at=NOW, updated_at=NOW)


def make_obj(oid: str | None = None, kind: ObjectKind = ObjectKind.md) -> ObjectMeta:
    return ObjectMeta(
        id=oid or new_object_id(),
        kind=kind,
        title="t",
        created_at=NOW,
        updated_at=NOW,
    )


def test_create_and_list_workbenches(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("alpha"))
    fs.create_workbench(make_wb("beta"))
    listed = [w.slug for w in fs.list_workbenches()]
    # Default sort is by last_accessed_at desc; both created at NOW so order is stable but not
    # necessarily alphabetical.
    assert set(listed) == {"alpha", "beta"}


def test_duplicate_workbench_rejected(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("dup"))
    with pytest.raises(AlreadyExists):
        fs.create_workbench(make_wb("dup"))


def test_get_missing_workbench(fs: FilesystemStorage) -> None:
    with pytest.raises(NotFound):
        fs.get_workbench("nope")


def test_update_workbench_patch(fs: FilesystemStorage) -> None:
    created = fs.create_workbench(make_wb("alpha"))
    updated = fs.update_workbench("alpha", {"title": "NEW", "tags": ["x"]})
    assert updated.title == "NEW"
    assert updated.tags == ["x"]
    assert updated.updated_at >= created.updated_at


def test_archive_and_restore(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("g"))
    archive = fs.archive_workbench("g")
    assert archive in fs.list_trash()
    with pytest.raises(NotFound):
        fs.get_workbench("g")
    restored = fs.restore_workbench(archive)
    assert restored == "g"
    assert fs.get_workbench("g").slug == "g"
    assert archive not in fs.list_trash()


def test_theme_round_trip(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("t"))
    theme = fs.put_theme("t", VALID_THEME)
    assert theme.tokens.core["accent"] == "#06d"
    assert "Test theme prose" in theme.prose
    raw = fs.get_theme_raw("t")
    assert "name: Test Theme" in raw


def test_theme_validation_rejects_missing_core(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("t"))
    bad = VALID_THEME.replace("accent: '#06d'", "")
    with pytest.raises(Exception, match="required core tokens"):
        fs.put_theme("t", bad)


def test_theme_assets(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("t"))
    fs.put_theme("t", VALID_THEME)
    fs.put_theme_asset("t", "banner.png", b"\x89PNGfake")
    assert "banner.png" in fs.list_theme_assets("t")
    data, etag = fs.get_theme_asset("t", "banner.png")
    assert data == b"\x89PNGfake"
    assert etag.startswith("sha256:")
    fs.delete_theme_asset("t", "banner.png")
    assert "banner.png" not in fs.list_theme_assets("t")


def test_theme_asset_path_traversal_rejected(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("t"))
    fs.put_theme("t", VALID_THEME)
    with pytest.raises(ValueError):
        fs.put_theme_asset("t", "../escaped.png", b"x")


def test_object_create_read_delete(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj(), content=b"# hi")
    assert o.size_bytes == 4
    assert o.etag.startswith("sha256:")
    fetched = fs.get_object("w", o.id)
    assert fetched.id == o.id
    fs.delete_object("w", o.id)
    with pytest.raises(NotFound):
        fs.get_object("w", o.id)


def test_object_content_stale_etag(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj(), content=b"v1")
    # update with correct etag passes
    updated, new_etag = fs.put_object_content("w", o.id, b"v2", if_match=o.etag)
    assert updated.etag == new_etag
    # update with stale etag rejects
    with pytest.raises(StaleETag):
        fs.put_object_content("w", o.id, b"v3", if_match=o.etag)


def test_object_content_no_if_match_always_succeeds(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj(), content=b"v1")
    updated, _ = fs.put_object_content("w", o.id, b"agent-write")
    assert updated.size_bytes == len(b"agent-write")


def test_response_monotonic_versions(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj(kind=ObjectKind.qa_form))
    e1 = fs.append_response(
        "w",
        o.id,
        ResponseEvent(version=0, object_id=o.id, submitted_at=NOW, kind=ResponseKind.autosave),
    )
    e2 = fs.append_response(
        "w",
        o.id,
        ResponseEvent(version=0, object_id=o.id, submitted_at=NOW, kind=ResponseKind.submit),
    )
    e3 = fs.append_response(
        "w",
        o.id,
        ResponseEvent(version=0, object_id=o.id, submitted_at=NOW, kind=ResponseKind.submit),
    )
    assert (e1.version, e2.version, e3.version) == (1, 2, 3)
    # state_version should bump only on submit kinds (2 submits → +2)
    final = fs.get_object("w", o.id)
    assert final.state_version == 2


def test_response_since_version_filter(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj())
    for _ in range(5):
        fs.append_response(
            "w",
            o.id,
            ResponseEvent(
                version=0,
                object_id=o.id,
                submitted_at=NOW,
                submitted_by=Submitter.user,
                kind=ResponseKind.submit,
            ),
        )
    after = fs.list_responses("w", o.id, since_version=3)
    assert [e.version for e in after] == [4, 5]


def test_response_latest(fs: FilesystemStorage) -> None:
    fs.create_workbench(make_wb("w"))
    o = fs.create_object("w", make_obj())
    assert fs.get_latest_response("w", o.id) is None
    fs.append_response(
        "w",
        o.id,
        ResponseEvent(
            version=0,
            object_id=o.id,
            submitted_at=NOW,
            kind=ResponseKind.submit,
            payload={"answer": "yes"},
        ),
    )
    latest = fs.get_latest_response("w", o.id)
    assert latest is not None
    assert latest.payload == {"answer": "yes"}
