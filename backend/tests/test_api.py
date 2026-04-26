from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arctic_base.api.deps import get_storage
from arctic_base.main import app
from arctic_base.storage.filesystem import FilesystemStorage

VALID_THEME = """\
---
name: API Test Theme
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
rounded: { sm: '0.25rem', md: '0.5rem', lg: '1rem' }
spacing: { unit: '8px', gutter: '24px', margin: '32px' }
custom: { pop: '#f0c' }
---

# Hi
"""


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = FilesystemStorage(tmp_path / "data")
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_workbench(client: TestClient) -> None:
    r = client.post("/api/workbenches", json={"title": "TaskyTrack"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "taskytrack"
    assert body["title"] == "TaskyTrack"


def test_workbench_already_exists_409(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    r = client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    assert r.status_code == 409


def test_workbench_get_404(client: TestClient) -> None:
    r = client.get("/api/workbenches/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_workbench_patch(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "Old", "slug": "x"})
    r = client.patch("/api/workbenches/x", json={"title": "New", "tags": ["a"]})
    assert r.status_code == 200
    assert r.json()["title"] == "New"


def test_workbench_archive_and_restore(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "y"})
    archive = client.delete("/api/workbenches/y").json()["archive"]
    assert archive in [t["archive"] for t in client.get("/api/workbenches/_trash/list").json()]
    r = client.post("/api/workbenches/_trash/restore", json={"archive": archive})
    assert r.status_code == 200
    assert r.json()["slug"] == "y"


def test_theme_put_get(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    r = client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tokens"]["core"]["accent"] == "#06d"

    raw_r = client.get("/api/workbenches/t/theme/raw")
    assert "API Test Theme" in raw_r.text


def test_theme_invalid_returns_422(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    bad = VALID_THEME.replace("accent: '#06d'", "")
    r = client.put("/api/workbenches/t/theme", json={"raw": bad})
    assert r.status_code == 422


def test_object_lifecycle_and_content(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})

    # create via JSON, then put content
    r = client.post(
        "/api/workbenches/t/objects",
        json={"kind": "md", "title": "Hello", "drawer": "docs"},
    )
    assert r.status_code == 201, r.text
    oid = r.json()["id"]

    pr = client.put(
        f"/api/workbenches/t/objects/{oid}/content",
        content=b"# Hi\n\nWorld.",
    )
    assert pr.status_code == 200
    etag1 = pr.json()["etag"]

    # stale write rejected
    pr2 = client.put(
        f"/api/workbenches/t/objects/{oid}/content",
        content=b"v3",
        headers={"If-Match": "sha256:bogus"},
    )
    assert pr2.status_code == 412

    # correct etag accepted
    pr3 = client.put(
        f"/api/workbenches/t/objects/{oid}/content",
        content=b"v3",
        headers={"If-Match": etag1},
    )
    assert pr3.status_code == 200

    # GET content
    gr = client.get(f"/api/workbenches/t/objects/{oid}/content")
    assert gr.status_code == 200
    assert gr.content == b"v3"

    # If-None-Match round-trip
    et = gr.headers["etag"]
    nr = client.get(
        f"/api/workbenches/t/objects/{oid}/content", headers={"If-None-Match": et}
    )
    assert nr.status_code == 304


def test_object_multipart_upload(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    files = {
        "meta": (
            None,
            '{"kind":"file","title":"banner","drawer":"files"}',
            "application/json",
        ),
        "file": ("hello.bin", b"\x00\x01\x02", "application/octet-stream"),
    }
    r = client.post("/api/workbenches/t/objects", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "hello.bin"
    assert body["size_bytes"] == 3


def test_response_lifecycle(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "qa-form", "title": "Q"}
    ).json()
    oid = o["id"]

    # autosave doesn't bump state_version
    r1 = client.post(
        f"/api/workbenches/t/objects/{oid}/responses",
        json={"kind": "autosave", "payload": {"draft": 1}},
    )
    assert r1.status_code == 201
    assert r1.json()["version"] == 1

    # submit bumps state_version
    r2 = client.post(
        f"/api/workbenches/t/objects/{oid}/responses",
        json={"kind": "submit", "payload": {"final": True}},
    )
    assert r2.json()["version"] == 2

    latest = client.get(f"/api/workbenches/t/objects/{oid}/responses/latest")
    assert latest.json()["payload"] == {"final": True}

    # since_version filter
    f = client.get(
        f"/api/workbenches/t/objects/{oid}/responses?since_version=1"
    ).json()
    assert [e["version"] for e in f] == [2]

    meta = client.get(f"/api/workbenches/t/objects/{oid}").json()
    assert meta["state_version"] == 1  # only one submit


def test_render_md(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "md", "title": "Doc"}
    ).json()
    oid = o["id"]
    client.put(
        f"/api/workbenches/t/objects/{oid}/content", content=b"# Hello\n\nworld"
    )
    r = client.get(f"/api/workbenches/t/objects/{oid}/render")
    assert r.status_code == 200
    assert "<h1>Hello</h1>" in r.text
    assert "--wb-bg" in r.text
    assert "--wb-accent" in r.text


def test_get_workbench_bumps_last_accessed_at(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "ax"})
    initial = client.get("/api/workbenches/ax").json()
    first = initial["last_accessed_at"]
    assert first is not None
    # Second GET should bump it forward.
    second = client.get("/api/workbenches/ax").json()
    assert second["last_accessed_at"] >= first


def test_default_workbench_order_is_last_accessed(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "A", "slug": "a"})
    client.post("/api/workbenches", json={"title": "B", "slug": "b"})
    client.post("/api/workbenches", json={"title": "C", "slug": "c"})
    # Touch them in order: a, c, b. Expect listing in [b, c, a] order (most-recent first).
    client.get("/api/workbenches/a")
    client.get("/api/workbenches/c")
    client.get("/api/workbenches/b")
    listed = [w["slug"] for w in client.get("/api/workbenches").json()]
    assert listed == ["b", "c", "a"]


def test_workbench_manual_reorder(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "A", "slug": "a"})
    client.post("/api/workbenches", json={"title": "B", "slug": "b"})
    client.post("/api/workbenches", json={"title": "C", "slug": "c"})
    r = client.post("/api/workbenches/_reorder", json={"slugs": ["c", "a", "b"]})
    assert r.status_code == 204
    listed = [w["slug"] for w in client.get("/api/workbenches").json()]
    assert listed == ["c", "a", "b"]
    # Empty body clears the override.
    client.post("/api/workbenches/_reorder", json={"slugs": []})
    # Without override, default sort returns. Touch order (a, b, c was last) so:
    listed2 = [w["slug"] for w in client.get("/api/workbenches").json()]
    assert set(listed2) == {"a", "b", "c"}  # any order is fine, just no longer sticky


def test_object_pin_floats_to_top(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "pn"})
    a = client.post("/api/workbenches/pn/objects", json={"kind": "md", "title": "a"}).json()
    b = client.post("/api/workbenches/pn/objects", json={"kind": "md", "title": "b"}).json()
    c = client.post("/api/workbenches/pn/objects", json={"kind": "md", "title": "c"}).json()
    # Pin c. Expect [c, a, b].
    client.patch(f"/api/workbenches/pn/objects/{c['id']}", json={"pinned": True})
    listed = [o["title"] for o in client.get("/api/workbenches/pn/objects").json()]
    assert listed == ["c", "a", "b"]


