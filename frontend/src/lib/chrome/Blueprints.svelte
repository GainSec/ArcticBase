<script lang="ts">
  import { onMount } from "svelte";

  interface Tpl { id: string; name: string; description: string; suggested_kind: string; when_to_use: string; }
  let templates: Tpl[] = [];
  let conventions = "";
  let loading = true;
  let error: string | null = null;

  onMount(async () => {
    try {
      const [tres, cres] = await Promise.all([
        fetch("/api/agent/templates").then((r) => r.json()),
        fetch("/api/agent/conventions").then((r) => r.text()),
      ]);
      templates = tres.templates;
      conventions = cres;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  });
</script>

<main>
  <header>
    <div class="eyebrow label-maker">// 2X4 TECH // BLUEPRINTS</div>
    <h1 class="display">BLUEPRINTS</h1>
    <p class="sub">Agent-facing reference: HTML templates, conventions, OpenAPI schema. Hand any agent the URL and it knows what to do.</p>
  </header>

  {#if error}<div class="error label-maker">{error}</div>{/if}

  <section class="overview-hero">
    <a class="overview-card" href="/wb/arctic-base/o/obj_e6099c3e591444408284dad7">
      <div class="overview-text">
        <div class="card-header label-maker">// HUMAN OVERVIEW</div>
        <div class="card-title">Arctic Base — System Overview</div>
        <p class="card-desc">Hero page covering what Arctic Base is, the architecture diagram, the 7 object kinds, the agent surface, and a feature tour. Good first stop if you're new (or sharing the project with someone).</p>
        <span class="card-link">OPEN OVERVIEW →</span>
      </div>
    </a>
  </section>

  <section class="endpoints">
    <h2 class="display">ENTRY POINTS</h2>
    <ul class="grid">
      <li class="card">
        <div class="card-header label-maker">/AGENT</div>
        <div class="card-title">302 → /openapi.json</div>
        <p class="card-desc">Hand the agent this URL. It lands on the OpenAPI schema and self-documents from there.</p>
        <a class="card-link" href="/agent">OPEN →</a>
      </li>
      <li class="card">
        <div class="card-header label-maker">/API/AGENT/CONVENTIONS</div>
        <div class="card-title">Runtime contract</div>
        <p class="card-desc">~6 KB Markdown of what OpenAPI can't express: window.workbench surface, polling, theme tokens, review-HTML rules.</p>
        <a class="card-link" href="/api/agent/conventions">OPEN →</a>
      </li>
      <li class="card">
        <div class="card-header label-maker">/OPENAPI.JSON</div>
        <div class="card-title">API schema</div>
        <p class="card-desc">Machine-readable contract for every workbench / object / theme / response endpoint.</p>
        <a class="card-link" href="/openapi.json">OPEN →</a>
      </li>
      <li class="card">
        <div class="card-header label-maker">/DOCS</div>
        <div class="card-title">Swagger UI</div>
        <p class="card-desc">Live, in-browser explorer for the API. Useful when learning the surface.</p>
        <a class="card-link" href="/docs">OPEN →</a>
      </li>
    </ul>
  </section>

  <section class="templates">
    <h2 class="display">TEMPLATES</h2>
    <p class="sub">Self-contained HTML starters. Reference <code>--wb-*</code> CSS variables (auto-theme), feature-detect <code>window.workbench</code>, fall back to localStorage + JSON export. Don't hand-write from scratch.</p>
    {#if loading}
      <p class="empty label-maker">// LOADING…</p>
    {:else}
      <ul class="grid">
        {#each templates as t (t.id)}
          <li class="card">
            <div class="card-header label-maker">{t.suggested_kind.toUpperCase()}</div>
            <div class="card-title">{t.name}</div>
            <p class="card-desc">{t.description}</p>
            <p class="when label-maker">WHEN: {t.when_to_use}</p>
            <div class="actions">
              <a class="card-link" href={`/api/agent/templates/${t.id}`}>FETCH RAW →</a>
              <a class="card-link alt" href={`/api/agent/templates/${t.id}?fill_title=Untitled`}>FETCH FILLED →</a>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if conventions}
    <section class="conventions">
      <h2 class="display">CONVENTIONS (FULL TEXT)</h2>
      <pre>{conventions}</pre>
    </section>
  {/if}
</main>

<style>
  main { max-width: 1100px; margin: 0 auto; padding: 28px 24px 80px; }
  header { margin-bottom: 24px; }
  .eyebrow { color: var(--ab-yellow); margin-bottom: 8px; }
  h1 { margin: 0; font-size: clamp(36px, 6vw, 56px); line-height: 0.95; text-shadow: 4px 4px 0 #000, 4px 4px 0 var(--ab-cyan); }
  h2 { margin: 32px 0 12px; font-size: 22px; color: var(--ab-yellow); }
  .sub { color: var(--ab-muted); font-size: 14px; max-width: 760px; }
  code { font-family: var(--ab-font-mono); background: var(--ab-bg); border: 1px solid var(--ab-rule); padding: 1px 5px; border-radius: 2px; font-size: 12px; }
  .grid { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .overview-hero { margin-bottom: 28px; }
  .overview-card {
    display: block;
    text-decoration: none;
    color: inherit;
    background: var(--ab-surface-2);
    border: 3px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    padding: 22px 24px;
    background-image: linear-gradient(135deg, rgba(125, 211, 252, 0.10), transparent 70%);
    transition: transform 0.05s, box-shadow 0.05s;
  }
  .overview-card:hover { transform: translate(-2px, -2px); box-shadow: 6px 6px 0 #000; }
  .overview-card:active { transform: translate(2px, 2px); box-shadow: 0 0 0 #000; }
  .overview-card .card-title { font-size: 22px; }
  .overview-card .card-desc { max-width: 700px; }
  .card {
    background: var(--ab-surface-2);
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    padding: 16px;
    background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent 60%);
  }
  .card-header { color: var(--ab-yellow); font-size: 11px; margin-bottom: 8px; }
  .card-title { font-family: var(--ab-font-display); font-size: 18px; line-height: 1.1; margin-bottom: 8px; }
  .card-desc { color: var(--ab-muted); font-size: 13px; line-height: 1.5; margin: 0 0 8px; }
  .when { color: var(--ab-cyan); font-size: 10px; margin: 6px 0; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .card-link {
    color: var(--ab-cyan);
    font-family: var(--ab-font-body);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    text-decoration: none;
    border: 1.5px solid var(--ab-cyan);
    padding: 4px 8px;
    border-radius: 2px;
    display: inline-block;
  }
  .card-link.alt { color: var(--ab-yellow); border-color: var(--ab-yellow); }
  .card-link:hover { background: var(--ab-cyan); color: #000; }
  .card-link.alt:hover { background: var(--ab-yellow); color: #000; }
  .conventions pre {
    background: var(--ab-surface);
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    padding: 16px;
    color: var(--ab-ink);
    font-family: var(--ab-font-mono);
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-x: auto;
  }
  .error { background: var(--ab-bg); color: var(--ab-red-bright); border: 2px solid var(--ab-red); padding: 10px 14px; border-radius: var(--ab-radius); margin-bottom: 12px; }
  .empty { color: var(--ab-muted); font-size: 13px; }
</style>
