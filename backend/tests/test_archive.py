from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arctic_base.api.deps import get_storage
from arctic_base.main import app
from arctic_base.storage.filesystem import FilesystemStorage

from .test_api import VALID_THEME


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = FilesystemStorage(tmp_path / "data")
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_wb(client: TestClient, slug: str, body: bytes = b"payload") -> str:
    client.post("/api/workbenches", json={"title": slug.upper(), "slug": slug})
    client.put(f"/api/workbenches/{slug}/theme", json={"raw": VALID_THEME})
    r = client.post(
        f"/api/workbenches/{slug}/objects",
        files={
            "meta": (None, '{"kind":"file","title":"f","drawer":"files"}', "application/json"),
            "file": ("f.bin", body, "application/octet-stream"),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_archive_manifest_lists_sizes(client: TestClient) -> None:
    _make_wb(client, "alpha")
    _make_wb(client, "beta")

    r = client.get("/api/archive/manifest")

    assert r.status_code == 200, r.text
    body = r.json()
    slugs = {w["slug"] for w in body["workbenches"]}
    assert {"alpha", "beta"} <= slugs
    assert body["total_content_bytes"] > 0
    for w in body["workbenches"]:
        assert w["content_bytes"] >= 0
        assert w["snapshot_bytes"] >= 0


def test_archive_export_all_by_default(client: TestClient) -> None:
    _make_wb(client, "alpha")
    _make_wb(client, "beta")

    r = client.get("/api/archive")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/gzip"
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert any(n.endswith("/ARCHIVE.json") for n in names)
    assert any("/workbenches/alpha/" in n for n in names)
    assert any("/workbenches/beta/" in n for n in names)


def test_archive_export_respects_selection(client: TestClient) -> None:
    _make_wb(client, "alpha")
    _make_wb(client, "beta")

    r = client.get("/api/archive", params={"slugs": "alpha"})

    assert r.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert any("/workbenches/alpha/" in n for n in names)
    assert not any("/workbenches/beta/" in n for n in names)


def test_archive_export_rejects_unknown_slug(client: TestClient) -> None:
    _make_wb(client, "alpha")

    r = client.get("/api/archive", params={"slugs": "alpha,ghost"})

    assert r.status_code == 404
    assert "ghost" in r.text


def test_archive_inspect_lists_import_candidates(client: TestClient) -> None:
    _make_wb(client, "alpha")
    _make_wb(client, "beta")
    archive = client.get("/api/archive").content
    client.delete("/api/workbenches/beta")

    r = client.post(
        "/api/archive/inspect",
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )

    assert r.status_code == 200, r.text
    entries = {w["slug"]: w for w in r.json()["workbenches"]}
    assert entries["alpha"]["exists"] is True
    assert entries["beta"]["exists"] is False
    assert entries["alpha"]["selected_by_default"] is True
    assert entries["beta"]["selected_by_default"] is True


def test_archive_roundtrip_restores_content_bytes(client: TestClient) -> None:
    oid = _make_wb(client, "alpha", body=b"the-original-bytes")
    original = client.get(f"/api/workbenches/alpha/objects/{oid}/content").content
    assert original == b"the-original-bytes"
    archive = client.get("/api/archive", params={"slugs": "alpha"}).content
    client.delete("/api/workbenches/alpha")

    r = client.post(
        "/api/archive/import",
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )

    assert r.status_code == 200, r.text
    assert r.json()["imported"] == ["alpha"]
    assert r.json()["skipped"] == []
    restored = client.get(f"/api/workbenches/alpha/objects/{oid}/content").content
    assert restored == original


def test_archive_import_respects_selection(client: TestClient) -> None:
    _make_wb(client, "alpha")
    _make_wb(client, "beta")
    archive = client.get("/api/archive").content
    client.delete("/api/workbenches/alpha")
    client.delete("/api/workbenches/beta")

    r = client.post(
        "/api/archive/import",
        params={"slugs": "beta"},
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"imported": ["beta"], "skipped": []}
    assert client.get("/api/workbenches/beta").status_code == 200
    assert client.get("/api/workbenches/alpha").status_code == 404


def test_archive_import_copies_existing_and_never_overwrites(client: TestClient) -> None:
    oid = _make_wb(client, "alpha", body=b"ORIGINAL")
    archive = client.get("/api/archive", params={"slugs": "alpha"}).content
    client.put(f"/api/workbenches/alpha/objects/{oid}/content", content=b"CHANGED-SINCE")

    r = client.post(
        "/api/archive/import",
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )

    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == []
    assert r.json()["imported"] == ["alpha-copy"]
    assert client.get(f"/api/workbenches/alpha/objects/{oid}/content").content == b"CHANGED-SINCE"
    copied = client.get("/api/workbenches/alpha-copy").json()
    assert copied["slug"] == "alpha-copy"
    assert copied["view_url"] == "/wb/alpha-copy"
    assert client.get(f"/api/workbenches/alpha-copy/objects/{oid}/content").content == b"ORIGINAL"


def test_archive_import_repeated_copy_suffixes(client: TestClient) -> None:
    _make_wb(client, "alpha", body=b"ORIGINAL")
    archive = client.get("/api/archive", params={"slugs": "alpha"}).content

    first = client.post(
        "/api/archive/import",
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )
    second = client.post(
        "/api/archive/import",
        files={"file": ("a.tar.gz", archive, "application/gzip")},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["imported"] == ["alpha-copy"]
    assert second.json()["imported"] == ["alpha-copy-copy"]
    assert client.get("/api/workbenches/alpha").status_code == 200
    assert client.get("/api/workbenches/alpha-copy").status_code == 200
    assert client.get("/api/workbenches/alpha-copy-copy").status_code == 200


def test_archive_import_accepts_single_workbench_export(client: TestClient) -> None:
    _make_wb(client, "alpha")
    single = client.get("/api/workbenches/alpha/export").content
    client.delete("/api/workbenches/alpha")

    r = client.post(
        "/api/archive/import",
        files={"file": ("a.tar.gz", single, "application/gzip")},
    )

    assert r.status_code == 200, r.text
    assert r.json()["imported"] == ["alpha"]
    assert client.get("/api/workbenches/alpha").status_code == 200


def test_archive_import_rejects_garbage(client: TestClient) -> None:
    r = client.post(
        "/api/archive/import",
        files={"file": ("x.tar.gz", b"not-a-tarball", "application/gzip")},
    )

    assert r.status_code == 400