def test_object_archive_hidden_by_default(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "ar"})
    a = client.post("/api/workbenches/ar/objects", json={"kind": "md", "title": "a"}).json()
    b = client.post("/api/workbenches/ar/objects", json={"kind": "md", "title": "b"}).json()
    client.patch(f"/api/workbenches/ar/objects/{a['id']}", json={"archived": True})
    # Default list: only b.
    listed = [o["title"] for o in client.get("/api/workbenches/ar/objects").json()]
    assert listed == ["b"]
    # include_archived=true: both.
    full = [o["title"] for o in
            client.get("/api/workbenches/ar/objects?include_archived=true").json()]
    assert set(full) == {"a", "b"}


def test_runbook_kind_round_trip(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "rb"})
    o = client.post(
        "/api/workbenches/rb/objects",
        json={"kind": "runbook", "title": "Comms module rollout", "drawer": "runbooks"},
    ).json()
    assert o["kind"] == "runbook"
    runbook = {
        "title": "Comms rollout",
        "steps": [
            {"id": "s1", "title": "Wire WebSocket primitive", "status": "done"},
            {"id": "s2", "title": "Per-titan keys", "status": "todo"},
            {"id": "s3", "title": "Ship to staging", "status": "blocked", "blocker": "Tailscale ACL"},
        ],
    }
    import json as _j
    client.put(
        f"/api/workbenches/rb/objects/{o['id']}/content",
        content=_j.dumps(runbook).encode(),
        headers={"content-type": "application/json"},
    )
    fetched = client.get(f"/api/workbenches/rb/objects/{o['id']}/content").json()
    assert fetched["steps"][2]["blocker"] == "Tailscale ACL"


