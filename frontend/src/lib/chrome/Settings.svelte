<script lang="ts">
  import { onMount } from "svelte";
  import { api, type WorkbenchMeta } from "../api";
  import { navigate } from "../router";

  let workbenches: WorkbenchMeta[] = [];
  let trash: { archive: string }[] = [];
  let loading = true;
  let busy: string | null = null;
  let error: string | null = null;
  let reorderMode = false;
  let savingOrder = false;

  // Edit modal state
  let editing: WorkbenchMeta | null = null;
  let editTitle = "";
  let editDesc = "";
  let editUrl = "";
  let editIp = "";
  let editLocalPath = "";
  let editTags = "";
  let editCustom: { key: string; value: string }[] = [];
  let savingEdit = false;
  // Snapshots state for the edit modal
  let editSnapshots: { name: string; label: string; size_bytes: number; created_at: string }[] = [];
  let snapshotLabel = "";
  let creatingSnapshot = false;
  let snapshotBusy: string | null = null;
  // Self-test state for the activity console header
  let selfTestRunning = false;
  let selfTestResult: { pass: boolean; total_ms: number; steps: { name: string; ok: boolean; elapsed_ms: number; detail: string }[] } | null = null;
  let bannerFile: FileList | null = null;
  let uploadingBanner = false;
  let bannerUploadCacheBust = Date.now();
  let activity: { ts: number; method: string; path: string; status: number; elapsed_ms: number; request_id: string; is_agent: boolean }[] = [];
  let activityTimer: ReturnType<typeof setInterval> | null = null;

  async function load() {
    error = null;
    try {
      const [wbs, ts] = await Promise.all([api.listWorkbenches(), api.listTrash()]);
      workbenches = wbs;
      trash = ts;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  async function loadActivity() {
    try {
      const r = await api.agentActivity(80, true);
      activity = r.events;
    } catch {
      // silent — activity is best-effort
    }
  }

  onMount(() => {
    load();
    loadActivity();
    activityTimer = setInterval(loadActivity, 5000);
    return () => { if (activityTimer) clearInterval(activityTimer); };
  });

  function openEdit(wb: WorkbenchMeta) {
    editing = wb;
    editTitle = wb.title;
    editDesc = wb.description ?? "";
    editUrl = wb.url ?? "";
    editIp = wb.ip ?? "";
    editLocalPath = wb.local_path ?? "";
    editTags = wb.tags.join(", ");
    editCustom = Object.entries(wb.custom_fields ?? {}).map(([key, value]) => ({ key, value }));
    editSnapshots = [];
    snapshotLabel = "";
    api.listSnapshots(wb.slug).then((s) => (editSnapshots = s)).catch(() => {});
  }

  async function createSnapshot() {
    if (!editing) return;
    creatingSnapshot = true;
    try {
      await api.createSnapshot(editing.slug, snapshotLabel.trim() || "snapshot");
      snapshotLabel = "";
      editSnapshots = await api.listSnapshots(editing.slug);
    } catch (e) {
      error = String(e);
    } finally {
      creatingSnapshot = false;
    }
  }

  async function restoreSnapshotPrompt(name: string) {
    if (!editing) return;
    const newSlug = prompt(`Restore snapshot to a new workbench. New slug:`, `${editing.slug}-restored`);
    if (!newSlug) return;
    snapshotBusy = `r:${name}`;
    try {
      const wb = await api.restoreSnapshot(editing.slug, name, newSlug);
      editing = null;
      await load();
      navigate(`/wb/${wb.slug}`);
    } catch (e) {
      error = String(e);
    } finally {
      snapshotBusy = null;
    }
  }

  async function deleteSnapshotPrompt(name: string) {
    if (!editing) return;
    if (!confirm(`Delete snapshot ${name}? Cannot be undone.`)) return;
    snapshotBusy = `d:${name}`;
    try {
      await api.deleteSnapshot(editing.slug, name);
      editSnapshots = editSnapshots.filter((s) => s.name !== name);
    } catch (e) {
      error = String(e);
    } finally {
      snapshotBusy = null;
    }
  }

  async function runSelfTest() {
    selfTestRunning = true;
    selfTestResult = null;
    try {
      selfTestResult = await api.agentSelfTest();
    } catch (e) {
      error = String(e);
    } finally {
      selfTestRunning = false;
    }
  }

  function fmtBytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
    return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }

  function addCustomField() {
    editCustom = [...editCustom, { key: "", value: "" }];
  }
  function removeCustomField(i: number) {
    editCustom = editCustom.filter((_, idx) => idx !== i);
  }

  function closeEdit() { editing = null; }

  async function saveEdit() {
    if (!editing) return;
    savingEdit = true;
    error = null;
    try {
      const tags = editTags.split(",").map((t) => t.trim()).filter(Boolean);
      const custom_fields: Record<string, string> = {};
      for (const { key, value } of editCustom) {
        const k = key.trim();
        if (k) custom_fields[k] = value;
      }
      await api.patchWorkbench(editing.slug, {
        title: editTitle.trim(),
        description: editDesc,
        url: editUrl.trim() || null,
        ip: editIp.trim() || null,
        local_path: editLocalPath.trim() || null,
        tags,
        custom_fields,
      } as Partial<WorkbenchMeta>);
      editing = null;
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      savingEdit = false;
    }
  }

  async function uploadBanner() {
    if (!editing || !bannerFile || bannerFile.length === 0) return;
    uploadingBanner = true;
    error = null;
    try {
      const f = bannerFile[0];
      const ext = f.name.split(".").pop()?.toLowerCase() ?? "png";
      const path = `banner.${ext}`;
      await api.uploadThemeAsset(editing.slug, path, f);
      // Set workbench banner to point at the uploaded asset.
      await api.patchWorkbench(editing.slug, {
        banner: { kind: "upload", ref: `theme/${path}` },
      } as Partial<WorkbenchMeta>);
      bannerUploadCacheBust = Date.now();
      bannerFile = null;
      // Refresh the editing reference so the preview shows the new banner.
      editing = await api.getWorkbench(editing.slug);
    } catch (e) {
      error = String(e);
    } finally {
      uploadingBanner = false;
    }
  }

  async function clearBanner() {
    if (!editing) return;
    if (!confirm("Clear banner? Workbench falls back to the auto-generated theme banner.")) return;
    try {
      await api.patchWorkbench(editing.slug, { banner: null } as Partial<WorkbenchMeta>);
      bannerUploadCacheBust = Date.now();
      editing = await api.getWorkbench(editing.slug);
    } catch (e) {
      error = String(e);
    }
  }

  function fmtTs(ts: number): string {
    return new Date(ts * 1000).toLocaleTimeString();
  }
  function fmtAgo(ts: number): string {
    const s = Math.round(Date.now() / 1000 - ts);
    if (s < 60) return `${s}s`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}m`;
    return `${Math.round(m / 60)}h`;
  }
  function statusColor(s: number): string {
    if (s >= 500) return "var(--ab-red-bright)";
    if (s >= 400) return "var(--ab-tertiary)";
    if (s >= 300) return "var(--ab-cyan)";
    return "var(--ab-green)";
  }

  async function duplicate(slug: string) {
    busy = `dup:${slug}`;
    try {
      const wb = await api.duplicateWorkbench(slug);
      await load();
      navigate(`/wb/${wb.slug}`);
    } catch (e) {
      error = String(e);
    } finally {
      busy = null;
    }
  }

  async function archive(slug: string) {
    if (!confirm(`Archive ${slug}? Workbench moves to trash; restorable.`)) return;
    busy = `arc:${slug}`;
    try {
      await api.archiveWorkbench(slug);
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      busy = null;
    }
  }

  async function restore(arch: string) {
    busy = `res:${arch}`;
    try {
      await api.restoreWorkbench(arch);
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      busy = null;
    }
  }

  async function purge(arch: string) {
    if (!confirm(`Permanently delete ${arch}? Cannot be undone.`)) return;
    busy = `del:${arch}`;
    try {
      await api.purgeTrash(arch);
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      busy = null;
    }
  }

  async function moveWorkbench(slug: string, dir: -1 | 1) {
    const idx = workbenches.findIndex((w) => w.slug === slug);
    const target = idx + dir;
    if (target < 0 || target >= workbenches.length) return;
    const next = [...workbenches];
    [next[idx], next[target]] = [next[target], next[idx]];
    workbenches = next;
    savingOrder = true;
    try {
      await api.reorderWorkbenches(workbenches.map((w) => w.slug));
    } catch (e) {
      error = String(e);
    } finally {
      savingOrder = false;
    }
  }

  async function clearOrder() {
    if (!confirm("Clear manual order and revert to last-accessed sort?")) return;
    try {
      await api.reorderWorkbenches([]);
      await load();
    } catch (e) {
      error = String(e);
    }
  }

  function fmtDate(s: string): string {
    try { return new Date(s).toLocaleString(); } catch { return s; }
  }
</script>

<main>
  <header>
    <div class="eyebrow label-maker">// CONFIG // SECTOR_MGMT</div>
    <h1 class="display">MANAGEMENT</h1>
    <p class="sub">Edit, duplicate, export, archive, restore, and purge workbenches.</p>
  </header>

  {#if error}
    <div class="error label-maker"><span class="err-tag">SIGNAL_ERROR //</span> {error}</div>
  {/if}

  <section class="console" aria-label="Agent activity">
    <div class="console-bezel">
      <div class="console-screen">
        <div class="console-header">
          <span class="console-title">AGENT_ACTIVITY :: TIMELINE</span>
          <button class="self-test-btn" on:click={runSelfTest} disabled={selfTestRunning}>
            {selfTestRunning ? "RUNNING…" : "▶ SELF_TEST"}
          </button>
          <span class="console-meta">{activity.length} events // refresh 5s</span>
          <span class="console-led" aria-hidden="true"></span>
        </div>
        {#if selfTestResult}
          <div class="self-test-result" class:passed={selfTestResult.pass}>
            <span class="st-verdict">{selfTestResult.pass ? "PASS" : "FAIL"}</span>
            <span class="st-total">{selfTestResult.total_ms.toFixed(1)}ms total</span>
            <span class="st-steps">
              {#each selfTestResult.steps as s}
                <span class="st-step" class:ok={s.ok} title={s.detail || s.name}>
                  {s.ok ? "✓" : "✕"} {s.name} ({s.elapsed_ms.toFixed(1)}ms)
                </span>
              {/each}
            </span>
          </div>
        {/if}
        <div class="console-body">
          {#if activity.length === 0}
            <div class="row idle">// NO_AGENT_ACTIVITY :: STANDING_BY</div>
          {:else}
            {#each activity as e}
              <div class="row">
                <span class="ts">{fmtTs(e.ts)}</span>
                <span class="ago">+{fmtAgo(e.ts)}</span>
                <span class="method">{e.method}</span>
                <span class="path" title={e.path}>{e.path}</span>
                <span class="status" style="color:{statusColor(e.status)}">{e.status}</span>
                <span class="elapsed">{e.elapsed_ms.toFixed(1)}ms</span>
              </div>
            {/each}
          {/if}
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="section-head">
      <h2 class="label-maker">// ACTIVE_WORKBENCHES</h2>
      <div class="section-actions">
        {#if savingOrder}<span class="saving label-maker">// SAVING…</span>{/if}
        <button class="ghost" class:active={reorderMode} on:click={() => (reorderMode = !reorderMode)}>
          {reorderMode ? "DONE" : "REORDER"}
        </button>
        {#if reorderMode}
          <button class="ghost" on:click={clearOrder}>CLEAR (USE LAST_ACCESSED)</button>
        {/if}
      </div>
    </div>
    {#if loading}
      <p class="empty label-maker">// LOADING…</p>
    {:else if workbenches.length === 0}
      <p class="empty label-maker">// NONE_DEPLOYED</p>
    {:else}
      <div class="table">
        <div class="row head label-maker desktop-only">
          <span>SLUG</span>
          <span>TITLE</span>
          <span>UPDATED</span>
          <span>ACTIONS</span>
        </div>
        {#each workbenches as wb, i (wb.slug)}
          <div class="row">
            <div class="cell-slug">
              <span class="slug-mark label-maker">SLUG</span>
              <span class="slug">{wb.slug}</span>
              {#if reorderMode}
                <div class="reorder-controls">
                  <button class="ghost tiny" disabled={i === 0} on:click={() => moveWorkbench(wb.slug, -1)} title="Move up">▲</button>
                  <button class="ghost tiny" disabled={i === workbenches.length - 1} on:click={() => moveWorkbench(wb.slug, 1)} title="Move down">▼</button>
                </div>
              {/if}
            </div>
            <div class="cell-title">
              <div class="title">{wb.title}</div>
              {#if wb.description}<div class="desc">{wb.description}</div>{/if}
              <div class="meta">
                {#if wb.url}<span class="kv"><b>URL</b> <a href={wb.url} target="_blank" rel="noopener">{wb.url}</a></span>{/if}
                {#if wb.ip}<span class="kv"><b>IP</b> <code>{wb.ip}</code></span>{/if}
                {#if wb.local_path}<span class="kv"><b>PATH</b> <code>{wb.local_path}</code></span>{/if}
                {#each Object.entries(wb.custom_fields ?? {}) as [k, v]}
                  <span class="kv"><b>{k.toUpperCase()}</b> <code>{v}</code></span>
                {/each}
              </div>
              {#if wb.tags.length}
                <div class="tags">
                  {#each wb.tags as t}<span class="tag label-maker">{t}</span>{/each}
                </div>
              {/if}
            </div>
            <div class="cell-date label-maker">{fmtDate(wb.updated_at)}</div>
            <div class="cell-actions">
              <button class="ghost" on:click={() => navigate(`/wb/${wb.slug}`)}>OPEN</button>
              <button class="ghost" on:click={() => openEdit(wb)}>EDIT</button>
              <button
                class="ghost"
                disabled={busy === `dup:${wb.slug}`}
                on:click={() => duplicate(wb.slug)}
              >
                {busy === `dup:${wb.slug}` ? "DUPLICATING…" : "DUPLICATE"}
              </button>
              <a class="ghost" href={api.exportWorkbenchUrl(wb.slug)} download>EXPORT (.tar.gz)</a>
              <a class="ghost" href={api.staticExportUrl(wb.slug)} download>STATIC SITE</a>
              <a class="ghost" href={api.auditLogUrl(wb.slug, true)} download>AUDIT</a>
              <button
                class="danger"
                disabled={busy === `arc:${wb.slug}`}
                on:click={() => archive(wb.slug)}
              >
                {busy === `arc:${wb.slug}` ? "ARCHIVING…" : "ARCHIVE"}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <section>
    <h2 class="label-maker">// SCRAP_VAULT (TRASH)</h2>
    {#if trash.length === 0}
      <p class="empty label-maker">// VAULT_EMPTY</p>
    {:else}
      <div class="table trash-table">
        {#each trash as t (t.archive)}
          <div class="row trash-row">
            <code class="trash-name">{t.archive}</code>
            <div class="cell-actions">
              <a class="ghost" href={api.trashDownloadUrl(t.archive)} download>DOWNLOAD</a>
              <button
                class="ghost"
                disabled={busy === `res:${t.archive}`}
                on:click={() => restore(t.archive)}
              >
                {busy === `res:${t.archive}` ? "RESTORING…" : "RESTORE"}
              </button>
              <button
                class="danger"
                disabled={busy === `del:${t.archive}`}
                on:click={() => purge(t.archive)}
              >
                {busy === `del:${t.archive}` ? "PURGING…" : "PURGE"}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</main>

{#if editing}
  <div
    class="modal-backdrop"
    on:click={closeEdit}
    on:keydown={(e) => e.key === "Escape" && closeEdit()}
    role="presentation"
  >
    <div
      class="modal"
      on:click|stopPropagation
      on:keydown|stopPropagation
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-title"
      tabindex="-1"
    >
      <div class="modal-header">
        <span class="label-maker">// EDIT_WORKBENCH</span>
        <span class="modal-slug">{editing.slug}</span>
        <button class="modal-close" on:click={closeEdit} aria-label="Close">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label class="label-maker" for="et">TITLE *</label>
          <input id="et" bind:value={editTitle} />
        </div>
        <div class="field span-2">
          <label class="label-maker" for="ed">DESCRIPTION (markdown)</label>
          <textarea id="ed" bind:value={editDesc} rows="6" placeholder="**bold**, *italic*, `code`, [links](https://…), - bullets, line breaks"></textarea>
          <span class="hint">Renders as Markdown on the workbench dashboard. Plain text works too.</span>
        </div>

        <div class="field span-2 banner-section">
          <span class="label-maker">BANNER IMAGE</span>
          <div class="banner-row">
            <div class="banner-preview">
              <img src={`/api/workbenches/${editing.slug}/banner?cb=${bannerUploadCacheBust}`} alt="banner" />
            </div>
            <div class="banner-controls">
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                bind:files={bannerFile}
              />
              <div class="banner-actions">
                <button class="ghost" on:click={uploadBanner} disabled={uploadingBanner || !bannerFile || bannerFile.length === 0}>
                  {uploadingBanner ? "UPLOADING…" : "UPLOAD"}
                </button>
                {#if editing.banner}
                  <button class="ghost danger" on:click={clearBanner}>CLEAR (USE GENERATED)</button>
                {/if}
              </div>
              <div class="hint">
                Current: {editing.banner ? `${editing.banner.kind} (${editing.banner.ref})` : "auto-generated from theme"}
              </div>
            </div>
          </div>
        </div>
        <div class="field">
          <label class="label-maker" for="eu">URL</label>
          <input id="eu" bind:value={editUrl} placeholder="https://…" />
        </div>
        <div class="field">
          <label class="label-maker" for="ei">IP</label>
          <input id="ei" bind:value={editIp} placeholder="192.168.13.37" />
        </div>
        <div class="field span-2">
          <label class="label-maker" for="ep">LOCAL_PATH</label>
          <input id="ep" bind:value={editLocalPath} placeholder="/Users/me/code/project" />
        </div>
        <div class="field span-2">
          <label class="label-maker" for="etags">TAGS (COMMA-SEP)</label>
          <input id="etags" bind:value={editTags} placeholder="webapp, security" />
        </div>

        <div class="field span-2 snapshots-section">
          <div class="custom-head">
            <span class="label-maker">SNAPSHOTS</span>
            <span class="hint" style="flex:1;text-align:right;">{editSnapshots.length} on disk</span>
          </div>
          <div class="snap-create">
            <input
              bind:value={snapshotLabel}
              placeholder="label (e.g. before-rewrite)"
              on:keydown={(e) => e.key === "Enter" && createSnapshot()}
              aria-label="snapshot label"
            />
            <button class="ghost" on:click={createSnapshot} disabled={creatingSnapshot}>
              {creatingSnapshot ? "SNAPSHOTTING…" : "+ SNAPSHOT NOW"}
            </button>
          </div>
          {#if editSnapshots.length === 0}
            <p class="hint">No snapshots yet. Tip: snapshot before letting an agent run any risky multi-file rewrite — restore-into-new-workbench is one click.</p>
          {:else}
            <ul class="snap-list">
              {#each editSnapshots as s (s.name)}
                <li class="snap-row">
                  <div class="snap-meta">
                    <span class="snap-label">{s.label || "snapshot"}</span>
                    <span class="snap-name">{s.name}</span>
                    <span class="snap-size">{fmtBytes(s.size_bytes)}</span>
                  </div>
                  <div class="snap-actions">
                    <a class="ghost tiny" href={api.snapshotDownloadUrl(editing!.slug, s.name)} download>DL</a>
                    <button class="ghost tiny" disabled={snapshotBusy === `r:${s.name}`} on:click={() => restoreSnapshotPrompt(s.name)}>
                      {snapshotBusy === `r:${s.name}` ? "…" : "RESTORE"}
                    </button>
                    <button class="ghost tiny danger" disabled={snapshotBusy === `d:${s.name}`} on:click={() => deleteSnapshotPrompt(s.name)}>✕</button>
                  </div>
                </li>
              {/each}
            </ul>
          {/if}
        </div>

        <div class="field span-2 custom-fields">
          <div class="custom-head">
            <span class="label-maker">CUSTOM FIELDS</span>
            <button class="ghost tiny" on:click={addCustomField}>+ ADD</button>
          </div>
          {#if editCustom.length === 0}
            <p class="hint">No custom fields. Click + ADD to define a key/value pair (e.g. <code>deploy_cmd: ./deploy.sh</code>). Visible to agents on the workbench manifest.</p>
          {:else}
            <div class="custom-list">
              {#each editCustom as row, i (i)}
                <div class="custom-row">
                  <input
                    class="custom-key"
                    bind:value={row.key}
                    placeholder="key"
                    aria-label="custom field key"
                  />
                  <input
                    class="custom-value"
                    bind:value={row.value}
                    placeholder="value"
                    aria-label="custom field value"
                  />
                  <button class="ghost tiny danger" on:click={() => removeCustomField(i)} title="Remove">✕</button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
      <div class="modal-footer">
        <button class="ghost" on:click={closeEdit}>CANCEL</button>
        <button class="cta" on:click={saveEdit} disabled={savingEdit || !editTitle.trim()}>
          {savingEdit ? "SAVING…" : "SAVE_CHANGES"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  main { max-width: 1200px; margin: 0 auto; padding: 24px 20px 60px; }

  /* ===== Activity terminal at top ===== */
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
    padding: 12px 14px;
    color: var(--ab-green);
    text-shadow: 0 0 6px rgba(109, 213, 140, 0.55);
    background-image:
      repeating-linear-gradient(0deg, rgba(109, 213, 140, 0.06) 0 1px, transparent 1px 3px),
      radial-gradient(ellipse at 50% 0%, rgba(109, 213, 140, 0.12), transparent 70%);
  }
  .console-header {
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
    border-bottom: 1px dashed rgba(109, 213, 140, 0.35);
    padding-bottom: 6px; margin-bottom: 8px;
  }
  .console-title { font-family: var(--ab-font-crt); font-size: 16px; letter-spacing: 0.06em; }
  .console-meta { font-family: var(--ab-font-crt); font-size: 12px; color: var(--ab-yellow); }
  .self-test-btn {
    background: transparent; color: var(--ab-cyan);
    border: 1.5px solid var(--ab-cyan);
    border-radius: 2px;
    padding: 3px 10px;
    font-family: var(--ab-font-crt);
    font-size: 12px;
    letter-spacing: 0.06em;
    cursor: pointer;
    margin-left: auto;
  }
  .self-test-btn:hover:not(:disabled) { background: var(--ab-cyan); color: #000; }
  .self-test-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .self-test-result {
    margin: 6px 0 0;
    padding: 8px 10px;
    background: rgba(255, 75, 75, 0.08);
    border: 1px solid var(--ab-red);
    border-radius: 3px;
    font-family: var(--ab-font-crt);
    font-size: 12px;
    color: var(--ab-red);
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  }
  .self-test-result.passed {
    background: rgba(109, 213, 140, 0.08);
    border-color: var(--ab-green);
    color: var(--ab-green);
  }
  .st-verdict { font-weight: 700; padding: 2px 8px; background: currentColor; color: #000; border-radius: 2px; }
  .st-total { color: var(--ab-muted); }
  .st-steps { display: flex; gap: 12px; flex-wrap: wrap; flex: 1; min-width: 0; }
  .st-step { color: var(--ab-muted); }
  .st-step.ok { color: var(--ab-green); }
  .console-led {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--ab-green);
    box-shadow: 0 0 8px var(--ab-green);
    animation: cblink 1.6s infinite;
  }
  @keyframes cblink { 0%, 60% { opacity: 1; } 70%, 100% { opacity: 0.25; } }
  .console-body {
    font-family: var(--ab-font-crt);
    font-size: 14px;
    line-height: 1.4;
    max-height: 240px;
    overflow-y: auto;
  }
  .console-body .row {
    display: grid;
    grid-template-columns: 90px 50px 56px 1fr 56px 70px;
    gap: 8px;
    align-items: baseline;
    padding: 1px 0;
    white-space: nowrap;
  }
  .console-body .row.idle { display: block; opacity: 0.6; }
  .console-body .ts { color: var(--ab-yellow); }
  .console-body .ago { color: var(--ab-muted); font-size: 12px; }
  .console-body .method { color: var(--ab-cyan); font-weight: 700; }
  .console-body .path { color: var(--ab-green); overflow: hidden; text-overflow: ellipsis; }
  .console-body .status { font-weight: 700; text-align: right; }
  .console-body .elapsed { color: var(--ab-muted); font-size: 12px; text-align: right; }
  @media (max-width: 720px) {
    .console-body .row { grid-template-columns: 70px 40px 1fr 50px; }
    .console-body .ago, .console-body .elapsed { display: none; }
    .console-body { font-size: 12px; }
  }

  @media (max-width: 540px) { main { padding: 16px 12px 40px; } }
  header { margin-bottom: 24px; }
  .eyebrow { color: var(--ab-yellow); margin-bottom: 8px; opacity: 0.9; }
  h1 { margin: 0 0 8px; font-size: clamp(36px, 5vw, 48px); line-height: 0.95; text-shadow: 4px 4px 0 #000, 4px 4px 0 var(--ab-cyan); }
  .sub { color: var(--ab-muted); font-size: 14px; }
  h2 { color: var(--ab-yellow); margin: 28px 0 14px; font-size: 12px; }
  .section-head { display: flex; align-items: center; gap: 12px; margin: 28px 0 14px; flex-wrap: wrap; }
  .section-head h2 { margin: 0; }
  .section-actions { margin-left: auto; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .section-actions .saving { color: var(--ab-cyan); font-size: 10px; }
  .ghost.active { background: var(--ab-yellow); color: #000; border-color: #000; }
  .ghost.tiny { padding: 2px 6px; font-size: 10px; min-width: 24px; }
  .reorder-controls { display: flex; gap: 4px; margin-top: 4px; }

  .table {
    background: var(--ab-surface);
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    overflow: hidden;
  }
  .row {
    display: grid;
    grid-template-columns: 160px 1fr 180px auto;
    align-items: start;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid var(--ab-rule);
  }
  .row:last-child { border-bottom: 0; }
  .row.head { background: var(--ab-bg); color: var(--ab-tertiary); font-size: 11px; padding: 10px 16px; }

  .cell-slug { display: flex; flex-direction: column; gap: 4px; }
  .slug-mark { display: none; color: var(--ab-muted); font-size: 10px; }
  .slug { font-family: var(--ab-font-mono); color: var(--ab-yellow); font-size: 13px; word-break: break-all; }

  .cell-title { display: flex; flex-direction: column; gap: 6px; }
  .title { font-weight: 700; color: var(--ab-ink); font-size: 15px; }
  .desc { color: var(--ab-muted); font-size: 13px; }
  .meta { display: flex; flex-wrap: wrap; gap: 10px; font-size: 11px; color: var(--ab-muted); }
  .kv { display: inline-flex; gap: 6px; align-items: baseline; }
  .kv b { color: var(--ab-tertiary); font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 700; }
  .kv code { font-family: var(--ab-font-mono); }
  .kv a { color: var(--ab-cyan); text-decoration: none; }
  .kv a:hover { text-decoration: underline; }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .tag { background: var(--ab-bg); color: var(--ab-muted); border: 1px solid var(--ab-rule); padding: 2px 8px; border-radius: 2px; font-size: 9px; }

  .cell-date { font-size: 11px; color: var(--ab-muted); padding-top: 4px; }
  .cell-actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }

  .trash-row { grid-template-columns: 1fr auto; }
  .trash-name { font-family: var(--ab-font-mono); color: var(--ab-muted); font-size: 12px; word-break: break-all; }

  button, a.ghost {
    background: transparent; color: var(--ab-muted);
    border: 1.5px solid var(--ab-rule-strong);
    border-radius: var(--ab-radius);
    padding: 6px 10px; cursor: pointer;
    font-family: var(--ab-font-stencil);
    font-size: 11px; letter-spacing: 0.06em;
    text-transform: uppercase; text-decoration: none;
    box-shadow: var(--ab-shadow-bolt);
    display: inline-block;
  }
  button:hover, a.ghost:hover { background: var(--ab-yellow); color: #000; border-color: #000; transform: translate(-1px,-1px); box-shadow: 3px 3px 0 #000; }
  button.danger { color: var(--ab-red); border-color: var(--ab-red); }
  button.danger:hover { background: var(--ab-red); color: var(--ab-ink); border-color: #000; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }

  .empty { color: var(--ab-muted); font-size: 13px; }
  .error {
    background: var(--ab-bg); color: var(--ab-red-bright);
    border: 2.5px solid var(--ab-red); padding: 12px 16px; border-radius: var(--ab-radius);
    margin-bottom: 14px; font-size: 12px; box-shadow: var(--ab-shadow-bolt);
  }
  .err-tag { background: var(--ab-red); color: #000; padding: 2px 8px; margin-right: 8px; border-radius: 2px; }

  /* mobile: stack the row into vertical cells */
  @media (max-width: 880px) {
    .desktop-only { display: none; }
    .row { grid-template-columns: 1fr; gap: 10px; }
    .slug-mark { display: inline; }
    .cell-actions { justify-content: flex-start; }
    .cell-date::before { content: "UPDATED "; color: var(--ab-tertiary); font-weight: 700; }
  }

  /* ===== Edit modal ===== */
  .modal-backdrop {
    position: fixed; inset: 0; z-index: 100;
    background: rgba(0, 0, 0, 0.7);
    display: grid; place-items: center;
    padding: 20px;
  }
  .modal {
    width: min(640px, 100%);
    max-height: 90vh;
    overflow: auto;
    background: var(--ab-surface);
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard-lg);
    border-radius: var(--ab-radius);
    display: flex; flex-direction: column;
  }
  .modal-header {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px;
    background: var(--ab-yellow); color: #000;
    border-bottom: 2.5px solid #000;
  }
  .modal-header .label-maker { color: #000; }
  .modal-slug { font-family: var(--ab-font-mono); font-size: 13px; flex: 1; }
  .modal-close {
    background: #000; color: var(--ab-yellow);
    border: 2px solid #000;
    padding: 4px 10px; cursor: pointer;
    font-size: 12px;
  }
  .modal-body {
    padding: 18px;
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .modal-body .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .modal-body .field.span-2 { grid-column: 1 / -1; }
  .modal-body .field label { color: var(--ab-yellow); font-size: 11px; }
  .modal-body input, .modal-body textarea {
    background: var(--ab-bg); border: 2px solid var(--ab-rule);
    color: var(--ab-ink); padding: 11px 12px;
    border-radius: var(--ab-radius);
    font-family: var(--ab-font-mono); font-size: 14px;
    min-width: 0; resize: vertical;
  }
  .modal-body input:focus, .modal-body textarea:focus { outline: none; border-color: var(--ab-yellow); box-shadow: 0 0 0 3px rgba(125, 211, 252, 0.25); }
  .modal-body .hint { color: var(--ab-muted); font-size: 11px; }
  .banner-section { padding: 12px; background: var(--ab-bg); border: 2px dashed var(--ab-rule); border-radius: var(--ab-radius); }
  .banner-row { display: grid; grid-template-columns: 200px 1fr; gap: 14px; align-items: start; }
  .banner-preview { aspect-ratio: 16 / 5; background: #000; border: 2px solid #000; overflow: hidden; }
  .banner-preview img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .banner-controls { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .banner-controls input[type="file"] { color: var(--ab-muted); }
  .banner-actions { display: flex; gap: 6px; flex-wrap: wrap; }

  /* Snapshots */
  .snapshots-section { background: var(--ab-bg); border: 2px dashed var(--ab-rule); padding: 12px; border-radius: var(--ab-radius); }
  .snap-create { display: flex; gap: 8px; margin: 8px 0; }
  .snap-create input { flex: 1; min-width: 0; background: var(--ab-bg); border: 2px solid var(--ab-rule); color: var(--ab-ink); padding: 8px 10px; border-radius: var(--ab-radius); font: inherit; font-family: var(--ab-font-mono); font-size: 13px; }
  .snap-create input:focus { outline: none; border-color: var(--ab-yellow); }
  .snap-list { list-style: none; padding: 0; margin: 4px 0 0; display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow-y: auto; }
  .snap-row { display: flex; align-items: center; gap: 12px; padding: 8px 10px; background: var(--ab-surface); border: 1px solid var(--ab-rule); border-radius: 3px; flex-wrap: wrap; }
  .snap-meta { display: flex; gap: 10px; align-items: baseline; flex: 1; min-width: 0; flex-wrap: wrap; }
  .snap-label { color: var(--ab-yellow); font-weight: 700; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }
  .snap-name { color: var(--ab-muted); font-family: var(--ab-font-mono); font-size: 11px; word-break: break-all; }
  .snap-size { color: var(--ab-muted); font-family: var(--ab-font-mono); font-size: 10px; }
  .snap-actions { display: flex; gap: 4px; }
  .snap-actions a, .snap-actions button { padding: 3px 8px; font-size: 10px; }

  /* Custom fields */
  .custom-fields { background: var(--ab-bg); border: 2px dashed var(--ab-rule); padding: 12px; border-radius: var(--ab-radius); }
  .custom-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .custom-list { display: flex; flex-direction: column; gap: 6px; }
  .custom-row { display: grid; grid-template-columns: 200px 1fr auto; gap: 8px; align-items: center; }
  .custom-key, .custom-value {
    background: var(--ab-bg); border: 2px solid var(--ab-rule); color: var(--ab-ink);
    padding: 8px 10px; border-radius: var(--ab-radius);
    font-family: var(--ab-font-mono); font-size: 13px; min-width: 0;
  }
  .custom-key { color: var(--ab-yellow); }
  .custom-key:focus, .custom-value:focus { outline: none; border-color: var(--ab-yellow); }
  @media (max-width: 540px) {
    .custom-row { grid-template-columns: 1fr auto; }
    .custom-row .custom-key { grid-column: 1 / -1; }
    .custom-row .custom-value { grid-column: 1; }
  }
  @media (max-width: 540px) {
    .banner-row { grid-template-columns: 1fr; }
  }
  .modal-footer {
    display: flex; gap: 8px; justify-content: flex-end;
    padding: 14px 18px;
    border-top: 2px solid #000;
    background: var(--ab-bg);
  }
  .cta {
    background: var(--ab-red); color: var(--ab-on-red);
    border: 2.5px solid #000; box-shadow: var(--ab-shadow-bolt);
    border-radius: var(--ab-radius); padding: 10px 18px;
    cursor: pointer;
    font-family: var(--ab-font-stencil); font-size: 12px; letter-spacing: 0.06em;
  }
  .cta:hover { background: var(--ab-red-bright); transform: translate(-1px,-1px); box-shadow: 3px 3px 0 #000; }
  .cta:disabled { opacity: 0.5; cursor: not-allowed; }
  @media (max-width: 540px) {
    .modal-body { grid-template-columns: 1fr; padding: 14px; }
    .modal-body .field.span-2 { grid-column: 1; }
    .modal-footer { flex-direction: column; padding: 12px; }
    .modal-footer > * { width: 100%; }
  }
</style>
