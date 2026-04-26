"""Themed render endpoints.

`GET /api/workbenches/{slug}/objects/{oid}/render` returns:
  - For `kind=md`: themed HTML body fragment (CSS vars + rendered MD).
  - For `kind=html` or `approval-html`: the raw HTML with theme CSS vars and the
    `window.workbench` postMessage bridge injected near the top of the document.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from markdown_it import MarkdownIt

from arctic_base.api.deps import get_storage
from arctic_base.models import ObjectKind, Theme
from arctic_base.storage.filesystem import FilesystemStorage

router = APIRouter(prefix="/workbenches/{slug}/objects/{oid}", tags=["render"])

def _make_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True}).enable(
        ["table", "strikethrough"]
    )
    # Render `[x]` and `[ ]` as actual checkboxes inside list items.
    try:
        from mdit_py_plugins.tasklists import tasklists_plugin

        md.use(tasklists_plugin)
    except Exception:
        # Plugin missing — fall back to the default literal-text rendering.
        pass
    return md


_md = _make_md()


_DENSITY_PADDING = {"compact": "12px", "comfortable": "18px", "spacious": "28px"}
_DENSITY_GAP = {"compact": "8px", "comfortable": "14px", "spacious": "22px"}
_CORNER_RADIUS = {
    "sharp": "0",
    "soft": "0.25rem",
    "rounded": "var(--wb-rounded-md, 0.5rem)",
    "full": "var(--wb-rounded-lg, 1rem)",
}
_SHADOW_VALUE = {
    "hard-offset": "4px 4px 0 #000",
    "soft": "0 6px 18px rgba(0, 0, 0, 0.35)",
    "glow": "0 0 18px var(--wb-accent)",
    "none": "none",
}


def build_theme_style_block(theme: Theme, scope: str = ":root") -> str:
    decls: list[str] = []
    for k, v in theme.tokens.core.items():
        decls.append(f"  --wb-{k}: {v};")
    for k, v in theme.tokens.rounded.items():
        decls.append(f"  --wb-rounded-{k}: {v};")
    for k, v in theme.tokens.spacing.items():
        decls.append(f"  --wb-space-{k}: {v};")
    for k, v in theme.tokens.custom.items():
        decls.append(f"  --wb-{k}: {v};")
    for name, style in theme.tokens.typography.items():
        if style.fontFamily:
            decls.append(f"  --wb-font-{name}: {style.fontFamily};")
        if style.fontSize:
            decls.append(f"  --wb-font-size-{name}: {style.fontSize};")
        if style.fontWeight:
            decls.append(f"  --wb-font-weight-{name}: {style.fontWeight};")
        if style.lineHeight:
            decls.append(f"  --wb-line-height-{name}: {style.lineHeight};")
        if style.letterSpacing:
            decls.append(f"  --wb-letter-spacing-{name}: {style.letterSpacing};")
    # Layout — derived to concrete CSS values so consumers don't have to reason about token names.
    layout = theme.tokens.layout
    if layout.density and layout.density in _DENSITY_PADDING:
        decls.append(f"  --wb-layout-padding: {_DENSITY_PADDING[layout.density]};")
        decls.append(f"  --wb-layout-gap: {_DENSITY_GAP[layout.density]};")
    if layout.corners and layout.corners in _CORNER_RADIUS:
        decls.append(f"  --wb-card-radius: {_CORNER_RADIUS[layout.corners]};")
    if layout.shadow and layout.shadow in _SHADOW_VALUE:
        decls.append(f"  --wb-card-shadow: {_SHADOW_VALUE[layout.shadow]};")
    body = "\n".join(decls)
    # The trailing rule provides workbench-themed defaults for `html`/`body`. Document styles can
    # override (they're parsed after this injected block). Authors who set their own backgrounds
    # are unaffected.
    return (
        f"<style data-arctic-base=\"theme\">\n{scope} {{\n{body}\n}}\n"
        "html, body { background: var(--wb-bg); color: var(--wb-ink); "
        "font-family: var(--wb-font-body, system-ui, sans-serif); }\n"
        "</style>"
    )


_BRIDGE_SCRIPT_TEMPLATE = r"""<script data-arctic-base="bridge">
(function () {
  var CTX = __CTX__;
  function send(type, payload) {
    return new Promise(function (resolve) {
      var rid = Math.random().toString(36).slice(2);
      function onMsg(ev) {
        if (!ev.data || ev.data.__ab !== rid) return;
        window.removeEventListener('message', onMsg);
        resolve(ev.data.result);
      }
      window.addEventListener('message', onMsg);
      window.parent.postMessage({ __ab: rid, type: type, payload: payload, ctx: CTX }, '*');
    });
  }
  window.workbench = {
    context: CTX,
    theme: __THEME__,
    save: function (k, v) { return send('save', { key: k, value: v }); },
    saveAll: function (state) { return send('saveAll', state); },
    load: function (k) { return send('load', { key: k }); },
    loadAll: function () { return send('loadAll', {}); },
    submit: function (state) { return send('submit', state); },
    onRemoteChange: function (cb) {
      // The parent SPA polls /responses?since_version=N for this object and forwards new events
      // to the iframe via postMessage with __ab_remote: true.
      function handler(ev) {
        if (!ev.data || ev.data.__ab_remote !== true) return;
        cb(ev.data.event);
      }
      window.addEventListener('message', handler);
      // Tell the parent we'd like remote-change events.
      window.parent.postMessage({ __ab_remote_subscribe: true, ctx: CTX }, '*');
      return function () {
        window.removeEventListener('message', handler);
        window.parent.postMessage({ __ab_remote_unsubscribe: true, ctx: CTX }, '*');
      };
    }
  };
})();
</script>"""


def build_bridge_script(slug: str, oid: str, kind: str, title: str, created_at: str, theme: Theme) -> str:
    import json as _json

    ctx = {
        "workbench": slug,
        "object": oid,
        "objectKind": kind,
        "title": title,
        "createdAt": created_at,
    }
    theme_dict = {
        "tokens": {
            "core": dict(theme.tokens.core),
            "rounded": dict(theme.tokens.rounded),
            "spacing": dict(theme.tokens.spacing),
            "custom": dict(theme.tokens.custom),
            "typography": {
                k: v.model_dump(exclude_none=True) for k, v in theme.tokens.typography.items()
            },
        },
        "prose": theme.prose,
    }
    return (
        _BRIDGE_SCRIPT_TEMPLATE
        .replace("__CTX__", _json.dumps(ctx))
        .replace("__THEME__", _json.dumps(theme_dict))
    )


def _inject_into_html(raw_html: str, head_blocks: list[str]) -> str:
    """Inject theme + bridge near the start of the document.

    Insertion strategy:
      1. After `<head>` if present.
      2. Otherwise after `<html>` or after `<!DOCTYPE>`.
      3. Otherwise prepend.
    """

    payload = "\n".join(head_blocks) + "\n"
    lower = raw_html.lower()
    head_idx = lower.find("<head>")
    if head_idx != -1:
        end = head_idx + len("<head>")
        return raw_html[:end] + "\n" + payload + raw_html[end:]
    html_idx = lower.find("<html")
    if html_idx != -1:
        gt = lower.find(">", html_idx)
        if gt != -1:
            return raw_html[: gt + 1] + "\n" + payload + raw_html[gt + 1 :]
    return payload + raw_html


@router.get("/render", operation_id="renderObject")
def render_object(
    slug: str,
    oid: str,
    storage: Annotated[FilesystemStorage, Depends(get_storage)],
    with_runtime: bool = True,
) -> Response:
    meta = storage.get_object(slug, oid)
    theme = storage.get_theme(slug)
    style_block = build_theme_style_block(theme)
    if meta.kind == ObjectKind.md:
        raw, _ = storage.get_object_content(slug, oid)
        text = raw.decode("utf-8", errors="replace")
        html_body = _md.render(text)
        page = (
            "<!DOCTYPE html><html><head>"
            f"{style_block}"
            "<style>"
            "body{margin:0;padding:var(--wb-space-margin,32px);"
            "background:var(--wb-bg);color:var(--wb-ink);"
            "font-family:var(--wb-font-body,system-ui);}"
            "a{color:var(--wb-accent);}"
            "code,pre{font-family:var(--wb-font-mono,monospace);}"
            "</style></head><body>"
            f"{html_body}"
            "</body></html>"
        )
        return HTMLResponse(content=page)
    if meta.kind in (ObjectKind.html, ObjectKind.approval_html, ObjectKind.qa_form):
        raw, _ = storage.get_object_content(slug, oid)
        text = raw.decode("utf-8", errors="replace")
        head_blocks = [style_block]
        if with_runtime:
            head_blocks.append(
                build_bridge_script(
                    slug=slug,
                    oid=oid,
                    kind=meta.kind.value,
                    title=meta.title,
                    created_at=meta.created_at.isoformat(),
                    theme=theme,
                )
            )
        return HTMLResponse(content=_inject_into_html(text, head_blocks))
    if meta.kind == ObjectKind.image:
        # Themed wrapper: shows the image inline against the workbench background.
        content_url = f"/api/workbenches/{slug}/objects/{oid}/content"
        page = (
            "<!DOCTYPE html><html><head>"
            f"{style_block}"
            "<style>"
            "body{margin:0;display:grid;place-items:center;min-height:100vh;"
            "background:var(--wb-bg);color:var(--wb-ink);"
            "font-family:var(--wb-font-body,system-ui);}"
            "img{max-width:100vw;max-height:100vh;object-fit:contain;}"
            ".caption{position:fixed;bottom:12px;left:12px;font-size:11px;"
            "letter-spacing:.1em;text-transform:uppercase;color:var(--wb-muted);}"
            "</style></head><body>"
            f'<img src="{content_url}" alt="{meta.title}"/>'
            f'<div class="caption">// {meta.filename or meta.id}</div>'
            "</body></html>"
        )
        return HTMLResponse(content=page)
    if meta.kind == ObjectKind.file:
        # Generic file: redirect to /content with attachment headers.
        return Response(
            status_code=302,
            headers={"location": f"/api/workbenches/{slug}/objects/{oid}/content"},
        )
    # Unknown kind — should not happen given the enum.
    return Response(status_code=415, content=f"render not supported for kind={meta.kind}")