def test_object_reorder(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "ot"})
    o1 = client.post("/api/workbenches/ot/objects", json={"kind": "md", "title": "1"}).json()
    o2 = client.post("/api/workbenches/ot/objects", json={"kind": "md", "title": "2"}).json()
    o3 = client.post("/api/workbenches/ot/objects", json={"kind": "md", "title": "3"}).json()
    r = client.post(
        "/api/workbenches/ot/objects/_reorder",
        json={"ids": [o3["id"], o1["id"], o2["id"]]},
    )
    assert r.status_code == 204
    listed = [o["title"] for o in client.get("/api/workbenches/ot/objects").json()]
    assert listed == ["3", "1", "2"]


def test_get_object_bumps_workbench_last_accessed(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "wo"})
    o = client.post("/api/workbenches/wo/objects", json={"kind": "md", "title": "x"}).json()
    wb_before = client.get("/api/workbenches/wo").json()["last_accessed_at"]
    client.get(f"/api/workbenches/wo/objects/{o['id']}")
    wb_after = client.get("/api/workbenches/wo").json()["last_accessed_at"]
    assert wb_after >= wb_before


def test_workbench_create_bootstraps_default_theme(client: TestClient) -> None:
    r = client.post("/api/workbenches", json={"title": "Auto", "slug": "auto"})
    assert r.status_code == 201
    # Theme should be readable immediately — no manual PUT needed.
    t = client.get("/api/workbenches/auto/theme")
    assert t.status_code == 200
    assert t.json()["tokens"]["core"]["bg"]


def test_workbench_custom_fields_round_trip(client: TestClient) -> None:
    r = client.post(
        "/api/workbenches",
        json={
            "title": "C",
            "slug": "cf",
            "custom_fields": {"deploy_cmd": "./deploy.sh", "secrets": "/tmp/.env"},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["custom_fields"] == {"deploy_cmd": "./deploy.sh", "secrets": "/tmp/.env"}
    # Patch to add a key + change a value.
    p = client.patch(
        "/api/workbenches/cf",
        json={"custom_fields": {"deploy_cmd": "make deploy", "ci_url": "https://ci.example/cf"}},
    ).json()
    assert p["custom_fields"] == {"deploy_cmd": "make deploy", "ci_url": "https://ci.example/cf"}


def test_workbench_ip_field_round_trip(client: TestClient) -> None:
    r = client.post(
        "/api/workbenches",
        json={"title": "I", "slug": "ipw", "ip": "192.168.13.37", "url": "https://x.example"},
    )
    assert r.json()["ip"] == "192.168.13.37"
    p = client.patch("/api/workbenches/ipw", json={"ip": "10.0.0.5"}).json()
    assert p["ip"] == "10.0.0.5"


def test_md_renders_task_lists(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "mdtl"})
    o = client.post(
        "/api/workbenches/mdtl/objects", json={"kind": "md", "title": "Doc"}
    ).json()
    client.put(
        f"/api/workbenches/mdtl/objects/{o['id']}/content",
        content=b"- [x] done\n- [ ] todo\n",
    )
    r = client.get(f"/api/workbenches/mdtl/objects/{o['id']}/render")
    body = r.text
    # Plugin renders each as <input type="checkbox" ...>
    assert body.count("type=\"checkbox\"") >= 2 or body.count("input checkbox") >= 1
    # The original literal `[x]` should NOT survive in rendered output
    assert "[x]" not in body


def test_workbench_banner_generated_when_null(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "Banner Test", "slug": "bt"})
    r = client.get("/api/workbenches/bt/banner")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"BANNER TEST" in r.content
    assert b"SECTOR_BT" in r.content


