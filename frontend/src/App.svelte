<script lang="ts">
  import { onMount } from "svelte";
  import { route, match } from "./lib/router";
  import { installBridge } from "./lib/bridge";
  import { api, type Theme, type WorkbenchMeta, type ObjectMeta } from "./lib/api";

  import TopNav from "./lib/chrome/TopNav.svelte";
  import Dashboard from "./lib/chrome/Dashboard.svelte";
  import Settings from "./lib/chrome/Settings.svelte";
  import Blueprints from "./lib/chrome/Blueprints.svelte";
  import ImageViewer from "./lib/chrome/ImageViewer.svelte";
  import FileBrowser from "./lib/chrome/FileBrowser.svelte";
  import ResponsesHistory from "./lib/chrome/ResponsesHistory.svelte";

  import WorkbenchDashboard from "./lib/themed/WorkbenchDashboard.svelte";
  import MdViewer from "./lib/themed/MdViewer.svelte";
  import HtmlViewer from "./lib/themed/HtmlViewer.svelte";
  import RunbookViewer from "./lib/themed/RunbookViewer.svelte";

  // Lazy-load CodeMirror-heavy components so initial bundle stays small.
  let EditorMod: any = null;
  let ThemeEditorMod: any = null;
  function loadEditor() {
    if (!EditorMod) import("./lib/chrome/Editor.svelte").then((m) => (EditorMod = m.default));
  }
  function loadThemeEditor() {
    if (!ThemeEditorMod) import("./lib/themed/ThemeEditor.svelte").then((m) => (ThemeEditorMod = m.default));
  }

  let activeTheme: Theme | null = null;
  let activeWorkbench: WorkbenchMeta | null = null;
  let viewedObject: ObjectMeta | null = null;

  onMount(installBridge);

  let lastSlug: string | null = null;
  $: {
    const path = $route.path;
    const m =
      match("/wb/:slug", path) ||
      match("/wb/:slug/files", path) ||
      match("/wb/:slug/theme", path) ||
      match("/wb/:slug/o/:oid", path) ||
      match("/wb/:slug/o/:oid/edit", path) ||
      match("/wb/:slug/o/:oid/responses", path);
    const slug = m?.slug ?? null;
    if (slug !== lastSlug) {
      lastSlug = slug;
      if (slug) {
        api.getWorkbench(slug).then((wb) => (activeWorkbench = wb)).catch(() => (activeWorkbench = null));
        api.getTheme(slug).then((t) => (activeTheme = t)).catch(() => (activeTheme = null));
      } else {
        activeWorkbench = null;
        activeTheme = null;
      }
      viewedObject = null;
    }
  }

  let lastOidKey: string | null = null;
  $: {
    const m = match("/wb/:slug/o/:oid", $route.path);
    const key = m ? `${m.slug}/${m.oid}` : null;
    if (key !== lastOidKey) {
      lastOidKey = key;
      if (m) {
        api.getObject(m.slug, m.oid).then((o) => (viewedObject = o)).catch(() => (viewedObject = null));
      } else {
        viewedObject = null;
      }
    }
  }

  // Trigger lazy load when a route that needs it becomes active.
  $: if (match("/wb/:slug/o/:oid/edit", $route.path)) loadEditor();
  $: if (match("/wb/:slug/theme", $route.path)) loadThemeEditor();
</script>

