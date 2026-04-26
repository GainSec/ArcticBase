<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { api, type ObjectMeta } from "../api";
  import { navigate } from "../router";

  export let slug: string;
  export let oid: string;

  let meta: ObjectMeta | null = null;
  let url: string | null = null;
  let error: string | null = null;

  onMount(async () => {
    try {
      meta = await api.getObject(slug, oid);
      const { blob } = await api.getObjectContentBlob(slug, oid);
      url = URL.createObjectURL(blob);
    } catch (e) {
      error = String(e);
    }
  });

  onDestroy(() => {
    if (url) URL.revokeObjectURL(url);
  });
</script>

<div class="wrap">
  <div class="bar">
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← Back</button>
    {#if meta}<span class="title">{meta.title || meta.filename}</span>{/if}
    <span class="spacer"></span>
    {#if url && meta}
      <a href={url} download={meta.filename || `${oid}.bin`}>Download</a>
    {/if}
  </div>
  {#if error}<div class="error">{error}</div>{/if}
  {#if url}
    <div class="canvas">
      <img src={url} alt={meta?.title ?? "image"} />
    </div>
  {/if}
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: calc(100vh - 53px); }
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: var(--ab-surface); border-bottom: 2px solid #000; font-family: var(--ab-font-body); }
  .title { font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
  .spacer { flex: 1; }
  .canvas { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 16px; background: var(--ab-bg); overflow: auto; }
  img { max-width: 100%; max-height: 100%; object-fit: contain; }
  a { color: var(--ab-primary); text-decoration: none; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  button.back { background: transparent; border: none; color: inherit; cursor: pointer; font: inherit; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
  .error { background: var(--ab-bg); color: var(--ab-error); padding: 8px 16px; border-bottom: 2px solid var(--ab-error); }
</style>