def test_workbench_snapshot_lifecycle(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "S", "slug": "snp"})
    client.put("/api/workbenches/snp/theme", json={"raw": VALID_THEME})
    o = client.post("/api/workbenches/snp/objects", json={"kind": "md", "title": "x"}).json()
    client.put(f"/api/workbenches/snp/objects/{o['id']}/content", content=b"# v1")

    snap = client.post("/api/workbenches/snp/snapshot", json={"label": "before-edit"}).json()
    assert "before-edit" in snap["name"]
    assert snap["size_bytes"] > 0
    listed = client.get("/api/workbenches/snp/snapshots").json()
    assert any(s["name"] == snap["name"] for s in listed)

    # Mutate the workbench
    client.put(f"/api/workbenches/snp/objects/{o['id']}/content", content=b"# v2 (different)")

    # Restore the snapshot to a new slug
    r = client.post(
        f"/api/workbenches/snp/snapshots/{snap['name']}/restore",
        json={"new_slug": "snp-restored"},
    )
    assert r.status_code == 200
    # The restored object should have v1 content
    rest_objs = client.get("/api/workbenches/snp-restored/objects").json()
    rest_oid = rest_objs[0]["id"]
    rc = client.get(f"/api/workbenches/snp-restored/objects/{rest_oid}/content")
    assert rc.content == b"# v1"

    # Download
    d = client.get(f"/api/workbenches/snp/snapshots/{snap['name']}/download")
    assert d.status_code == 200
    assert d.content[:2] == b"\x1f\x8b"  # gzip magic

    # Delete
    dl = client.delete(f"/api/workbenches/snp/snapshots/{snap['name']}")
    assert dl.status_code == 204
    assert client.get("/api/workbenches/snp/snapshots").json() == []


def test_audit_log_records_mutations(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "A", "slug": "auw"})
    client.put("/api/workbenches/auw/theme", json={"raw": VALID_THEME})
    o = client.post("/api/workbenches/auw/objects", json={"kind": "md", "title": "x"}).json()
    client.put(f"/api/workbenches/auw/objects/{o['id']}/content", content=b"# hi")
    client.patch(f"/api/workbenches/auw/objects/{o['id']}", json={"pinned": True})
    client.post(
        f"/api/workbenches/auw/objects/{o['id']}/responses",
        json={"kind": "submit", "payload": {"x": 1}},
    )
    audit = client.get("/api/workbenches/auw/audit").json()
    events = [e["event"] for e in audit["events"]]
    assert "theme.put" in events
    assert "object.create" in events
    assert "object.content_write" in events
    assert "object.update" in events
    assert "response.append" in events

    # Download form
    d = client.get("/api/workbenches/auw/audit?download=true")
    assert d.status_code == 200
    assert d.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in d.headers["content-disposition"]


