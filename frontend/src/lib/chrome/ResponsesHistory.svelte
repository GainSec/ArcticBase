<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ObjectMeta, type ResponseEvent } from "../api";
  import { navigate } from "../router";

  export let slug: string;
  export let oid: string;

  let meta: ObjectMeta | null = null;
  let events: ResponseEvent[] = [];
  let loading = true;
  let error: string | null = null;
  let expanded = new Set<number>();

  async function load() {
    try {
      meta = await api.getObject(slug, oid);
      events = await api.listResponses(slug, oid, 0);
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function toggle(v: number) {
    if (expanded.has(v)) expanded.delete(v);
    else expanded.add(v);
    expanded = new Set(expanded);
  }

  function fmt(s: string) {
    try { return new Date(s).toLocaleString(); } catch { return s; }
  }
</script>

<main>
  <header>
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← BACK TO WORKBENCH</button>
    <div class="eyebrow label-maker">// AUDIT_LOG // OBJECT_RESPONSES</div>
    <h1 class="display">{meta?.title || oid}</h1>
    <p class="sub">
      <span class="kv"><b>OID</b> <code>{oid}</code></span>
      {#if meta}
        <span class="kv"><b>KIND</b> <code>{meta.kind}</code></span>
        <span class="kv"><b>STATE_VERSION</b> <code>{meta.state_version}</code></span>
      {/if}
    </p>
    <div class="actions">
      <a class="ghost" href={api.responsesExportUrl(slug, oid)} download>EXPORT FULL HISTORY</a>
    </div>
  </header>

  {#if error}<div class="error label-maker">{error}</div>{/if}

  {#if loading}
    <p class="empty label-maker">// LOADING…</p>
  {:else if events.length === 0}
    <p class="empty label-maker">// NO_EVENTS_RECORDED</p>
  {:else}
    <ol class="timeline">
      {#each events as e (e.version)}
        <li class="event" class:submit={e.kind === "submit"} class:autosave={e.kind === "autosave"}>
          <div class="ev-head" on:click={() => toggle(e.version)} on:keydown={(k) => k.key === "Enter" && toggle(e.version)} role="button" tabindex="0">
            <span class="ev-version label-maker">v{e.version}</span>
            <span class="ev-kind label-maker">{e.kind.toUpperCase()}</span>
            <span class="ev-by label-maker">{e.submitted_by}</span>
            <span class="ev-time">{fmt(e.submitted_at)}</span>
            <span class="ev-toggle">{expanded.has(e.version) ? "▾" : "▸"}</span>
          </div>
          {#if expanded.has(e.version)}
            <pre class="ev-payload">{JSON.stringify(e.payload, null, 2)}</pre>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
</main>

<style>
  main { max-width: 1000px; margin: 0 auto; padding: 24px 20px 60px; }
  @media (max-width: 540px) { main { padding: 16px 12px 40px; } }
  header { margin-bottom: 24px; }
  .back { background: transparent; border: 0; color: var(--ab-muted); padding: 0; cursor: pointer; font: inherit; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 12px; }
  .back:hover { color: var(--ab-yellow); }
  .eyebrow { color: var(--ab-yellow); margin-bottom: 8px; }
  h1 { margin: 0 0 12px; font-size: clamp(28px, 5vw, 42px); line-height: 1; text-shadow: 4px 4px 0 #000, 4px 4px 0 var(--ab-cyan); word-break: break-word; }
  .sub { color: var(--ab-muted); font-size: 12px; margin: 0 0 14px; display: flex; flex-wrap: wrap; gap: 12px; }
  .kv { display: inline-flex; gap: 6px; align-items: baseline; }
  .kv b { color: var(--ab-tertiary); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; }
  .kv code { font-family: var(--ab-font-mono); background: var(--ab-surface); padding: 2px 6px; border: 1px solid var(--ab-rule); border-radius: 2px; }
  .actions { display: flex; gap: 8px; }
  .ghost {
    background: transparent; color: var(--ab-muted);
    border: 1.5px solid var(--ab-rule-strong);
    border-radius: var(--ab-radius);
    padding: 8px 12px; cursor: pointer;
    font-family: var(--ab-font-stencil);
    font-size: 11px; letter-spacing: 0.06em;
    text-transform: uppercase; text-decoration: none;
    box-shadow: var(--ab-shadow-bolt);
  }
  .ghost:hover { background: var(--ab-yellow); color: #000; border-color: #000; }

  .timeline { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .event {
    background: var(--ab-surface);
    border: 2px solid #000;
    box-shadow: var(--ab-shadow-bolt);
    border-radius: var(--ab-radius);
    overflow: hidden;
  }
  .event.submit { border-left: 4px solid var(--ab-green); }
  .event.autosave { border-left: 4px solid var(--ab-cyan); opacity: 0.85; }
  .ev-head {
    display: grid;
    grid-template-columns: 50px 90px 70px 1fr auto;
    align-items: center; gap: 10px;
    padding: 10px 14px;
    cursor: pointer;
    font-size: 11px;
  }
  .ev-head:hover { background: var(--ab-bg); }
  .ev-version { color: var(--ab-yellow); }
  .ev-kind { color: var(--ab-ink); }
  .event.submit .ev-kind { color: var(--ab-green); }
  .event.autosave .ev-kind { color: var(--ab-cyan); }
  .ev-by { color: var(--ab-muted); }
  .ev-time { color: var(--ab-muted); font-family: var(--ab-font-mono); font-size: 11px; text-align: right; }
  .ev-toggle { font-family: var(--ab-font-mono); color: var(--ab-muted); }
  .ev-payload {
    margin: 0;
    padding: 14px 16px;
    background: #02080c;
    color: var(--ab-green);
    font-family: var(--ab-font-mono);
    font-size: 12px;
    line-height: 1.5;
    border-top: 1px solid var(--ab-rule);
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
  @media (max-width: 720px) {
    .ev-head { grid-template-columns: 50px 90px 1fr auto; }
    .ev-by { display: none; }
  }
  .empty { color: var(--ab-muted); font-size: 13px; }
  .error { background: var(--ab-bg); color: var(--ab-red-bright); border: 2px solid var(--ab-red); padding: 10px 14px; border-radius: var(--ab-radius); }
</style>
