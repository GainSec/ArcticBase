// Minimal markdown → HTML renderer for inline use (workbench descriptions).
// Handles: **bold**, *italic*, `code`, [text](url), line breaks, and bullet lists (- item).
// HTML escapes everything else; no <script>/<iframe>/raw HTML pass-through.

export function renderMiniMd(src: string): string {
  if (!src) return "";
  const escaped = src
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const lines = escaped.split(/\r?\n/);
  const out: string[] = [];
  let inList = false;
  for (const raw of lines) {
    const m = raw.match(/^\s*-\s+(.*)$/);
    if (m) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inline(m[1])}</li>`);
    } else {
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      if (raw.trim()) out.push(`<p>${inline(raw)}</p>`);
    }
  }
  if (inList) out.push("</ul>");
  return out.join("\n");
}

function inline(s: string): string {
  // Code spans (do these first; they shouldn't be touched by the rest).
  s = s.replace(/`([^`]+)`/g, (_, t) => `<code>${t}</code>`);
  // Links [text](url) — only http(s) URLs allowed
  s = s.replace(/\[([^\]]+)\]\(((?:https?:)?\/\/[^\s)]+)\)/g, (_, t, u) => `<a href="${u}" target="_blank" rel="noopener">${t}</a>`);
  // Bold **x**
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic *x* (avoid matching inside ** by requiring non-* on both sides)
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  return s;
}
