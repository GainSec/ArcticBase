<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ObjectMeta, type ObjectKind, type Theme, type WorkbenchMeta } from "../api";
  import { navigate } from "../router";
  import { renderMiniMd } from "../mini-md";
  import ThemeWrapper from "./ThemeWrapper.svelte";

  export let slug: string;
  export let onTheme: (t: Theme | null) => void = () => {};
  export let onWorkbench: (w: WorkbenchMeta | null) => void = () => {};

  let wb: WorkbenchMeta | null = null;
  let theme: Theme | null = null;
  let objects: ObjectMeta[] = [];
  let error: string | null = null;
  let loading = true;
  let editMode = false;
  let savingOrder = false;
  let showArchived = false;

  const drawerOrder: { kind: ObjectKind; label: string }[] = [
    { kind: "approval-html", label: "Approvals" },
    { kind: "qa-form", label: "Q&A" },
    { kind: "runbook", label: "Runbooks" },
    { kind: "html", label: "HTML" },
    { kind: "md", label: "Docs" },
    { kind: "image", label: "Images" },
    { kind: "file", label: "Files" },
  ];

  async function loadAll() {
    try {
      wb = await api.getWorkbench(slug);
      onWorkbench(wb);
      objects = await api.listObjects(slug, { includeArchived: showArchived });
      try {
        theme = await api.getTheme(slug);
      } catch {
        theme = null;
      }
      onTheme(theme);
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  onMount(loadAll);

  $: if (showArchived !== undefined && !loading) reloadObjects();
  async function reloadObjects() {
    try { objects = await api.listObjects(slug, { includeArchived: showArchived }); } catch {}
  }

  async function togglePin(o: ObjectMeta, ev: MouseEvent) {
    ev.stopPropagation();
    try {
      const next = await api.patchObject(slug, o.id, { pinned: !o.pinned });
      objects = objects.map((x) => (x.id === o.id ? next : x));
      // Re-sort locally so pin moves to top.
      objects = [...objects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.order - b.order;
      });
    } catch (e) { alert("Pin failed: " + e); }
  }

  async function toggleArchive(o: ObjectMeta, ev: MouseEvent) {
    ev.stopPropagation();
    const action = o.archived ? "Unarchive" : "Archive";
    if (!confirm(`${action} "${o.title || o.filename || o.id}"?`)) return;
    try {
      await api.patchObject(slug, o.id, { archived: !o.archived });
      await reloadObjects();
    } catch (e) { alert("Archive failed: " + e); }
  }

  function bannerSrc(wb: WorkbenchMeta): string {
    // Server falls back to a generated SVG when no banner is set, so this is always non-null.
    return api.bannerUrl(wb.slug);
  }

  function clickObject(o: ObjectMeta) {
    if (o.kind === "file") navigate(`/wb/${slug}/files`);
    else navigate(`/wb/${slug}/o/${o.id}`);
  }

  async function deleteObject(o: ObjectMeta, ev: MouseEvent) {
    ev.stopPropagation();
    if (!confirm(`Delete "${o.title || o.filename || o.id}"? This is permanent.`)) return;
    try {
      await api.deleteObject(slug, o.id);
      objects = objects.filter((x) => x.id !== o.id);
    } catch (e) {
      alert("Delete failed: " + e);
    }
  }

  function viewResponses(o: ObjectMeta, ev: MouseEvent) {
    ev.stopPropagation();
    navigate(`/wb/${slug}/o/${o.id}/responses`);
  }

  // Reorder a single object within its drawer (its kind group). Persists to API after each move.
  async function moveWithinDrawer(o: ObjectMeta, dir: -1 | 1) {
    const sameKind = objects.filter((x) => x.kind === o.kind);
    const idx = sameKind.findIndex((x) => x.id === o.id);
    const target = idx + dir;
    if (target < 0 || target >= sameKind.length) return;
    const reordered = [...sameKind];
    [reordered[idx], reordered[target]] = [reordered[target], reordered[idx]];
    // Rebuild full list: same global order, but items of this kind come from the new order.
    let i = 0;
    objects = objects.map((x) => (x.kind === o.kind ? reordered[i++] : x));
    await persistOrder();
  }

  async function persistOrder() {
    savingOrder = true;
    try {
      await api.reorderObjects(slug, objects.map((o) => o.id));
    } catch (e) {
      alert("Reorder failed: " + e);
    } finally {
      savingOrder = false;
    }
  }

  // Pull layout token aliases (camelCase + kebab-case both supported by the API).
  function layoutVal(t: Theme | null, key: string, fallback: string): string {
    if (!t) return fallback;
    const layout = (t.tokens as unknown as { layout?: Record<string, string | null> }).layout;
    if (!layout) return fallback;
    return layout[key] ?? layout[key.replace("_", "-")] ?? fallback;
  }

  $: cardStyle = layoutVal(theme, "card_style", "flat");
  $: motif = layoutVal(theme, "motif", "none");
  $: bannerShape = layoutVal(theme, "banner_shape", "rect");
  $: heroStyle = layoutVal(theme, "hero_style", "cover");
  $: density = layoutVal(theme, "density", "comfortable");
</script>

{#if loading}
  <p style="padding:32px;color:#8b91a0;">Loading workbench…</p>
{:else if error || !wb}
  <div style="padding:32px;color:#f88;">{error || "Workbench not found"}</div>
{:else if theme}
  <ThemeWrapper {theme}>
    <main
      data-density={density}
      data-card-style={cardStyle}
      data-motif={motif}
      data-banner-shape={bannerShape}
      data-hero-style={heroStyle}
    >
      {#if heroStyle !== "none"}
        <div class="banner" data-shape={bannerShape} data-hero={heroStyle}>
          {#if heroStyle === "crt-monitor"}
            <div class="crt-frame">
              <img src={bannerSrc(wb)} alt="" />
              <div class="crt-overlay"></div>
            </div>
          {:else}
            <img src={bannerSrc(wb)} alt="" />
          {/if}
        </div>
      {/if}

      <header>
        <h1>{wb.title}</h1>
        {#if wb.description}<div class="desc">{@html renderMiniMd(wb.description)}</div>{/if}
        <div class="meta">
          {#if wb.url}<span class="kv"><b>URL</b> <a href={wb.url} target="_blank" rel="noopener">{wb.url}</a></span>{/if}
          {#if wb.ip}<span class="kv"><b>IP</b> <code>{wb.ip}</code></span>{/if}
          {#if wb.local_path}<span class="kv"><b>PATH</b> <code>{wb.local_path}</code></span>{/if}
          {#each Object.entries(wb.custom_fields ?? {}) as [k, v]}
            <span class="kv">
              <b>{k.toUpperCase()}</b>
              {#if /^https?:\/\//.test(v)}<a href={v} target="_blank" rel="noopener">{v}</a>{:else}<code>{v}</code>{/if}
            </span>
          {/each}
        </div>
        {#if wb.tags.length}
          <div class="tags">
            {#each wb.tags as t}<span class="tag">{t}</span>{/each}
          </div>
        {/if}
      </header>

      <section class="actions">
        <button on:click={() => navigate(`/wb/${slug}/files`)}>Files</button>
        <button on:click={() => navigate(`/wb/${slug}/theme`)}>Theme</button>
        <button class:active={editMode} on:click={() => (editMode = !editMode)}>
          {editMode ? "Done" : "Edit"}
        </button>
        <label class="show-archived">
          <input type="checkbox" bind:checked={showArchived} />
          <span>Show archived</span>
        </label>
        {#if savingOrder}<span class="saving">saving order…</span>{/if}
      </section>

      {#each drawerOrder as d}
        {@const items = objects.filter((o) => o.kind === d.kind)}
        {#if items.length}
          <section class="drawer">
            <h2>{d.label}</h2>
            <ul>
              {#each items as o (o.id)}
                <li>
                  <div class="obj-wrap" class:archived={o.archived}>
                    <button class="obj-card" on:click={() => clickObject(o)}>
                      {#if motif === "bolts"}
                        <span class="bolt tl"></span><span class="bolt tr"></span>
                        <span class="bolt bl"></span><span class="bolt br"></span>
                      {:else if motif === "hex"}
                        <svg class="hex-accent" viewBox="0 0 32 32" aria-hidden="true">
                          <polygon points="16,2 28,9 28,23 16,30 4,23 4,9" fill="none" stroke="currentColor" stroke-width="1.5"/>
                        </svg>
                      {:else if motif === "tape"}
                        <span class="tape-strip"></span>
                      {/if}
                      {#if o.pinned}<span class="pin-badge" title="Pinned">📌</span>{/if}
                      {#if o.archived}<span class="archived-badge">ARCHIVED</span>{/if}
                      <div class="obj-title">{o.title || o.filename || o.id}</div>
                      <div class="obj-meta">
                        {o.state_version > 0 ? `v${o.state_version}` : ""}
                        {o.filename ? o.filename : ""}
                      </div>
                    </button>
                    <div class="obj-actions">
                      {#if o.state_version > 0}
                        <button class="obj-btn" on:click={(e) => viewResponses(o, e)} title="View response history">⏱</button>
                      {/if}
                      {#if editMode}
                        {@const sameKind = objects.filter((x) => x.kind === o.kind && !x.archived)}
                        {@const isFirst = sameKind[0]?.id === o.id}
                        {@const isLast = sameKind[sameKind.length - 1]?.id === o.id}
                        <button class="obj-btn" class:on={o.pinned} on:click={(e) => togglePin(o, e)} title={o.pinned ? "Unpin" : "Pin"}>📌</button>
                        <button class="obj-btn" on:click={(e) => { e.stopPropagation(); moveWithinDrawer(o, -1); }} disabled={isFirst || o.archived} title="Move up">▲</button>
                        <button class="obj-btn" on:click={(e) => { e.stopPropagation(); moveWithinDrawer(o, 1); }} disabled={isLast || o.archived} title="Move down">▼</button>
                        <button class="obj-btn" on:click={(e) => toggleArchive(o, e)} title={o.archived ? "Unarchive" : "Archive"}>{o.archived ? "↑" : "📥"}</button>
                        <button class="obj-btn danger" on:click={(e) => deleteObject(o, e)} title="Delete object">✕</button>
                      {/if}
                    </div>
                  </div>
                </li>
              {/each}
            </ul>
          </section>
        {/if}
      {/each}
    </main>
  </ThemeWrapper>
{:else}
  <main class="no-theme">
    <h1>{wb.title}</h1>
    <p class="warn">This workbench has no theme yet. <button on:click={() => navigate(`/wb/${slug}/theme`)}>Set one</button></p>
  </main>
{/if}

<style>
  /* Defaults — get overridden by data-* attributes via the rules below. */
  main {
    --pad: var(--wb-layout-padding, var(--wb-space-margin, 28px));
    --gap: var(--wb-layout-gap, 14px);
    --card-radius: var(--wb-card-radius, var(--wb-rounded-md, 8px));
    --card-shadow: var(--wb-card-shadow, 0 2px 0 rgba(0,0,0,0.2));

    max-width: 1100px;
    margin: 0 auto;
    padding: var(--pad) var(--wb-space-gutter, 24px);
  }

  /* Density overrides for surfaces that don't read --wb-layout-padding directly */
  main[data-density="compact"] { --pad: 12px; --gap: 8px; }
  main[data-density="spacious"] { --pad: 32px; --gap: 22px; }

  /* ------ Banner / hero ------ */
  .banner {
    margin-bottom: var(--wb-space-gutter, 24px);
    border-radius: var(--card-radius);
    overflow: hidden;
    aspect-ratio: 16 / 5;
    background: var(--wb-surface, #f5f5f5);
  }
  .banner[data-shape="circle"] {
    aspect-ratio: 1 / 1;
    width: 240px;
    height: 240px;
    border-radius: 50%;
    margin: 0 auto var(--wb-space-gutter, 24px);
  }
  .banner[data-shape="t-shape"] {
    /* Titans-Tower T silhouette via clip-path */
    aspect-ratio: 4 / 5;
    max-width: 360px;
    margin: 0 auto var(--wb-space-gutter, 24px);
    clip-path: polygon(0 0, 100% 0, 100% 25%, 65% 25%, 65% 100%, 35% 100%, 35% 25%, 0 25%);
  }
  .banner img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .banner[data-hero="crt-monitor"] {
    aspect-ratio: 16 / 9;
    background: #000;
    padding: 14px;
    border: 3px solid var(--wb-rule, #333);
    box-shadow: inset 0 0 30px rgba(0, 255, 90, 0.15);
  }
  .crt-frame { position: relative; width: 100%; height: 100%; overflow: hidden; }
  .crt-frame .crt-overlay {
    position: absolute; inset: 0;
    background: repeating-linear-gradient(0deg, rgba(0,255,90,0.06) 0 1px, transparent 1px 3px);
    pointer-events: none;
  }

  /* ------ Header ------ */
  header h1 {
    font-family: var(--wb-font-headline-lg, var(--wb-font-body));
    font-size: var(--wb-font-size-headline-lg, 2.25rem);
    margin: 0 0 8px;
    letter-spacing: -0.02em;
  }
  .desc { color: var(--wb-muted); margin: 0 0 8px; }
  .desc :global(p) { margin: 0 0 6px; }
  .desc :global(p:last-child) { margin-bottom: 0; }
  .desc :global(ul) { margin: 6px 0; padding-left: 22px; }
  .desc :global(li) { margin-bottom: 2px; }
  .desc :global(a) { color: var(--wb-accent); }
  .desc :global(code) { font-family: var(--wb-font-mono); background: var(--wb-surface); padding: 1px 6px; border-radius: 2px; font-size: 12px; }
  .desc :global(strong) { color: var(--wb-ink); }
  .meta { display: flex; gap: 14px; font-size: 12px; color: var(--wb-muted); margin-bottom: 10px; flex-wrap: wrap; }
  .kv { display: inline-flex; gap: 6px; align-items: baseline; }
  .kv b { color: var(--wb-accent); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700; }
  .kv code { font-family: var(--wb-font-mono); background: var(--wb-surface); padding: 2px 8px; border-radius: var(--wb-rounded-sm, 4px); }
  .kv a { color: var(--wb-accent); text-decoration: none; }
  .kv a:hover { text-decoration: underline; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
  .tag { background: var(--wb-surface); border: 1px solid var(--wb-rule); padding: 2px 8px; border-radius: var(--wb-rounded-full, 9999px); font-size: 11px; }

  .actions { display: flex; gap: 8px; margin: 24px 0; align-items: center; flex-wrap: wrap; }
  .actions button {
    background: var(--wb-accent); color: var(--wb-bg); border: none;
    padding: 8px 16px; border-radius: var(--card-radius); cursor: pointer;
    font: inherit; font-weight: 600;
  }
  .actions button.active { background: var(--wb-success); }
  .actions .saving { color: var(--wb-muted); font-size: 12px; font-family: var(--wb-font-mono); }
  .show-archived { display: inline-flex; align-items: center; gap: 6px; color: var(--wb-muted); font-size: 12px; cursor: pointer; }
  .show-archived input { accent-color: var(--wb-accent); }

  /* ------ Drawers + cards ------ */
  .drawer { margin-top: 32px; }
  .drawer h2 {
    font-family: var(--wb-font-headline-md, var(--wb-font-body));
    font-size: 1.1rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--wb-muted);
    margin: 0 0 12px;
  }
  .drawer ul {
    list-style: none; padding: 0; margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: var(--gap);
  }

  /* Card variants — driven by data-card-style on <main> */
  .obj-card {
    position: relative;
    width: 100%;
    text-align: left;
    background: var(--wb-surface);
    border: 1px solid var(--wb-rule);
    padding: var(--pad);
    border-radius: var(--card-radius);
    cursor: pointer;
    color: inherit;
    font: inherit;
  }
  .obj-card:hover { border-color: var(--wb-accent); }

  main[data-card-style="bolted"] .obj-card {
    border: 2.5px solid #000;
    box-shadow: var(--card-shadow);
    background-image: linear-gradient(180deg, rgba(255,255,255,0.04), transparent 60%);
  }
  main[data-card-style="floating"] .obj-card {
    border: 1px solid transparent;
    box-shadow: var(--card-shadow);
    transition: transform 0.15s, box-shadow 0.15s;
  }
  main[data-card-style="floating"] .obj-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.45);
  }
  main[data-card-style="inset"] .obj-card {
    border: 1px solid var(--wb-rule);
    box-shadow: inset 0 2px 6px rgba(0,0,0,0.35);
    background: color-mix(in srgb, var(--wb-bg) 70%, var(--wb-surface) 30%);
  }

  /* Motifs — corner accents */
  .bolt {
    position: absolute;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, var(--wb-rule), color-mix(in srgb, var(--wb-rule) 60%, #000));
    border: 1.5px solid #000;
  }
  .bolt.tl { top: 6px; left: 6px; }
  .bolt.tr { top: 6px; right: 6px; }
  .bolt.bl { bottom: 6px; left: 6px; }
  .bolt.br { bottom: 6px; right: 6px; }

  .hex-accent {
    position: absolute;
    top: 8px; right: 8px;
    width: 22px; height: 22px;
    color: var(--wb-accent);
    opacity: 0.6;
  }

  .tape-strip {
    position: absolute;
    top: -2px; right: 12px;
    width: 56px; height: 14px;
    background-image: repeating-linear-gradient(-45deg, var(--wb-accent) 0 6px, #000 6px 12px);
    border: 1.5px solid #000;
    transform: rotate(8deg);
  }

  .obj-title { font-weight: 600; font-size: 14px; }
  .obj-meta { font-size: 11px; color: var(--wb-muted); margin-top: 4px; font-family: var(--wb-font-mono); }

  .obj-wrap { position: relative; }
  .obj-actions {
    position: absolute;
    top: 6px; right: 6px;
    display: flex; gap: 4px;
  }
  .obj-btn {
    width: 24px; height: 24px;
    background: var(--wb-bg);
    color: var(--wb-ink);
    border: 1.5px solid var(--wb-rule);
    border-radius: var(--wb-rounded-sm, 3px);
    cursor: pointer;
    font-size: 12px;
    line-height: 1;
    padding: 0;
  }
  .obj-btn:hover { border-color: var(--wb-accent); }
  .obj-btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .obj-btn.danger:hover:not(:disabled) { background: var(--wb-error); color: var(--wb-bg); border-color: var(--wb-error); }
  .obj-btn.on { background: var(--wb-accent); color: var(--wb-bg); border-color: var(--wb-accent); }

  .pin-badge { position: absolute; top: 6px; left: 6px; font-size: 14px; }
  .archived-badge {
    position: absolute; bottom: 6px; right: 6px;
    font-family: var(--wb-font-mono); font-size: 9px; letter-spacing: 0.1em;
    background: var(--wb-rule); color: var(--wb-muted); padding: 2px 6px; border-radius: 2px;
  }
  .obj-wrap.archived { opacity: 0.55; }

  .no-theme { padding: 32px; max-width: 600px; margin: 0 auto; }
  .warn { color: #b1b6c1; }
  .warn button { background: #2563eb; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; margin-left: 8px; }
</style>
