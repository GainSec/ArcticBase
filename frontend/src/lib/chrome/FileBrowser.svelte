<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ObjectMeta } from "../api";
  import { navigate } from "../router";

  export let slug: string;

  let objects: ObjectMeta[] = [];
  let loading = true;
  let uploading = false;
  let error: string | null = null;
  let fileInput: HTMLInputElement;

  async function load() {
    try {
      objects = (await api.listObjects(slug)).filter((o) => o.kind === "file" || o.kind === "image");
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function upload() {
    if (!fileInput.files?.length) return;
    uploading = true;
    error = null;
    try {
      for (const f of Array.from(fileInput.files)) {
        const isImage = f.type.startsWith("image/");
        await api.uploadObject(
          slug,
          { kind: isImage ? "image" : "file", title: f.name, drawer: isImage ? "images" : "files" },
          f,
        );
      }
      fileInput.value = "";
      await load();
    } catch (e) {
      error = String(e);
    } finally {
      uploading = false;
    }
  }

  function fmt(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
    return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }
</script>

<main>
  <header>
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← Back</button>
    <h1>Files</h1>
  </header>
  <section class="upload">
    <input type="file" bind:this={fileInput} multiple />
    <button on:click={upload} disabled={uploading}>{uploading ? "Uploading…" : "Upload"}</button>
  </section>
  {#if error}<div class="error">{error}</div>{/if}
  {#if loading}
    <p>Loading…</p>
  {:else if objects.length === 0}
    <p class="empty">No files yet.</p>
  {:else}
    <table>
      <thead>
        <tr><th>Name</th><th>Kind</th><th>Size</th><th></th></tr>
      </thead>
      <tbody>
        {#each objects as o (o.id)}
          <tr>
            <td>{o.title || o.filename}</td>
            <td><span class="kind">{o.kind}</span></td>
            <td>{fmt(o.size_bytes)}</td>
            <td class="actions">
              {#if o.kind === "image"}
                <button on:click={() => navigate(`/wb/${slug}/o/${o.id}`)}>View</button>
              {/if}
              <a href={`/api/workbenches/${slug}/objects/${o.id}/content`} download={o.filename}>Download</a>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</main>

<style>
  main { max-width: 1100px; margin: 0 auto; padding: 28px 24px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }
  h1 { margin: 0; font-size: 32px; font-weight: 700; letter-spacing: -0.02em; text-transform: uppercase; }
  .upload {
    display: flex; gap: 12px; margin-bottom: 20px; align-items: center; flex-wrap: wrap;
    background: var(--ab-surface); border: 2px dashed var(--ab-rule-strong); padding: 16px;
    border-radius: var(--ab-radius);
  }
  input[type=file] { color: var(--ab-muted); font: inherit; font-size: 13px; }
  button {
    background: var(--ab-primary-bright); border: 2px solid #000; color: var(--ab-on-primary);
    padding: 9px 16px; border-radius: var(--ab-radius); cursor: pointer; box-shadow: 2px 2px 0 #000;
    font: inherit; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  }
  button:hover { transform: translate(-1px, -1px); box-shadow: 3px 3px 0 #000; }
  button.back { background: transparent; color: inherit; border: none; padding: 4px 8px; box-shadow: none; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  table { width: 100%; border-collapse: collapse; background: var(--ab-surface); border: 2px solid #000; box-shadow: var(--ab-shadow-hard); border-radius: var(--ab-radius); overflow: hidden; }
  th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--ab-rule); font-size: 14px; }
  th { color: var(--ab-tertiary); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; background: var(--ab-bg); }
  .kind { font-family: var(--ab-font-mono); font-size: 10px; padding: 2px 8px; background: var(--ab-bg); border: 1px solid var(--ab-rule); border-radius: 2px; color: var(--ab-muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
  .actions a { color: var(--ab-primary); text-decoration: none; padding: 4px 8px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  .actions button { padding: 4px 10px; font-size: 11px; }
  .error { background: var(--ab-bg); color: var(--ab-error); padding: 10px 14px; border: 2px solid var(--ab-error); border-radius: var(--ab-radius); margin-bottom: 12px; }
  .empty { color: var(--ab-muted); font-size: 13px; }
</style>
