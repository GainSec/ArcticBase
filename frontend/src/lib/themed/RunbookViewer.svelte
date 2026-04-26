<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ObjectMeta, type Theme, type WorkbenchMeta } from "../api";
  import { navigate } from "../router";
  import ThemeWrapper from "./ThemeWrapper.svelte";

  export let slug: string;
  export let oid: string;

  type Status = "todo" | "in-progress" | "done" | "blocked";
  interface Step {
    id: string;
    title: string;
    description?: string;
    status: Status;
    blocker?: string;
    started_at?: string;
    completed_at?: string;
  }
  interface Runbook {
    title?: string;
    description?: string;
    steps: Step[];
  }

  let meta: ObjectMeta | null = null;
  let theme: Theme | null = null;
  let wb: WorkbenchMeta | null = null;
  let runbook: Runbook = { steps: [] };
  let saving = false;
  let saved = false;
  let error: string | null = null;
  let loading = true;

  async function load() {
    try {
      meta = await api.getObject(slug, oid);
      try { theme = await api.getTheme(slug); } catch {}
      try { wb = await api.getWorkbench(slug); } catch {}
      const { text } = await api.getObjectContentText(slug, oid);
      try {
        runbook = text.trim() ? JSON.parse(text) : { steps: [] };
      } catch (e) {
        error = "Runbook content is not valid JSON: " + e;
        runbook = { steps: [] };
      }
      if (!runbook.steps) runbook.steps = [];
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function persist() {
    saving = true;
    saved = false;
    try {
      const body = JSON.stringify(runbook, null, 2);
      await api.putObjectContent(slug, oid, body);
      saved = true;
    } catch (e) {
      error = String(e);
    } finally {
      saving = false;
    }
  }

  async function setStatus(step: Step, next: Status) {
    step.status = next;
    const now = new Date().toISOString();
    if (next === "in-progress" && !step.started_at) step.started_at = now;
    if (next === "done") {
      step.completed_at = now;
      step.blocker = undefined;
    }
    if (next !== "blocked") step.blocker = undefined;
    runbook = { ...runbook, steps: [...runbook.steps] };
    await persist();
  }

  async function setBlocker(step: Step, msg: string) {
    step.blocker = msg;
    if (msg) step.status = "blocked";
    runbook = { ...runbook, steps: [...runbook.steps] };
    await persist();
  }

  async function addStep() {
    const id = `s${Date.now().toString(36)}`;
    runbook = {
      ...runbook,
      steps: [...runbook.steps, { id, title: "New step", status: "todo" }],
    };
    await persist();
  }

  async function removeStep(step: Step) {
    if (!confirm(`Remove step "${step.title}"?`)) return;
    runbook = { ...runbook, steps: runbook.steps.filter((s) => s.id !== step.id) };
    await persist();
  }

  async function moveStep(step: Step, dir: -1 | 1) {
    const idx = runbook.steps.findIndex((s) => s.id === step.id);
    const target = idx + dir;
    if (target < 0 || target >= runbook.steps.length) return;
    const next = [...runbook.steps];
    [next[idx], next[target]] = [next[target], next[idx]];
    runbook = { ...runbook, steps: next };
    await persist();
  }

  function statusGlyph(s: Status): string {
    return s === "done" ? "✓" : s === "in-progress" ? "▶" : s === "blocked" ? "⚠" : " ";
  }
  function nextStatus(s: Status): Status {
    return s === "todo" ? "in-progress" : s === "in-progress" ? "done" : s === "done" ? "todo" : "todo";
  }

  $: progress = runbook.steps.length === 0
    ? 0
    : Math.round((runbook.steps.filter((s) => s.status === "done").length / runbook.steps.length) * 100);
  $: counts = {
    done: runbook.steps.filter((s) => s.status === "done").length,
    inProgress: runbook.steps.filter((s) => s.status === "in-progress").length,
    blocked: runbook.steps.filter((s) => s.status === "blocked").length,
    todo: runbook.steps.filter((s) => s.status === "todo").length,
  };
</script>

<div class="wrap">
  <div class="bar">
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← BACK</button>
    {#if meta}<span class="title">{meta.title || "Runbook"}</span>{/if}
    <span class="kind">runbook</span>
    <span class="spacer"></span>
    {#if saving}<span class="status dirty">saving…</span>{/if}
    {#if saved}<span class="status ok">saved</span>{/if}
    <button on:click={() => navigate(`/wb/${slug}/o/${oid}/edit`)}>RAW JSON</button>
    <button class="primary" on:click={addStep}>+ STEP</button>
  </div>

  {#if error}<div class="error">{error}</div>{/if}

  {#if loading}
    <p class="loading">Loading runbook…</p>
  {:else if theme}
    <ThemeWrapper {theme}>
      <main>
        <header class="rb-header">
          <h1>{runbook.title ?? meta?.title ?? "Runbook"}</h1>
          {#if runbook.description}<p class="rb-desc">{runbook.description}</p>{/if}

          <div class="progress">
            <div class="progress-track"><div class="progress-fill" style="width:{progress}%"></div></div>
            <div class="progress-stats">
              <span class="stat done">{counts.done} done</span>
              <span class="stat in-progress">{counts.inProgress} active</span>
              <span class="stat blocked">{counts.blocked} blocked</span>
              <span class="stat todo">{counts.todo} todo</span>
              <span class="stat pct">{progress}%</span>
            </div>
          </div>
        </header>

        {#if runbook.steps.length === 0}
          <p class="empty">No steps yet. Click + STEP to add one (or edit raw JSON).</p>
        {:else}
          <ol class="steps">
            {#each runbook.steps as step, i (step.id)}
              <li class="step" data-status={step.status}>
                <button
                  class="check"
                  on:click={() => setStatus(step, nextStatus(step.status))}
                  title="Cycle status (todo → in-progress → done → todo)"
                >
                  <span class="glyph">{statusGlyph(step.status)}</span>
                </button>

                <div class="body">
                  <input
                    class="step-title"
                    bind:value={step.title}
                    on:blur={persist}
                    placeholder="Step title"
                  />
                  {#if step.description}
                    <p class="step-desc">{step.description}</p>
                  {/if}

                  <div class="step-meta">
                    <span class="status-pill" data-status={step.status}>{step.status.toUpperCase()}</span>
                    {#if step.started_at}<span class="ts">started {new Date(step.started_at).toLocaleString()}</span>{/if}
                    {#if step.completed_at}<span class="ts">done {new Date(step.completed_at).toLocaleString()}</span>{/if}
                  </div>

                  {#if step.status === "blocked" || step.blocker}
                    <input
                      class="blocker-input"
                      placeholder="Blocker — what's stuck?"
                      value={step.blocker ?? ""}
                      on:blur={(e) => setBlocker(step, (e.target as HTMLInputElement).value)}
                    />
                  {/if}
                </div>

                <div class="step-actions">
                  <button on:click={() => moveStep(step, -1)} disabled={i === 0} title="Move up">▲</button>
                  <button on:click={() => moveStep(step, 1)} disabled={i === runbook.steps.length - 1} title="Move down">▼</button>
                  {#if step.status !== "blocked"}
                    <button on:click={() => setStatus(step, "blocked")} title="Mark blocked">⚠</button>
                  {/if}
                  <button class="danger" on:click={() => removeStep(step)} title="Remove">✕</button>
                </div>
              </li>
            {/each}
          </ol>
        {/if}

        <footer class="rb-footer">
          <span>// Persisted as JSON to <code>{wb?.slug ?? slug}/{oid}</code> · agents read via <code>GET .../content</code> · write via <code>PUT .../content</code></span>
        </footer>
      </main>
    </ThemeWrapper>
  {/if}
</div>

<style>
  .wrap { display: flex; flex-direction: column; min-height: calc(100vh - 53px); }
  .bar {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 16px;
    background: var(--ab-surface); border-bottom: 2px solid #000;
    font-family: var(--ab-font-body);
    flex-wrap: wrap;
  }
  .title { font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
  .kind { font-family: var(--ab-font-mono); font-size: 10px; padding: 2px 8px; background: var(--ab-bg); border: 1px solid var(--ab-rule); border-radius: 2px; color: var(--ab-muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .spacer { flex: 1; }
  .status { font-size: 10px; padding: 3px 8px; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
  .dirty { background: #422c00; color: var(--ab-tertiary); }
  .ok { background: #133a23; color: #6dd58c; }
  button { background: var(--ab-bg); border: 1.5px solid var(--ab-rule); color: var(--ab-ink); padding: 7px 12px; border-radius: var(--ab-radius); cursor: pointer; font: inherit; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.primary { background: var(--ab-primary-bright); border-color: #000; color: var(--ab-on-primary); box-shadow: 2px 2px 0 #000; }
  button.back { background: transparent; border: none; }
  .loading { padding: 32px; color: var(--ab-muted); }
  .error { background: var(--ab-bg); color: var(--ab-red-bright); padding: 10px 16px; border: 2px solid var(--ab-red); margin: 14px 16px; border-radius: var(--ab-radius); }

  main {
    max-width: 920px; width: 100%;
    margin: 0 auto;
    padding: var(--wb-space-margin, 32px) var(--wb-space-gutter, 24px);
    flex: 1;
  }
  .rb-header h1 {
    margin: 0 0 6px;
    font-family: var(--wb-font-headline-md, var(--wb-font-body));
    font-size: 28px;
    color: var(--wb-ink);
  }
  .rb-desc { color: var(--wb-muted); margin: 0 0 16px; }

  .progress { margin: 18px 0 28px; }
  .progress-track {
    height: 8px;
    background: var(--wb-surface);
    border: 1px solid var(--wb-rule);
    border-radius: 999px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--wb-success), var(--wb-accent));
    transition: width 0.2s;
  }
  .progress-stats {
    display: flex; gap: 10px; flex-wrap: wrap;
    margin-top: 8px;
    font-size: 12px;
    color: var(--wb-muted);
  }
  .progress-stats .stat { display: inline-flex; align-items: center; gap: 4px; font-family: var(--wb-font-mono); }
  .progress-stats .stat.done::before        { content: "● "; color: var(--wb-success); }
  .progress-stats .stat.in-progress::before { content: "● "; color: var(--wb-accent); }
  .progress-stats .stat.blocked::before     { content: "● "; color: var(--wb-error); }
  .progress-stats .stat.todo::before        { content: "○ "; color: var(--wb-muted); }
  .progress-stats .stat.pct { margin-left: auto; color: var(--wb-ink); font-weight: 700; }

  .empty { color: var(--wb-muted); padding: 24px 0; text-align: center; }

  .steps { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .step {
    display: grid;
    grid-template-columns: 44px 1fr auto;
    gap: 14px;
    padding: 12px 14px;
    background: var(--wb-surface);
    border: 1px solid var(--wb-rule);
    border-radius: var(--wb-rounded-md, 6px);
    align-items: start;
    transition: border-color 0.15s, opacity 0.15s;
  }
  .step[data-status="done"] { opacity: 0.65; }
  .step[data-status="in-progress"] { border-color: var(--wb-accent); }
  .step[data-status="blocked"] { border-color: var(--wb-error); }

  .check {
    width: 36px; height: 36px;
    background: var(--wb-bg);
    border: 2px solid var(--wb-rule);
    border-radius: var(--wb-rounded-sm, 4px);
    color: var(--wb-ink);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    padding: 0;
    display: grid; place-items: center;
  }
  .step[data-status="done"] .check { background: var(--wb-success); color: var(--wb-bg); border-color: var(--wb-success); }
  .step[data-status="in-progress"] .check { background: var(--wb-accent); color: var(--wb-bg); border-color: var(--wb-accent); }
  .step[data-status="blocked"] .check { background: var(--wb-error); color: var(--wb-bg); border-color: var(--wb-error); }

  .body { min-width: 0; }
  .step-title {
    width: 100%;
    background: transparent;
    border: 1px dashed transparent;
    color: var(--wb-ink);
    font: inherit;
    font-weight: 600;
    font-size: 15px;
    padding: 4px 6px;
    border-radius: 3px;
    box-sizing: border-box;
  }
  .step[data-status="done"] .step-title { text-decoration: line-through; color: var(--wb-muted); }
  .step-title:focus { outline: none; border-color: var(--wb-rule); background: var(--wb-bg); }
  .step-desc { color: var(--wb-muted); font-size: 13px; margin: 4px 6px 0; }
  .step-meta { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 8px; padding: 0 6px; font-size: 11px; color: var(--wb-muted); }
  .status-pill {
    font-family: var(--wb-font-mono);
    padding: 2px 6px; border-radius: 2px;
    background: var(--wb-bg); border: 1px solid var(--wb-rule);
    letter-spacing: 0.08em; font-size: 10px; font-weight: 700;
  }
  .status-pill[data-status="done"] { color: var(--wb-success); border-color: var(--wb-success); }
  .status-pill[data-status="in-progress"] { color: var(--wb-accent); border-color: var(--wb-accent); }
  .status-pill[data-status="blocked"] { color: var(--wb-error); border-color: var(--wb-error); }
  .ts { font-family: var(--wb-font-mono); font-size: 10px; }

  .blocker-input {
    width: 100%; box-sizing: border-box;
    margin-top: 8px;
    background: color-mix(in srgb, var(--wb-error) 14%, transparent);
    border: 1px solid var(--wb-error);
    color: var(--wb-ink);
    padding: 8px 10px;
    border-radius: var(--wb-rounded-sm, 4px);
    font: inherit; font-size: 13px;
  }

  .step-actions { display: flex; flex-direction: column; gap: 4px; }
  .step-actions button {
    width: 28px; height: 28px;
    background: var(--wb-bg); border: 1px solid var(--wb-rule); color: var(--wb-ink);
    padding: 0;
    text-transform: none; letter-spacing: 0;
    font-size: 12px; font-weight: 400;
    border-radius: var(--wb-rounded-sm, 3px);
  }
  .step-actions button:hover:not(:disabled) { border-color: var(--wb-accent); }
  .step-actions button.danger:hover { background: var(--wb-error); color: var(--wb-bg); border-color: var(--wb-error); }

  .rb-footer { margin-top: 32px; padding-top: 14px; border-top: 1px dashed var(--wb-rule); color: var(--wb-muted); font-size: 11px; font-family: var(--wb-font-mono); }
  .rb-footer code { background: var(--wb-surface); padding: 1px 5px; border-radius: 2px; }

  @media (max-width: 540px) {
    .step { grid-template-columns: 36px 1fr; }
    .step-actions { grid-column: 1 / -1; flex-direction: row; flex-wrap: wrap; justify-content: flex-end; }
  }
</style>
