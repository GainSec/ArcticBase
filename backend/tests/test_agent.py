from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arctic_base.api.deps import get_storage
from arctic_base.main import app
from arctic_base.storage.filesystem import FilesystemStorage


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = FilesystemStorage(tmp_path / "data")
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_agent_landing_redirects_to_openapi(client: TestClient) -> None:
    r = client.get("/agent", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/openapi.json"


def test_agent_conventions_doc(client: TestClient) -> None:
    r = client.get("/api/agent/conventions")
    assert r.status_code == 200
    text = r.text
    # spot checks for the things OpenAPI can't express
    assert "window.workbench" in text
    assert "since_version" in text
    assert "approval-html" in text
    assert "--wb-" in text
    assert "self-contained" in text
    assert "layout:" in text


def test_agent_bootstrap_creates_workbench_with_checklist(client: TestClient) -> None:
    r = client.post(
        "/api/agent/bootstrap",
        json={"project_title": "TaskyTrack", "local_path": "/Users/x/code/tasky"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workbench"]["slug"] == "taskytrack"
    assert body["workbench"]["local_path"] == "/Users/x/code/tasky"
    assert body["workbench_url"].endswith("/wb/taskytrack")
    ids = [item["id"] for item in body["checklist"]]
    assert {"theme", "banner", "local_path", "tags", "memory_snippet"}.issubset(set(ids))
    assert len(body["next_steps"]) >= 1


def test_agent_bootstrap_respects_suggested_slug(client: TestClient) -> None:
    r = client.post(
        "/api/agent/bootstrap",
        json={"project_title": "TaskyTrack", "suggested_slug": "tt"},
    )
    assert r.json()["workbench"]["slug"] == "tt"


def test_agent_memory_snippet_claude(client: TestClient) -> None:
    client.post("/api/agent/bootstrap", json={"project_title": "TT", "suggested_slug": "tt"})
    r = client.get("/api/agent/claude-md-snippet?slug=tt&format=claude")
    assert r.status_code == 200
    text = r.text
    assert "tt" in text
    assert "/wb/tt" in text
    assert "approval-html" in text
    assert "window.workbench" in text
    assert "/api/agent/templates" in text


def test_agent_memory_snippet_agents(client: TestClient) -> None:
    client.post("/api/agent/bootstrap", json={"project_title": "TT", "suggested_slug": "tt"})
    r = client.get("/api/agent/claude-md-snippet?slug=tt&format=agents")
    assert r.status_code == 200
    text = r.text
    assert "/api/agent/conventions" in text
    assert "/wb/tt" in text


def test_agent_memory_snippet_unknown_slug_404(client: TestClient) -> None:
    r = client.get("/api/agent/claude-md-snippet?slug=nope&format=claude")
    assert r.status_code == 404


def test_agent_list_templates(client: TestClient) -> None:
    r = client.get("/api/agent/templates")
    assert r.status_code == 200
    body = r.json()
    ids = [t["id"] for t in body["templates"]]
    assert {"approval-questions", "qa-form", "pitch", "runbook"}.issubset(ids)
    for t in body["templates"]:
        assert t["suggested_kind"] in {"approval-html", "qa-form", "runbook"}
        assert t["when_to_use"]


def test_agent_get_template_unfilled(client: TestClient) -> None:
    r = client.get("/api/agent/templates/approval-questions")
    assert r.status_code == 200
    text = r.text
    # Self-contained essentials and theme references
    assert "<!DOCTYPE html>" in text
    assert "var(--wb-bg" in text
    assert "window.workbench" in text
    assert "localStorage" in text
    assert "Export JSON" in text
    # Placeholders left for the agent to fill
    assert "{{TITLE}}" in text
    assert "{{STATE_KEY}}" in text


def test_agent_get_template_filled(client: TestClient) -> None:
    r = client.get("/api/agent/templates/approval-questions?fill_title=Forge%20v1")
    assert r.status_code == 200
    text = r.text
    assert "{{TITLE}}" not in text
    assert "{{STATE_KEY}}" not in text
    assert "Forge v1" in text
    assert "ab-forge-v1-v1" in text or "ab-forge-v1" in text


def test_agent_get_template_404(client: TestClient) -> None:
    r = client.get("/api/agent/templates/does-not-exist")
    assert r.status_code == 404


def test_agent_self_test_passes(client: TestClient) -> None:
    r = client.post("/api/agent/self-test")
    assert r.status_code == 200
    body = r.json()
    assert body["pass"] is True
    names = [s["name"] for s in body["steps"]]
    assert names == [
        "create_workbench",
        "create_object",
        "write_content",
        "append_response",
        "read_back",
        "cleanup",
    ]
    for s in body["steps"]:
        assert s["ok"] is True
        assert s["elapsed_ms"] >= 0
    assert body["total_ms"] > 0


def test_conventions_doc_is_compact(client: TestClient) -> None:
    """The conventions doc must stay tight to avoid wasting agent context."""

    r = client.get("/api/agent/conventions")
    assert r.status_code == 200
    # Soft cap: enforce something well under typical CLAUDE.md size guidelines.
    assert len(r.text) < 12500, f"conventions doc grew to {len(r.text)} chars; tighten it"


def test_workbench_view_url_field(client: TestClient) -> None:
    """WorkbenchMeta exposes a view_url so agents can hand humans a working URL."""

    r = client.post("/api/agent/bootstrap", json={"project_title": "VU", "suggested_slug": "vu"})
    assert r.status_code == 200
    assert r.json()["workbench"]["view_url"] == "/wb/vu"

    r = client.get("/api/workbenches/vu")
    assert r.status_code == 200
    assert r.json()["view_url"] == "/wb/vu"

    r = client.get("/api/workbenches")
    assert r.status_code == 200
    assert any(w["view_url"] == "/wb/vu" for w in r.json())


def test_memory_snippet_global_no_slug(client: TestClient) -> None:
    """Without slug, the snippet returns generic instance-level guidance."""

    r = client.get("/api/agent/claude-md-snippet")
    assert r.status_code == 200
    assert "Arctic Base instance" in r.text
    # No slug-specific URL when no slug given.
    assert "/wb/" not in r.text or "POST /api/agent/bootstrap" in r.text


def test_workbench_path_typo_redirects(client: TestClient) -> None:
    """`/workbench/<slug>` and `/workbenches/<slug>` redirect to `/wb/<slug>`."""

    client.post("/api/agent/bootstrap", json={"project_title": "RD", "suggested_slug": "rd"})
    for prefix in ("workbench", "workbenches"):
        r = client.get(f"/{prefix}/rd", follow_redirects=False)
        assert r.status_code == 302, (prefix, r.status_code)
        assert r.headers["location"] == "/wb/rd", (prefix, r.headers)