<div class="shell">
  <div class="stack">
    <TopNav theme={activeTheme} workbenchTitle={activeWorkbench?.title ?? null} />

    <div class="content">
      {#if $route.path === "/"}
        <Dashboard />
      {:else if $route.path === "/settings"}
        <Settings />
      {:else if $route.path === "/blueprints"}
        <Blueprints />
      {:else if match("/wb/:slug", $route.path)}
        {@const m1 = match("/wb/:slug", $route.path)}
        {#if m1}
          <WorkbenchDashboard
            slug={m1.slug}
            onTheme={(t) => (activeTheme = t)}
            onWorkbench={(w) => (activeWorkbench = w)}
          />
        {/if}
      {:else if match("/wb/:slug/files", $route.path)}
        {@const m2 = match("/wb/:slug/files", $route.path)}
        {#if m2}<FileBrowser slug={m2.slug} />{/if}
      {:else if match("/wb/:slug/theme", $route.path)}
        {@const m3 = match("/wb/:slug/theme", $route.path)}
        {#if m3}
          {#if ThemeEditorMod}
            <svelte:component this={ThemeEditorMod} slug={m3.slug} />
          {:else}
            <p class="loading label-maker">// LOADING THEME EDITOR…</p>
          {/if}
        {/if}
      {:else if match("/wb/:slug/o/:oid/responses", $route.path)}
        {@const mr = match("/wb/:slug/o/:oid/responses", $route.path)}
        {#if mr}<ResponsesHistory slug={mr.slug} oid={mr.oid} />{/if}
      {:else if match("/wb/:slug/o/:oid/edit", $route.path)}
        {@const m4 = match("/wb/:slug/o/:oid/edit", $route.path)}
        {#if m4}
          {#if EditorMod}
            <svelte:component this={EditorMod} slug={m4.slug} oid={m4.oid} />
          {:else}
            <p class="loading label-maker">// LOADING EDITOR…</p>
          {/if}
        {/if}
      {:else if match("/wb/:slug/o/:oid", $route.path)}
        {@const m5 = match("/wb/:slug/o/:oid", $route.path)}
        {#if m5}
          {#if !viewedObject}
            <p class="loading label-maker">// LOADING…</p>
          {:else if viewedObject.kind === "image"}
            <ImageViewer slug={m5.slug} oid={m5.oid} />
          {:else if viewedObject.kind === "md"}
            <MdViewer slug={m5.slug} oid={m5.oid} />
          {:else if viewedObject.kind === "html" || viewedObject.kind === "approval-html" || viewedObject.kind === "qa-form"}
            <HtmlViewer slug={m5.slug} oid={m5.oid} />
          {:else if viewedObject.kind === "runbook"}
            <RunbookViewer slug={m5.slug} oid={m5.oid} />
          {:else}
            <FileBrowser slug={m5.slug} />
          {/if}
        {/if}
      {:else}
        <main class="not-found">
          <h1 class="display">SIGNAL_LOST</h1>
          <p class="label-maker">// NO ROUTE MATCHES <code>{$route.path}</code></p>
        </main>
      {/if}
    </div>

    {#if $route.path === "/" || $route.path === "/blueprints" || $route.path === "/settings"}
      <footer class="credit label-maker">
        made by <a href="https://gainsec.com/" target="_blank" rel="noopener noreferrer">Jon &lsquo;GainSec&rsquo; Gaines</a>
      </footer>
    {/if}
  </div>
</div>

<style>
  .shell {
    display: flex;
    min-height: 100vh;
  }
  .stack {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .content {
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .not-found {
    max-width: 600px;
    margin: 0 auto;
    padding: 64px 24px;
    text-align: center;
  }
  .not-found h1 { font-size: 56px; margin: 0 0 12px; text-shadow: 4px 4px 0 #000, 4px 4px 0 var(--ab-red); }
  .not-found p { color: var(--ab-muted); font-size: 12px; }
  .not-found code { font-family: var(--ab-font-mono); }
  .loading { padding: 32px; color: var(--ab-muted); }
  .credit {
    text-align: center;
    padding: 24px 16px 32px;
    font-size: 10px;
    color: var(--ab-muted);
    opacity: 0.55;
    letter-spacing: 0.08em;
  }
  .credit a { color: inherit; text-decoration: underline; text-decoration-color: var(--ab-rule-strong); text-underline-offset: 3px; }
  .credit a:hover { color: var(--ab-yellow); text-decoration-color: var(--ab-yellow); }
</style>
