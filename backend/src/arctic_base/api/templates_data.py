"""HTML templates served to agents via /api/agent/templates.

Each template is a self-contained HTML doc that:

- references `--wb-*` CSS variables so it auto-themes when served from a workbench;
- bakes in fallback values so it still works opened standalone (per the review-HTML rules);
- includes `window.workbench` feature-detection so state mirrors to the API when present and to
  `localStorage` always;
- exposes a JSON-export button for the canonical recorded state.

Agents are expected to fetch the template, replace the marked sections (questions, prose, etc.),
and upload the result via POST /api/workbenches/{slug}/objects.
"""

from __future__ import annotations

from typing import TypedDict


class TemplateMeta(TypedDict):
    id: str
    name: str
    description: str
    suggested_kind: str
    when_to_use: str


# ---------- approval-questions: multi-question decision doc ----------
APPROVAL_QUESTIONS = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  /* Theme variables. References to --wb-* auto-pick up the workbench theme when served via Arctic
     Base; the literal fallbacks make the file work standalone too. */
  :root {
    --bg: var(--wb-bg, #f7f4ee);
    --paper: var(--wb-surface, #ffffff);
    --ink: var(--wb-ink, #1a1a1a);
    --muted: var(--wb-muted, #5c5c5c);
    --accent: var(--wb-accent, #7a1f1f);
    --accent-2: var(--wb-accent-2, #2a5562);
    --rule: var(--wb-rule, #d9d3c7);
    --rec: var(--wb-success, #2c6e3a);
    --code-bg: var(--wb-bg, #f0ece4);
    --rounded: var(--wb-rounded-md, 4px);
    --space: var(--wb-space-gutter, 24px);
    --font-body: var(--wb-font-body, "Charter","Palatino","Georgia",serif);
    --font-mono: var(--wb-font-mono, "JetBrains Mono","Menlo",monospace);
  }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); }
  body { font-family: var(--font-body); font-size: 16px; line-height: 1.55; }
  .wrap { max-width: 920px; margin: 0 auto; padding: 32px 28px 96px; background: var(--paper); }
  header { border-bottom: 2px solid var(--ink); padding-bottom: 14px; margin-bottom: 20px; }
  header h1 { font-size: 22px; margin: 0 0 4px; }
  header .sub { color: var(--muted); font-size: 13px; font-style: italic; }
  .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; padding: 12px 16px;
             margin: 12px 0 24px; background: var(--bg); border-left: 3px solid var(--accent-2);
             font-size: 13px; }
  .toolbar .progress { font-weight: 600; }
  .toolbar .progress.complete { color: var(--rec); }
  .toolbar button { font: inherit; cursor: pointer; padding: 6px 12px; border: 1px solid var(--rule);
                    background: var(--paper); border-radius: var(--rounded); }
  .toolbar button:hover { border-color: var(--accent-2); }
  .ack-bar { margin: 28px 0 0; background: var(--bg); padding: 14px 18px;
             border-left: 3px solid var(--accent); }
  .ack-bar button.ack-all { background: #d8ead2; color: var(--rec); border-color: var(--rec);
                            font-weight: 600; padding: 8px 16px; cursor: pointer; }
  article.q { margin: 28px 0 0; border-top: 1px solid var(--rule); padding-top: 22px; }
  article.q h2 { font-size: 17px; margin: 0 0 4px; }
  article.q .qmeta { font-size: 12.5px; color: var(--muted); font-style: italic; margin: 0 0 12px; }
  .options { display: grid; gap: 8px; margin: 10px 0; }
  .option { padding: 10px 14px; border: 1px solid var(--rule); border-radius: var(--rounded);
            background: var(--paper); display: block; }
  .option label { display: flex; gap: 10px; cursor: pointer; align-items: flex-start; }
  .option .opt-title { font-weight: 600; font-size: 14px; margin: 0 0 4px; }
  .option .opt-body { font-size: 13.5px; color: var(--ink); }
  .option.recommended { border-left: 3px solid var(--rec); }
  .option.recommended .rec-badge { background: #d8ead2; color: var(--rec); padding: 1px 7px;
                                    border-radius: 10px; font-size: 10px; letter-spacing: 0.05em;
                                    text-transform: uppercase; vertical-align: middle; margin-left: 6px; }
  .option:has(input:checked) { background: var(--bg); border-color: var(--accent); }
  code { font-family: var(--font-mono); background: var(--code-bg); font-size: 12.5px;
         padding: 1px 4px; border-radius: 2px; }
  .notes { margin-top: 12px; }
  .notes label { font-size: 11px; color: var(--muted); letter-spacing: 0.06em;
                 text-transform: uppercase; display: block; margin-bottom: 4px; }
  .notes textarea { width: 100%; box-sizing: border-box; padding: 8px 10px; min-height: 44px;
                    border: 1px solid var(--rule); border-radius: var(--rounded);
                    font-family: inherit; font-size: 13px; background: var(--paper);
                    resize: vertical; }
  .submit-bar { margin-top: 32px; padding: 14px 18px; background: var(--bg);
                border-left: 3px solid var(--rec); display: flex; gap: 12px; align-items: center; }
  .submit-bar button.submit { background: var(--rec); color: white; border: none; padding: 8px 18px;
                              border-radius: var(--rounded); font-weight: 600; cursor: pointer; }
  footer { margin-top: 56px; padding-top: 14px; border-top: 1px solid var(--rule); font-size: 12px;
           color: var(--muted); font-style: italic; text-align: center; }
  @media (max-width: 760px) { .wrap { padding: 20px 14px 64px; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{{TITLE}}</h1>
    <div class="sub">{{SUBTITLE}}</div>
  </header>

  <div class="toolbar">
    <span class="progress" id="progress">0 / 0 answered</span>
    <span style="margin-left:auto"></span>
    <button id="export">Export JSON</button>
    <button id="reset" style="border-color:#c0a0a0;color:#a04040;">Reset</button>
  </div>

  <div class="ack-bar">
    <button class="ack-all" id="ack-all">Ack all defaults</button>
    <span style="margin-left:8px;font-size:13px;color:var(--muted)">
      One-click confirm of every recommendation.
    </span>
  </div>

  <div id="qs"></div>

  <div class="submit-bar">
    <span style="font-size:13px;color:var(--muted)">When you're done:</span>
    <span style="margin-left:auto"></span>
    <button class="submit" id="submit">Submit decisions</button>
    <span id="submit-status" style="font-size:12px;color:var(--rec)"></span>
  </div>

  <footer>
    State persisted to <code>localStorage["{{STATE_KEY}}"]</code> and (when served via Arctic Base)
    mirrored through <code>window.workbench</code>.
  </footer>
</div>

<script>
// ===== EDIT THIS QUESTION SET =====
const QS = [
  {
    id: "q1",
    title: "First decision",
    why: "Why this matters in one sentence.",
    options: [
      { id: "a", title: "Option A", body: "<p>Body HTML allowed.</p>" },
      { id: "b", title: "Option B", recommended: true, body: "<p>Recommended option.</p>" },
      { id: "c", title: "Option C", body: "<p>Alternative.</p>" }
    ]
  }
];
// ==================================

const STATE_KEY = "{{STATE_KEY}}";

function loadState() {
  try { return JSON.parse(localStorage.getItem(STATE_KEY)) || {}; } catch { return {}; }
}
function saveLocal(state) { localStorage.setItem(STATE_KEY, JSON.stringify(state)); }

async function persist(state) {
  saveLocal(state);
  if (window.workbench) { try { await window.workbench.saveAll(state); } catch {} }
}

function render() {
  const state = loadState();
  const qs = document.getElementById("qs");
  qs.innerHTML = "";
  for (const q of QS) {
    const cur = state[q.id] || {};
    const article = document.createElement("article");
    article.className = "q";
    article.innerHTML = `
      <h2>${q.title}</h2>
      <p class="qmeta">${q.why}</p>
      <div class="options">
        ${q.options.map(o => `
          <div class="option ${o.recommended ? "recommended" : ""}">
            <label>
              <input type="radio" name="${q.id}" value="${o.id}" ${cur.choice === o.id ? "checked" : ""} />
              <span>
                <div class="opt-title">${o.title}${o.recommended ? ' <span class="rec-badge">Recommended</span>' : ""}</div>
                <div class="opt-body">${o.body}</div>
              </span>
            </label>
          </div>
        `).join("")}
      </div>
      <div class="notes">
        <label for="notes-${q.id}">Notes</label>
        <textarea id="notes-${q.id}" placeholder="Optional notes…">${cur.notes || ""}</textarea>
      </div>
    `;
    qs.appendChild(article);
  }
  // wire inputs
  for (const q of QS) {
    document.querySelectorAll(`input[name="${q.id}"]`).forEach(r => {
      r.addEventListener("change", () => {
        const s = loadState();
        s[q.id] = { ...(s[q.id] || {}), choice: r.value };
        persist(s);
        updateProgress();
      });
    });
    const ta = document.getElementById(`notes-${q.id}`);
    ta.addEventListener("input", () => {
      const s = loadState();
      s[q.id] = { ...(s[q.id] || {}), notes: ta.value };
      persist(s);
    });
  }
  updateProgress();
}

function updateProgress() {
  const state = loadState();
  const answered = QS.filter(q => state[q.id] && state[q.id].choice).length;
  const el = document.getElementById("progress");
  el.textContent = `${answered} / ${QS.length} answered`;
  el.classList.toggle("complete", answered === QS.length);
}

document.getElementById("ack-all").addEventListener("click", () => {
  const s = loadState();
  for (const q of QS) {
    const rec = q.options.find(o => o.recommended);
    if (rec) s[q.id] = { ...(s[q.id] || {}), choice: rec.id };
  }
  persist(s);
  render();
});

document.getElementById("reset").addEventListener("click", () => {
  if (confirm("Reset all answers?")) {
    localStorage.removeItem(STATE_KEY);
    if (window.workbench) { try { window.workbench.saveAll({}); } catch {} }
    render();
  }
});

document.getElementById("export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(loadState(), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `${STATE_KEY}.json`; a.click();
  URL.revokeObjectURL(url);
});

document.getElementById("submit").addEventListener("click", async () => {
  const state = loadState();
  saveLocal(state);
  const status = document.getElementById("submit-status");
  if (window.workbench) {
    try {
      const r = await window.workbench.submit(state);
      status.textContent = `submitted (v${r.version})`;
    } catch (e) { status.textContent = "submit failed: " + e; }
  } else {
    status.textContent = "submitted (local only — open via Arctic Base to mirror to API)";
  }
});

render();
</script>
</body>
</html>
"""


# ---------- qa-form: short ad-hoc Q&A ----------
QA_FORM = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  :root {
    --bg: var(--wb-bg, #fafafa);
    --paper: var(--wb-surface, #ffffff);
    --ink: var(--wb-ink, #1a1a1a);
    --muted: var(--wb-muted, #5c5c5c);
    --accent: var(--wb-accent, #2a5562);
    --rule: var(--wb-rule, #d9d3c7);
    --success: var(--wb-success, #2c6e3a);
    --rounded: var(--wb-rounded-md, 4px);
    --font-body: var(--wb-font-body, ui-sans-serif,system-ui,sans-serif);
  }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); }
  .wrap { max-width: 640px; margin: 0 auto; padding: 32px 20px 80px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 24px; font-style: italic; }
  .q { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--rounded);
       padding: 16px; margin-bottom: 14px; }
  .q label.q-label { font-weight: 600; display: block; margin-bottom: 8px; }
  .q .why { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
  .q input[type=text], .q textarea {
    width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--rule);
    border-radius: var(--rounded); font: inherit; font-size: 14px; background: var(--bg);
  }
  .q textarea { min-height: 60px; resize: vertical; }
  .choices label { display: flex; align-items: center; gap: 8px; padding: 6px 0; cursor: pointer; }
  .actions { display: flex; gap: 10px; margin-top: 16px; align-items: center; flex-wrap: wrap; }
  button { font: inherit; cursor: pointer; padding: 8px 14px; border-radius: var(--rounded); }
  button.submit { background: var(--success); color: white; border: none; font-weight: 600; }
  button.export { background: var(--paper); color: var(--ink); border: 1px solid var(--rule); }
  .status { color: var(--success); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>{{TITLE}}</h1>
  <div class="sub">{{SUBTITLE}}</div>
  <div id="qs"></div>
  <div class="actions">
    <button class="submit" id="submit">Submit</button>
    <button class="export" id="export">Export JSON</button>
    <span class="status" id="status"></span>
  </div>
</div>

<script>
// Each question: { id, label, why?, type: "text"|"textarea"|"choice", choices?: [{id,label}] }
// ===== EDIT THIS QUESTION SET =====
const QS = [
  { id: "q1", label: "What's your name?", type: "text" },
  { id: "q2", label: "Pick one:", type: "choice", choices: [
    { id: "yes", label: "Yes" }, { id: "no", label: "No" }
  ]},
  { id: "q3", label: "Anything else?", type: "textarea" }
];
// ==================================

const STATE_KEY = "{{STATE_KEY}}";

function loadState() { try { return JSON.parse(localStorage.getItem(STATE_KEY)) || {}; } catch { return {}; } }
function saveLocal(s) { localStorage.setItem(STATE_KEY, JSON.stringify(s)); }
async function persist(s) { saveLocal(s); if (window.workbench) { try { await window.workbench.saveAll(s); } catch {} } }

function render() {
  const state = loadState();
  const qs = document.getElementById("qs");
  qs.innerHTML = QS.map(q => {
    const v = state[q.id] || "";
    if (q.type === "choice") {
      return `<div class="q">
        <label class="q-label">${q.label}</label>
        ${q.why ? `<div class="why">${q.why}</div>` : ""}
        <div class="choices">${q.choices.map(c => `
          <label><input type="radio" name="${q.id}" value="${c.id}" ${v === c.id ? "checked" : ""}> ${c.label}</label>
        `).join("")}</div>
      </div>`;
    }
    if (q.type === "textarea") {
      return `<div class="q"><label class="q-label">${q.label}</label>
        ${q.why ? `<div class="why">${q.why}</div>` : ""}
        <textarea data-q="${q.id}">${v.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"})[c])}</textarea></div>`;
    }
    return `<div class="q"><label class="q-label">${q.label}</label>
      ${q.why ? `<div class="why">${q.why}</div>` : ""}
      <input type="text" data-q="${q.id}" value="${v.replace(/"/g, "&quot;")}"></div>`;
  }).join("");

  qs.querySelectorAll("input[type=text], textarea").forEach(el => {
    el.addEventListener("input", () => {
      const s = loadState(); s[el.dataset.q] = el.value; persist(s);
    });
  });
  qs.querySelectorAll("input[type=radio]").forEach(el => {
    el.addEventListener("change", () => {
      const s = loadState(); s[el.name] = el.value; persist(s);
    });
  });
}

document.getElementById("submit").addEventListener("click", async () => {
  const state = loadState();
  saveLocal(state);
  const status = document.getElementById("status");
  if (window.workbench) {
    try { const r = await window.workbench.submit(state); status.textContent = `submitted (v${r.version})`; }
    catch (e) { status.textContent = "submit failed: " + e; }
  } else {
    status.textContent = "submitted (local only)";
  }
});

document.getElementById("export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(loadState(), null, 2)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob), download: `${STATE_KEY}.json`
  });
  a.click(); URL.revokeObjectURL(a.href);
});

render();
</script>
</body>
</html>
"""


# ---------- pitch: read-only narrative + decision footer ----------
PITCH = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  :root {
    --bg: var(--wb-bg, #f7f4ee);
    --paper: var(--wb-surface, #ffffff);
    --ink: var(--wb-ink, #1a1a1a);
    --muted: var(--wb-muted, #5c5c5c);
    --accent: var(--wb-accent, #7a1f1f);
    --rule: var(--wb-rule, #d9d3c7);
    --success: var(--wb-success, #2c6e3a);
    --error: var(--wb-error, #a52a2a);
    --rounded: var(--wb-rounded-md, 4px);
    --font-body: var(--wb-font-body, "Charter","Georgia",serif);
  }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); }
  .wrap { max-width: 760px; margin: 0 auto; padding: 40px 28px 96px; background: var(--paper); }
  header { border-bottom: 2px solid var(--ink); padding-bottom: 14px; margin-bottom: 28px; }
  header h1 { margin: 0 0 4px; font-size: 26px; }
  header .sub { color: var(--muted); font-size: 14px; font-style: italic; }
  section { margin: 24px 0; }
  section h2 { font-size: 18px; margin: 0 0 8px; color: var(--accent); }
  .footer { position: sticky; bottom: 0; background: var(--paper); border-top: 2px solid var(--ink);
            padding: 14px 0; margin-top: 32px; display: flex; gap: 10px; flex-wrap: wrap;
            align-items: center; }
  .footer button { font: inherit; cursor: pointer; padding: 8px 16px; border-radius: var(--rounded);
                   font-weight: 600; }
  .approve { background: var(--success); color: white; border: none; }
  .defer { background: var(--paper); color: var(--ink); border: 1px solid var(--rule); }
  .reject { background: var(--paper); color: var(--error); border: 1px solid var(--error); }
  .notes { flex: 1 1 240px; min-width: 200px; padding: 8px 10px; font: inherit;
           border: 1px solid var(--rule); border-radius: var(--rounded); }
  .status { color: var(--success); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{{TITLE}}</h1>
    <div class="sub">{{SUBTITLE}}</div>
  </header>

  <!-- ===== EDIT BODY SECTIONS BELOW ===== -->
  <section>
    <h2>The pitch</h2>
    <p>What you're proposing, in one or two short paragraphs.</p>
  </section>

  <section>
    <h2>Why now</h2>
    <p>The motivation. What changed; what you'd unlock.</p>
  </section>

  <section>
    <h2>Cost / risk</h2>
    <p>Honest tradeoffs.</p>
  </section>
  <!-- ===================================== -->

  <div class="footer">
    <input class="notes" id="notes" placeholder="Optional notes…">
    <button class="reject" data-decision="reject">Reject</button>
    <button class="defer" data-decision="defer">Defer</button>
    <button class="approve" data-decision="approve">Approve</button>
    <span class="status" id="status"></span>
  </div>
</div>

<script>
const STATE_KEY = "{{STATE_KEY}}";

function loadState() { try { return JSON.parse(localStorage.getItem(STATE_KEY)) || {}; } catch { return {}; } }

const notes = document.getElementById("notes");
notes.value = loadState().notes || "";
notes.addEventListener("input", async () => {
  const s = { ...loadState(), notes: notes.value };
  localStorage.setItem(STATE_KEY, JSON.stringify(s));
  if (window.workbench) { try { await window.workbench.saveAll(s); } catch {} }
});

document.querySelectorAll("button[data-decision]").forEach(btn => {
  btn.addEventListener("click", async () => {
    const state = { decision: btn.dataset.decision, notes: notes.value, at: new Date().toISOString() };
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
    const status = document.getElementById("status");
    if (window.workbench) {
      try { const r = await window.workbench.submit(state); status.textContent = `submitted (v${r.version})`; }
      catch (e) { status.textContent = "submit failed: " + e; }
    } else {
      status.textContent = "submitted (local only)";
    }
  });
});
</script>
</body>
</html>
"""


# ---------- runbook: structured task list (JSON content for kind=runbook) ----------
RUNBOOK = """\
{
  "title": "{{TITLE}}",
  "description": "{{SUBTITLE}}",
  "steps": [
    {
      "id": "s1",
      "title": "First step — replace this list with the real plan",
      "description": "Optional Markdown-ish prose; kept short.",
      "status": "todo"
    },
    {
      "id": "s2",
      "title": "Mark steps in-progress as you start them",
      "status": "todo"
    },
    {
      "id": "s3",
      "title": "Use status: blocked + blocker: <message> when stuck",
      "status": "todo"
    }
  ]
}
"""


TEMPLATES: dict[str, tuple[TemplateMeta, str]] = {
    "approval-questions": (
        {
            "id": "approval-questions",
            "name": "Approval — multi-question decision doc",
            "description": (
                "Long-form approval/decision document. List of questions, each with options, an "
                "optional `recommended: true` flag, and a notes textarea. Toolbar with progress + "
                "JSON export + ack-all-recommendations + Reset. Submit button mirrors final state "
                "to the API via window.workbench.submit()."
            ),
            "suggested_kind": "approval-html",
            "when_to_use": (
                "Use when you have 3+ design/architecture decisions you need the user to confirm "
                "before you can proceed. Replaces a multi-turn back-and-forth."
            ),
        },
        APPROVAL_QUESTIONS,
    ),
    "qa-form": (
        {
            "id": "qa-form",
            "name": "Q&A — short ad-hoc form",
            "description": (
                "Lightweight form with a few text/textarea/choice questions. Submit + Export JSON."
                " Smaller and simpler than approval-questions; no recommendation badges or ack-all."
            ),
            "suggested_kind": "qa-form",
            "when_to_use": (
                "Use for quick free-form questions (1–5 short prompts) you can't resolve in chat."
            ),
        },
        QA_FORM,
    ),
    "pitch": (
        {
            "id": "pitch",
            "name": "Pitch — narrative + Approve/Defer/Reject",
            "description": (
                "Read-only narrative document with a sticky footer offering Approve / Defer / "
                "Reject and an optional notes field. No per-question controls."
            ),
            "suggested_kind": "approval-html",
            "when_to_use": (
                "Use when there's exactly ONE decision to make and you want to make the case in "
                "prose first. Cheaper and shorter than approval-questions."
            ),
        },
        PITCH,
    ),
    "runbook": (
        {
            "id": "runbook",
            "name": "Runbook — structured task list (JSON)",
            "description": (
                "JSON content for kind=runbook. Persistent step list with status "
                "(todo|in-progress|done|blocked), per-step blocker text, and timestamps. The "
                "user sees and edits checkboxes in the browser; the agent reads + writes via "
                "PUT/GET .../content. Replaces ad-hoc TODO comments scattered across files."
            ),
            "suggested_kind": "runbook",
            "when_to_use": (
                "Use for multi-session work where you want a shared, persistent task plan that "
                "survives across sessions and lets the user see/update progress and blockers."
            ),
        },
        RUNBOOK,
    ),
}


def list_templates() -> list[TemplateMeta]:
    return [meta for meta, _ in TEMPLATES.values()]


def get_template(template_id: str) -> tuple[TemplateMeta, str] | None:
    return TEMPLATES.get(template_id)
