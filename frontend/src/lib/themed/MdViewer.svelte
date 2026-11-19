<script lang="ts">
  import type { ObjectMeta } from "../api";
  import { navigate } from "../router";

  export let slug: string;
  export let oid: string;
  export let meta: ObjectMeta;

  $: url = `/api/workbenches/${slug}/objects/${oid}/render`;

</script>

<div class="wrap">
  <div class="bar">
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← Back</button>
    {#if meta}<span class="title">{meta.title}</span>{/if}
    <span class="spacer"></span>
    {#if meta}<button on:click={() => navigate(`/wb/${slug}/o/${oid}/edit`)}>Edit</button>{/if}
  </div>
  {#if url}
    <iframe title={meta?.title ?? "doc"} src={url}></iframe>
  {/if}
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: calc(100vh - 53px); }
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: var(--ab-surface); border-bottom: 2px solid #000; font-family: var(--ab-font-body); }
  .title { font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
  .spacer { flex: 1; }
  button { background: var(--ab-bg); border: 1.5px solid var(--ab-rule); color: inherit; padding: 7px 12px; border-radius: var(--ab-radius); cursor: pointer; font: inherit; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  button.back { background: transparent; border: none; }
  iframe { flex: 1; min-height: 0; width: 100%; border: 0; background: white; }
</style>