def test_static_export_zip(client: TestClient) -> None:
    import io as _io
    import zipfile as _zip

    client.post("/api/workbenches", json={"title": "S", "slug": "se"})
    client.put("/api/workbenches/se/theme", json={"raw": VALID_THEME})
    o = client.post("/api/workbenches/se/objects", json={"kind": "md", "title": "Doc"}).json()
    client.put(f"/api/workbenches/se/objects/{o['id']}/content", content=b"# Hello\n\n- [x] done\n")

    r = client.get("/api/workbenches/se/static-export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    z = _zip.ZipFile(_io.BytesIO(r.content))
    names = z.namelist()
    assert any(n.endswith("/index.html") for n in names)
    assert any(n.endswith("/manifest.json") for n in names)
    assert any(n.endswith("/style.css") for n in names)
    assert any(n.startswith("se/md/") and n.endswith(".html") for n in names)
    # The MD page should be readable HTML, no API dependency.
    md_path = [n for n in names if n.startswith("se/md/")][0]
    md_html = z.read(md_path).decode("utf-8")
    assert "<h1>Hello</h1>" in md_html


def test_workbench_export_returns_targz(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "X", "slug": "x"})
    client.put("/api/workbenches/x/theme", json={"raw": VALID_THEME})
    r = client.get("/api/workbenches/x/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.tar.gz"')
    # gzip magic bytes
    assert r.content[:2] == b"\x1f\x8b"


def test_workbench_duplicate(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "Original", "slug": "orig"})
    client.put("/api/workbenches/orig/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/orig/objects", json={"kind": "md", "title": "Doc"}
    ).json()
    client.put(f"/api/workbenches/orig/objects/{o['id']}/content", content=b"# Hi")
    # Submit a response so state_version > 0 on the original
    client.post(
        f"/api/workbenches/orig/objects/{o['id']}/responses",
        json={"kind": "submit", "payload": {"x": 1}},
    )
    # Duplicate
    dup = client.post("/api/workbenches/orig/duplicate", json={}).json()
    assert dup["slug"] == "orig-copy"
    assert dup["title"] == "Original (copy)"
    # Cloned object exists with state_version reset
    cloned_objs = client.get("/api/workbenches/orig-copy/objects").json()
    assert len(cloned_objs) == 1
    assert cloned_objs[0]["state_version"] == 0
    # Cloned object content matches
    cc = client.get(f"/api/workbenches/orig-copy/objects/{cloned_objs[0]['id']}/content")
    assert cc.content == b"# Hi"
    # Cloned object has no responses
    rs = client.get(
        f"/api/workbenches/orig-copy/objects/{cloned_objs[0]['id']}/responses"
    ).json()
    assert rs == []


def test_workbench_duplicate_explicit_slug(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    dup = client.post("/api/workbenches/t/duplicate", json={"new_slug": "t2"}).json()
    assert dup["slug"] == "t2"


def test_trash_download_and_purge(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "Z", "slug": "z"})
    archive = client.delete("/api/workbenches/z").json()["archive"]
    # Download
    r = client.get(f"/api/workbenches/_trash/{archive}/download")
    assert r.status_code == 200
    assert r.content[:2] == b"\x1f\x8b"
    assert "attachment" in r.headers["content-disposition"]
    # Purge
    p = client.delete(f"/api/workbenches/_trash/{archive}")
    assert p.status_code == 204
    # Trash list now empty
    trash = client.get("/api/workbenches/_trash/list").json()
    assert all(t["archive"] != archive for t in trash)


def test_responses_latest_payload_bare(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "qa-form", "title": "Q"}
    ).json()
    # Empty -> {}
    r = client.get(f"/api/workbenches/t/objects/{o['id']}/responses/latest/payload")
    assert r.status_code == 200
    assert r.json() == {}
    # Submit
    client.post(
        f"/api/workbenches/t/objects/{o['id']}/responses",
        json={"kind": "submit", "payload": {"answer": "yes", "notes": "ok"}},
    )
    r = client.get(f"/api/workbenches/t/objects/{o['id']}/responses/latest/payload")
    assert r.json() == {"answer": "yes", "notes": "ok"}


