<script lang="ts">
  import { onMount } from "svelte";
  import { api, type WorkbenchMeta, type ObjectMeta } from "../api";
  import { navigate } from "../router";

  type Enriched = WorkbenchMeta & {
    objectCount: number;
    objectsByKind: Record<string, number>;
    totalSize: number;
    powerLevel: number; // 0-100
    isUrgent: boolean;
    isRecent: boolean;
    primaryButton: "access" | "continue" | "schematics";
  };

  let workbenches: Enriched[] = [];
  let loading = true;
  let creating = false;
  let showCreate = false;
  let newTitle = "";
  let newSlug = "";
  let newTags = "";
  let newUrl = "";
  let newIp = "";
  let newLocalPath = "";
  let error: string | null = null;
  let nowMs = Date.now();
  let totalObjects = 0;
  let totalsByKind: Record<string, number> = {};
  let totalSize = 0;
  let mostRecent: Date | null = null;
  let lastWorkbench: { slug: string; title: string; at: Date } | null = null;
  let lastFile: { slug: string; title: string; at: Date } | null = null;
  let activeTag: string | null = null;
  let showTagFilter = false;

  function deriveStats(wb: WorkbenchMeta, objects: ObjectMeta[]): Enriched {
    const objectCount = objects.length;
    const totalSize = objects.reduce((a, o) => a + o.size_bytes, 0);
    const objectsByKind: Record<string, number> = {};
    for (const o of objects) objectsByKind[o.kind] = (objectsByKind[o.kind] ?? 0) + 1;
    const powerLevel = Math.min(100, Math.round((objectCount / 10) * 100));
    const isUrgent = nowMs - new Date(wb.updated_at).getTime() < 30 * 60 * 1000;
    const isRecent = nowMs - new Date(wb.updated_at).getTime() < 24 * 60 * 60 * 1000;
    const primaryButton: Enriched["primaryButton"] =
      objectCount === 0 ? "schematics" : powerLevel < 50 ? "continue" : "access";
    return { ...wb, objectCount, objectsByKind, totalSize, powerLevel, isUrgent, isRecent, primaryButton };
  }

  function fmtBytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
    return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }

  function fmtAgo(d: Date | null): string {
    if (!d) return "never";
    const ms = Date.now() - d.getTime();
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.round(m / 60);
    if (h < 48) return `${h}h ago`;
    return `${Math.round(h / 24)}d ago`;
  }

  function pad(s: string | number, w: number): string {
    const t = String(s);
    return t + " ".repeat(Math.max(0, w - t.length));
  }
  function rpad(s: string | number, w: number, ch = "."): string {
    const t = String(s);
    return t + ch.repeat(Math.max(0, w - t.length));
  }

  async function load() {
    try {
      const list = await api.listWorkbenches();
      const pairs = await Promise.all(
        list.map(async (wb) => {
          try { return { wb, objs: await api.listObjects(wb.slug) }; }
          catch { return { wb, objs: [] as ObjectMeta[] }; }
        }),
      );
      const enriched = pairs.map(({ wb, objs }) => deriveStats(wb, objs));
      workbenches = enriched;
      totalObjects = enriched.reduce((a, w) => a + w.objectCount, 0);
      totalSize = enriched.reduce((a, w) => a + w.totalSize, 0);
      const merged: Record<string, number> = {};
      for (const w of enriched) {
        for (const [k, n] of Object.entries(w.objectsByKind)) merged[k] = (merged[k] ?? 0) + n;
      }
      totalsByKind = merged;
      const updated = enriched
        .map((w) => new Date(w.updated_at).getTime())
        .filter((t) => Number.isFinite(t));
      mostRecent = updated.length ? new Date(Math.max(...updated)) : null;

      const wbWithAccess = enriched
        .filter((w) => w.last_accessed_at)
        .map((w) => ({ slug: w.slug, title: w.title, at: new Date(w.last_accessed_at!) }))
        .sort((a, b) => b.at.getTime() - a.at.getTime());
      lastWorkbench = wbWithAccess[0] ?? null;

      let bestFile: typeof lastFile = null;
      for (const { wb, objs } of pairs) {
        for (const o of objs) {
          if (!o.last_accessed_at) continue;
          const at = new Date(o.last_accessed_at);
          if (!bestFile || at.getTime() > bestFile.at.getTime()) {
            bestFile = { slug: wb.slug, title: o.title || o.filename || o.id, at };
          }
        }
      }
      lastFile = bestFile;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    load();
    const t = setInterval(() => {
      nowMs = Date.now();
    }, 30000);
    return () => clearInterval(t);
  });

  async function create() {
    if (!newTitle.trim()) return;
    creating = true;
    error = null;
    try {
      const tags = newTags.split(",").map((t) => t.trim()).filter(Boolean);
      const wb = await api.createWorkbench({
        title: newTitle.trim(),
        slug: newSlug.trim() || undefined,
        url: newUrl.trim() || undefined,
        ip: newIp.trim() || undefined,
        local_path: newLocalPath.trim() || undefined,
        tags: tags.length ? tags : undefined,
      });
      newTitle = "";
      newSlug = "";
      newTags = "";
      newUrl = "";
      newIp = "";
      newLocalPath = "";
      showCreate = false;
      await load();
      navigate(`/wb/${wb.slug}`);
    } catch (e) {
      error = String(e);
    } finally {
      creating = false;
    }
  }

  // Sorted unique tag list across all workbenches, with counts.
  $: allTags = (() => {
    const counts = new Map<string, number>();
    for (const w of workbenches) for (const t of w.tags) counts.set(t, (counts.get(t) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  })();

  $: filteredWorkbenches = activeTag
    ? workbenches.filter((w) => w.tags.includes(activeTag!))
    : workbenches;

  function buttonLabel(p: Enriched["primaryButton"]): string {
    switch (p) {
      case "access": return "ACCESS CONSOLE";
      case "continue": return "CONTINUE BUILD";
      case "schematics": return "VIEW SCHEMATICS";
    }
  }

</script>

<main>
  <!-- ===== System Status Console ===== -->
  <section class="console" aria-label="System status">
    <div class="console-bezel">
      <div class="console-screen">
        <div class="console-header">
          <span class="console-title">ARCTIC_BASE :: STATUS_REPORT</span>
          <span class="console-led" aria-hidden="true"></span>
        </div>
        <pre class="console-body">{`> system_status........ NOMINAL
> workbenches active... ${pad(workbenches.length, 6)}
> total objects........ ${pad(totalObjects, 6)}
>   approval-html...... ${pad(totalsByKind["approval-html"] ?? 0, 4)}
>   qa-form............ ${pad(totalsByKind["qa-form"] ?? 0, 4)}
>   md................. ${pad(totalsByKind["md"] ?? 0, 4)}
>   html............... ${pad(totalsByKind["html"] ?? 0, 4)}
>   image.............. ${pad(totalsByKind["image"] ?? 0, 4)}
>   file............... ${pad(totalsByKind["file"] ?? 0, 4)}
> total cache.......... ${pad(fmtBytes(totalSize), 10)}
> last activity........ ${pad(fmtAgo(mostRecent), 10)}
> last workbench....... ${lastWorkbench ? `${lastWorkbench.slug} (${fmtAgo(lastWorkbench.at)})` : "—"}
> last file............ ${lastFile ? `${lastFile.slug}/${lastFile.title} (${fmtAgo(lastFile.at)})` : "—"}`}<span class="console-cursor">▌</span></pre>
      </div>
    </div>
  </section>

  <header>
    <div class="title-row">
      <div class="title-block">
        <div class="eyebrow label-maker">// SECTOR_V — TREEHOUSE OPERATIONS</div>
        <h1 class="display">ACTIVE WORKBENCHES</h1>
      </div>
      <button class="cta" on:click={() => (showCreate = !showCreate)}>
        <span class="cta-icon" aria-hidden="true">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="10" cy="10" r="7" />
            <path d="M10 4 V10" />
          </svg>
        </span>
        <span>INITIALIZE NEW WORKBENCH</span>
      </button>
    </div>
  </header>

  {#if showCreate}
    <section class="create">
      <div class="create-header label-maker">// NEW MISSION DOSSIER</div>
      <div class="create-grid">
        <div class="field">
          <label class="label-maker" for="newTitle">PROJECT_TITLE *</label>
          <input
            id="newTitle"
            bind:value={newTitle}
            placeholder="e.g. TaskyTrack"
            on:keydown={(e) => e.key === "Enter" && create()}
          />
        </div>
        <div class="field">
          <label class="label-maker" for="newSlug">SLUG</label>
          <input id="newSlug" bind:value={newSlug} placeholder="auto-from-title" />
        </div>
        <div class="field">
          <label class="label-maker" for="newUrl">URL</label>
          <input id="newUrl" bind:value={newUrl} placeholder="https://taskytrack.example" />
        </div>
        <div class="field">
          <label class="label-maker" for="newIp">IP</label>
          <input id="newIp" bind:value={newIp} placeholder="192.168.13.37" />
        </div>
        <div class="field span-2">
          <label class="label-maker" for="newLocalPath">LOCAL_PATH</label>
          <input id="newLocalPath" bind:value={newLocalPath} placeholder="/Users/me/code/project" />
        </div>
        <div class="field span-2">
          <label class="label-maker" for="newTags">TAGS (COMMA-SEP)</label>
          <input id="newTags" bind:value={newTags} placeholder="webapp, personal, security" />
        </div>
      </div>
      <div class="create-actions">
        <button class="ghost" on:click={() => (showCreate = false)}>CANCEL</button>
        <button class="cta" on:click={create} disabled={creating || !newTitle.trim()}>
          {creating ? "DEPLOYING…" : "DEPLOY"}
        </button>
      </div>
    </section>
  {/if}

  {#if error}
    <div class="error label-maker"><span class="err-tag">SIGNAL_ERROR //</span> {error}</div>
  {/if}

  {#if loading}
    <p class="empty label-maker crt">// SCANNING DATABASE…</p>
  {:else if workbenches.length === 0}
    <p class="empty label-maker">// NO WORKBENCHES DEPLOYED — INITIALIZE ABOVE</p>
  {:else}
    {#if allTags.length}
      <div class="tag-filter">
        <button
          class="tf-toggle label-maker"
          class:active={showTagFilter || activeTag !== null}
          on:click={() => (showTagFilter = !showTagFilter)}
          aria-expanded={showTagFilter}
        >
          <span class="tf-chev" aria-hidden="true">{showTagFilter ? "▾" : "▸"}</span>
          // FILTER BY TAG
          {#if activeTag}
            <span class="tf-active-label">: {activeTag.toUpperCase()}</span>
          {/if}
        </button>
        {#if showTagFilter}
          <div class="tf-chips">
            <button class="tf-chip" class:active={activeTag === null} on:click={() => (activeTag = null)}>ALL · {workbenches.length}</button>
            {#each allTags as [t, n]}
              <button class="tf-chip" class:active={activeTag === t} on:click={() => (activeTag = activeTag === t ? null : t)}>
                {t.toUpperCase()} · {n}
              </button>
            {/each}
            {#if activeTag}
              <button class="tf-chip clear" on:click={() => (activeTag = null)}>CLEAR</button>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
    {#if filteredWorkbenches.length === 0}
      <p class="empty label-maker">// NO WORKBENCHES MATCH TAG: {activeTag}</p>
    {/if}
    <ul class="grid">
      {#each filteredWorkbenches as wb (wb.slug)}
        <li>
          <div class="card" class:urgent={wb.isUrgent}>
            <span class="bolt bolt-tl" aria-hidden="true"></span>
            <span class="bolt bolt-tr" aria-hidden="true"></span>
            <span class="bolt bolt-bl" aria-hidden="true"></span>
            <span class="bolt bolt-br" aria-hidden="true"></span>

            {#if wb.isUrgent}
              <span class="urgent-badge label-maker">URGENT</span>
            {:else if wb.isRecent}
              <span class="recent-badge label-maker">FRESH</span>
            {/if}

            <div class="card-header label-maker">PROJECT_{wb.slug.toUpperCase()}</div>
            <div class="card-title display">{wb.title}</div>
            {#if wb.description}<div class="card-desc">{wb.description}</div>{/if}

            <div class="meter">
              <div class="meter-row label-maker">
                <span>POWER_LEVEL</span>
                <span class="meter-pct">{wb.powerLevel}%</span>
              </div>
              <div class="meter-track">
                <div class="meter-fill" style="width: {wb.powerLevel}%"></div>
              </div>
            </div>

            {#if wb.tags.length}
              <div class="tags">
                {#each wb.tags.slice(0, 4) as t}<span class="tag label-maker">{t}</span>{/each}
              </div>
            {/if}

            <button
              class="cta-card"
              class:variant-access={wb.primaryButton === "access"}
              class:variant-continue={wb.primaryButton === "continue"}
              class:variant-schematics={wb.primaryButton === "schematics"}
              on:click={() => navigate(`/wb/${wb.slug}`)}
            >
              <span class="cta-card-glyph" aria-hidden="true">▶</span>
              <span>{buttonLabel(wb.primaryButton)}</span>
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</main>

<style>
  main { max-width: 1200px; margin: 0 auto; padding: 24px 20px 60px; }
  header { margin-bottom: 24px; }
  @media (max-width: 540px) {
    main { padding: 16px 12px 40px; }
    h1 { text-shadow: 2px 2px 0 #000, 2px 2px 0 var(--ab-red); }
  }
  @media (max-width: 720px) {
    .title-row { flex-direction: column; align-items: stretch; }
    .cta { justify-content: center; }
  }
  .title-row { display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; }
  .eyebrow { color: var(--ab-yellow); margin-bottom: 8px; opacity: 0.9; }
  h1 { margin: 0; font-size: clamp(36px, 6vw, 64px); line-height: 0.95; color: var(--ab-ink); text-shadow: 4px 4px 0 #000, 4px 4px 0 var(--ab-red); }

  .cta {
    display: inline-flex; align-items: center; gap: 12px;
    background: var(--ab-warn-yellow); color: #000;
    border: 2.5px solid #000; box-shadow: var(--ab-shadow-hard); border-radius: var(--ab-radius);
    padding: 16px 22px; cursor: pointer;
    font-family: var(--ab-font-stencil); font-size: 14px; letter-spacing: 0.06em;
    transition: transform 0.05s, box-shadow 0.05s;
  }
  .cta:hover { transform: translate(-1px, -1px); box-shadow: var(--ab-shadow-hard-lg); filter: brightness(1.08); }
  .cta:active { transform: translate(2px, 2px); box-shadow: 0 0 0 #000; }
  .cta:disabled { opacity: 0.5; cursor: not-allowed; }
  .cta-icon {
    display: inline-grid; place-items: center;
    width: 26px; height: 26px;
    background: var(--ab-yellow); color: #000;
    border: 2px solid #000; border-radius: 50%;
  }
  .cta-icon svg { width: 18px; height: 18px; }

  .ghost {
    background: transparent; color: var(--ab-muted);
    border: 2px solid var(--ab-rule-strong); border-radius: var(--ab-radius);
    padding: 16px 22px; cursor: pointer;
    font-family: var(--ab-font-stencil); font-size: 13px; letter-spacing: 0.06em;
    box-shadow: var(--ab-shadow-bolt);
  }
  .ghost:hover { color: #000; border-color: #000; background: var(--ab-yellow); }

  /* ===== Status console (CRT bezel + green-on-black VT323 stat block) ===== */
  .console {
    margin-bottom: 24px;
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    overflow: hidden;
  }
  .console-bezel {
    background: linear-gradient(180deg, #2a1a0e 0%, #1a0f08 100%);
    padding: 10px;
    border-bottom: 2.5px solid #000;
  }
  .console-screen {
    background: #02080c;
    border: 2px solid #000;
    border-radius: 4px;
    padding: 14px 16px 16px;
    color: var(--ab-green);
    text-shadow: 0 0 6px rgba(109, 213, 140, 0.55);
    background-image:
      repeating-linear-gradient(0deg, rgba(109, 213, 140, 0.06) 0 1px, transparent 1px 3px),
      radial-gradient(ellipse at 50% 0%, rgba(109, 213, 140, 0.12), transparent 70%);
    position: relative;
    animation: flicker 3.7s infinite;
  }
  @keyframes flicker {
    0%, 100% { opacity: 1; }
    93% { opacity: 1; }
    94% { opacity: 0.92; }
    95% { opacity: 1; }
    96% { opacity: 0.96; }
    97% { opacity: 1; }
  }
  .console-header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px dashed rgba(109, 213, 140, 0.35);
    padding-bottom: 6px; margin-bottom: 8px;
  }
  .console-title {
    font-family: var(--ab-font-crt);
    font-size: 16px;
    letter-spacing: 0.06em;
    color: var(--ab-green);
  }
  .console-led {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--ab-green);
    box-shadow: 0 0 8px var(--ab-green);
    animation: blink 1.6s infinite;
  }
  @keyframes blink {
    0%, 60% { opacity: 1; }
    70%, 100% { opacity: 0.25; }
  }
  .console-body {
    margin: 0;
    font-family: var(--ab-font-crt);
    font-size: 16px;
    line-height: 1.35;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--ab-green);
  }
  .console-cursor {
    color: var(--ab-green);
    animation: cursor-blink 1s steps(1) infinite;
  }
  @keyframes cursor-blink { 50% { opacity: 0; } }

  @media (max-width: 540px) {
    .console-body { font-size: 13px; }
    .console-title { font-size: 13px; }
  }

  /* ===== Tag filter (collapsible) ===== */
  .tag-filter {
    margin-bottom: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .tf-toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: 1.5px solid var(--ab-rule);
    color: var(--ab-muted);
    padding: 6px 12px;
    border-radius: 2px;
    cursor: pointer;
    align-self: flex-start;
    font-family: var(--ab-font-body);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .tf-toggle:hover { color: var(--ab-ink); border-color: var(--ab-yellow); }
  .tf-toggle.active { color: var(--ab-yellow); border-color: var(--ab-yellow); }
  .tf-chev { font-family: var(--ab-font-mono); }
  .tf-active-label { color: var(--ab-yellow); }
  .tf-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 12px;
    background: var(--ab-surface);
    border: 1.5px solid var(--ab-rule);
    border-radius: 2px;
  }
  .tf-chip {
    background: var(--ab-bg);
    border: 1.5px solid var(--ab-rule);
    color: var(--ab-muted);
    padding: 5px 10px;
    border-radius: 2px;
    cursor: pointer;
    font-family: var(--ab-font-body);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .tf-chip:hover { color: var(--ab-ink); border-color: var(--ab-yellow); }
  .tf-chip.active { background: var(--ab-yellow); color: #000; border-color: #000; }
  .tf-chip.clear { color: var(--ab-red); border-color: var(--ab-red); }
  .tf-chip.clear:hover { background: var(--ab-red); color: var(--ab-ink); border-color: #000; }

  /* ===== Create form ===== */
  .create { background: var(--ab-surface); border: 2.5px solid #000; box-shadow: var(--ab-shadow-hard); border-radius: var(--ab-radius); margin-bottom: 24px; overflow: hidden; }
  .create-header { padding: 10px 16px; background: var(--ab-yellow); color: #000; border-bottom: 2.5px solid #000; }
  .create-grid { padding: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .field.span-2 { grid-column: 1 / -1; }
  .field label { color: var(--ab-yellow); font-size: 11px; }
  .field input { background: var(--ab-bg); border: 2px solid var(--ab-rule); color: var(--ab-ink); padding: 11px 12px; border-radius: var(--ab-radius); font-family: var(--ab-font-mono); font-size: 14px; min-width: 0; }
  .field input:focus { outline: none; border-color: var(--ab-yellow); box-shadow: 0 0 0 3px rgba(125, 211, 252, 0.25); }
  .create-actions { display: flex; gap: 8px; padding: 0 18px 18px; justify-content: flex-end; }
  @media (max-width: 720px) {
    .create-grid { grid-template-columns: 1fr; padding: 14px; }
    .field.span-2 { grid-column: 1; }
    .create-actions { flex-direction: column; padding: 0 14px 14px; }
    .create-actions > * { width: 100%; }
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 22px;
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .card {
    position: relative;
    background: var(--ab-surface-2);
    color: inherit;
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    padding: 18px 16px 16px;
    display: flex; flex-direction: column; gap: 10px;
    background-image:
      linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 60%),
      repeating-linear-gradient(90deg, transparent 0 18px, rgba(0, 0, 0, 0.04) 18px 19px),
      repeating-linear-gradient(0deg, transparent 0 6px, rgba(0, 0, 0, 0.03) 6px 7px);
  }
  .card.urgent { border-color: var(--ab-red); box-shadow: 4px 4px 0 var(--ab-red); }

  .bolt { position: absolute; width: 9px; height: 9px; border-radius: 50%; background: radial-gradient(circle at 30% 30%, var(--ab-rule-strong), #4a3010 70%); border: 1.5px solid #000; }
  .bolt-tl { top: 8px; left: 8px; }
  .bolt-tr { top: 8px; right: 8px; }
  .bolt-bl { bottom: 8px; left: 8px; }
  .bolt-br { bottom: 8px; right: 8px; }

  .urgent-badge, .recent-badge {
    position: absolute;
    top: -10px; right: 14px;
    padding: 4px 10px;
    border: 2px solid #000;
    box-shadow: var(--ab-shadow-bolt);
    font-size: 10px;
  }
  .urgent-badge { background: var(--ab-red); color: var(--ab-ink); }
  .recent-badge { background: var(--ab-yellow); color: #000; }

  .card-header { color: var(--ab-yellow); font-size: 11px; padding-left: 14px; }
  .card-title { font-family: var(--ab-font-display); font-size: 26px; line-height: 1.05; color: var(--ab-ink); padding: 0 14px; }
  .card-desc { color: var(--ab-muted); font-size: 13px; line-height: 1.5; padding: 0 14px; }

  .meter { padding: 6px 14px 0; }
  .meter-row { display: flex; justify-content: space-between; color: var(--ab-muted); font-size: 10px; margin-bottom: 4px; }
  .meter-pct { color: var(--ab-yellow); }
  .meter-track {
    height: 10px;
    background: var(--ab-bg);
    border: 2px solid #000;
    border-radius: 2px;
    overflow: hidden;
    box-shadow: inset 1px 1px 0 rgba(0, 0, 0, 0.4);
  }
  .meter-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--ab-green), var(--ab-yellow) 70%, var(--ab-orange));
    transition: width 0.3s ease;
  }

  .tags { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 14px; }
  .tag { background: var(--ab-yellow); color: #000; border: 1.5px solid #000; padding: 3px 8px; border-radius: 2px; font-size: 10px; }

  .cta-card {
    margin: 8px 14px 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: calc(100% - 28px);
    padding: 10px 14px;
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-bolt);
    border-radius: var(--ab-radius);
    cursor: pointer;
    font-family: var(--ab-font-stencil);
    font-size: 12px;
    letter-spacing: 0.06em;
    transition: transform 0.05s, box-shadow 0.05s;
  }
  .cta-card:hover { transform: translate(-1px, -1px); box-shadow: 4px 4px 0 #000; }
  .cta-card:active { transform: translate(2px, 2px); box-shadow: 0 0 0 #000; }
  .cta-card-glyph { font-family: var(--ab-font-mono); font-weight: 700; }

  .variant-access { background: var(--ab-green); color: #062b0f; }
  .variant-continue { background: var(--ab-warn-yellow); color: #000; }
  .variant-schematics { background: var(--ab-cyan); color: #001824; }

  .error { background: var(--ab-bg); color: var(--ab-red-bright); border: 2.5px solid var(--ab-red); padding: 12px 16px; border-radius: var(--ab-radius); margin-bottom: 14px; font-size: 12px; box-shadow: var(--ab-shadow-bolt); }
  .err-tag { background: var(--ab-red); color: #000; padding: 2px 8px; margin-right: 8px; border-radius: 2px; }
  .empty { color: var(--ab-muted); font-size: 13px; }
</style>