def test_responses_export(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "qa-form", "title": "Q"}
    ).json()
    client.post(
        f"/api/workbenches/t/objects/{o['id']}/responses",
        json={"kind": "autosave", "payload": {"draft": 1}},
    )
    client.post(
        f"/api/workbenches/t/objects/{o['id']}/responses",
        json={"kind": "submit", "payload": {"final": True}},
    )
    r = client.get(f"/api/workbenches/t/objects/{o['id']}/responses/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "attachment" in r.headers["content-disposition"]
    body = r.json()
    assert body["slug"] == "t"
    assert body["object_id"] == o["id"]
    assert [e["kind"] for e in body["events"]] == ["autosave", "submit"]
    assert body["events"][1]["payload"] == {"final": True}


def test_render_image_returns_themed_wrapper(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "ti"})
    o = client.post(
        "/api/workbenches/ti/objects",
        json={"kind": "image", "title": "Pic", "filename": "x.png", "mime": "image/png"},
    ).json()
    client.put(f"/api/workbenches/ti/objects/{o['id']}/content", content=b"\x89PNGfake")
    r = client.get(f"/api/workbenches/ti/objects/{o['id']}/render")
    assert r.status_code == 200
    body = r.text
    assert "<img" in body
    assert "data-arctic-base=\"theme\"" in body
    assert f"/objects/{o['id']}/content" in body


def test_render_file_redirects(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "tf"})
    o = client.post(
        "/api/workbenches/tf/objects",
        json={"kind": "file", "title": "F", "filename": "x.bin"},
    ).json()
    client.put(f"/api/workbenches/tf/objects/{o['id']}/content", content=b"abc")
    r = client.get(f"/api/workbenches/tf/objects/{o['id']}/render", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith(f"/objects/{o['id']}/content")


def test_agent_activity_endpoint(client: TestClient) -> None:
    # Generate some activity.
    client.post("/api/workbenches", json={"title": "A", "slug": "act"})
    client.get("/api/workbenches/act")
    r = client.get("/api/agent/activity")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert len(body["events"]) >= 2
    # Newest-first ordering
    paths = [e["path"] for e in body["events"]]
    assert "/api/workbenches/act" in paths
    assert "/api/workbenches" in paths
    # Activity endpoint itself should NOT appear (excluded).
    assert "/api/agent/activity" not in paths


def test_render_qa_form_themed(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "qa-form", "title": "Q"}
    ).json()
    oid = o["id"]
    raw = b"<!DOCTYPE html><html><head><title>X</title></head><body><p>q</p></body></html>"
    client.put(f"/api/workbenches/t/objects/{oid}/content", content=raw)
    r = client.get(f"/api/workbenches/t/objects/{oid}/render")
    assert r.status_code == 200
    body = r.text
    assert "data-arctic-base=\"theme\"" in body
    assert "data-arctic-base=\"bridge\"" in body
    assert "window.workbench" in body


def test_render_html_with_bridge_injection(client: TestClient) -> None:
    client.post("/api/workbenches", json={"title": "T", "slug": "t"})
    client.put("/api/workbenches/t/theme", json={"raw": VALID_THEME})
    o = client.post(
        "/api/workbenches/t/objects", json={"kind": "approval-html", "title": "Doc"}
    ).json()
    oid = o["id"]
    raw = b"<!DOCTYPE html><html><head><title>X</title></head><body><p>hi</p></body></html>"
    client.put(f"/api/workbenches/t/objects/{oid}/content", content=raw)
    r = client.get(f"/api/workbenches/t/objects/{oid}/render")
    assert r.status_code == 200
    body = r.text
    assert "data-arctic-base=\"theme\"" in body
    assert "data-arctic-base=\"bridge\"" in body
    assert "window.workbench" in body
    # bridge before <title>
    assert body.index("data-arctic-base=\"bridge\"") < body.index("<title>")
