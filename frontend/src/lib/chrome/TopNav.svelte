<script lang="ts">
  import { onMount } from "svelte";
  import { navigate } from "../router";
  import { api, type Theme, type WorkbenchMeta } from "../api";
  import { themeToCssVars } from "../theme";

  export let theme: Theme | null = null;
  export let workbenchTitle: string | null = null;

  let query = "";
  let allWorkbenches: WorkbenchMeta[] = [];
  let showSuggestions = false;

  onMount(async () => {
    try {
      allWorkbenches = await api.listWorkbenches();
    } catch {
      // ignore
    }
  });

  $: results = query.trim()
    ? allWorkbenches
        .filter((w) =>
          (w.title + " " + w.slug + " " + (w.description || "") + " " + w.tags.join(" "))
            .toLowerCase()
            .includes(query.toLowerCase())
        )
        .slice(0, 6)
    : [];

  $: themed = theme !== null;
  $: vars = theme ? themeToCssVars(theme) : "";
</script>

<div class="nav-shell" class:themed style={vars}>
  <nav>
    <button class="brand" on:click={() => navigate("/")} aria-label="Arctic Base — Home">
      <img class="logo" src="/arctic-base-logo-256.png" alt="Arctic Base" />
    </button>

    {#if workbenchTitle}
      <span class="sep" aria-hidden="true">//</span>
      <span class="wb-title label-maker">SECTOR_{workbenchTitle.replace(/[^a-zA-Z0-9]+/g, "_").toUpperCase()}</span>
    {/if}

    <div class="search">
      <span class="search-icon" aria-hidden="true">⌕</span>
      <input
        bind:value={query}
        on:focus={() => (showSuggestions = true)}
        on:blur={() => setTimeout(() => (showSuggestions = false), 120)}
        placeholder="QUERY_DATABASE…"
        spellcheck="false"
        autocomplete="off"
      />
      {#if showSuggestions && results.length > 0}
        <ul class="suggest">
          {#each results as r (r.slug)}
            <li>
              <button on:mousedown={() => { navigate(`/wb/${r.slug}`); query = ""; }}>
                <span class="r-title">{r.title}</span>
                <span class="r-slug label-maker">// {r.slug}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <span class="status-pip" title="System nominal">
      <span class="dot"></span>
      <span class="label-maker">NOMINAL</span>
    </span>

    <button class="ghost label-maker" on:click={() => navigate("/blueprints")}>BLUEPRINTS</button>
    <button class="ghost label-maker" on:click={() => navigate("/settings")}>SETTINGS</button>
  </nav>

  <div class="caution-tape under-tape" aria-hidden="true"></div>
</div>

<style>
  .nav-shell { position: sticky; top: 0; z-index: 50; }
  nav {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 20px;
    background: var(--ab-surface);
    color: var(--ab-ink);
    border-bottom: 3px solid #000;
    box-shadow: 0 4px 0 var(--ab-bg);
    font-family: var(--ab-font-body);
    background-image: linear-gradient(180deg, rgba(255, 244, 214, 0.04), transparent);
  }
  .nav-shell.themed nav {
    background: var(--wb-surface, var(--ab-surface));
    color: var(--wb-ink, var(--ab-ink));
    border-bottom-color: #000;
    font-family: var(--wb-font-body, var(--ab-font-body));
    background-image: none;
  }
  .under-tape { height: 6px; border-bottom: 2px solid #000; }
  .brand { display: inline-flex; align-items: center; background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-family: inherit; }
  .logo { height: 44px; width: auto; display: block; filter: drop-shadow(2px 2px 0 #000); }
  .sep { opacity: 0.5; font-family: var(--ab-font-mono); font-weight: 700; }
  .wb-title { color: var(--ab-yellow); }
  .nav-shell.themed .wb-title { color: var(--wb-accent, var(--ab-yellow)); }

  .search {
    flex: 1;
    max-width: 420px;
    position: relative;
    margin: 0 8px;
  }
  .search-icon {
    position: absolute;
    top: 50%;
    left: 10px;
    transform: translateY(-50%);
    color: var(--ab-muted);
    font-size: 16px;
    pointer-events: none;
  }
  .search input {
    width: 100%;
    background: var(--ab-bg);
    color: var(--ab-ink);
    border: 2px solid var(--ab-rule);
    border-radius: var(--ab-radius);
    padding: 8px 10px 8px 30px;
    font: inherit;
    font-family: var(--ab-font-mono);
    font-size: 12px;
    letter-spacing: 0.04em;
  }
  .search input:focus { outline: none; border-color: var(--ab-yellow); }
  .nav-shell.themed .search input {
    background: var(--wb-bg, var(--ab-bg));
    color: var(--wb-ink, var(--ab-ink));
    border-color: var(--wb-rule, var(--ab-rule));
  }
  .suggest {
    position: absolute;
    top: calc(100% + 4px);
    left: 0; right: 0;
    list-style: none;
    margin: 0;
    padding: 0;
    background: var(--ab-surface-2);
    border: 2.5px solid #000;
    box-shadow: var(--ab-shadow-hard);
    border-radius: var(--ab-radius);
    z-index: 60;
    overflow: hidden;
  }
  .suggest li button {
    width: 100%;
    background: transparent;
    color: var(--ab-ink);
    border: 0;
    padding: 8px 12px;
    text-align: left;
    cursor: pointer;
    font: inherit;
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: center;
  }
  .suggest li button:hover { background: var(--ab-yellow); color: #000; }
  .r-title { font-weight: 700; font-size: 13px; }
  .r-slug { font-size: 10px; opacity: 0.7; }

  .status-pip { display: inline-flex; align-items: center; gap: 6px; color: var(--ab-green); }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--ab-green); box-shadow: 0 0 8px var(--ab-green), 0 0 0 2px #000; }
  .nav-shell.themed .status-pip { color: var(--wb-success, var(--ab-green)); }
  .nav-shell.themed .dot { background: var(--wb-success, var(--ab-green)); box-shadow: 0 0 8px var(--wb-success, var(--ab-green)), 0 0 0 2px #000; }

  .ghost { background: transparent; border: 2px solid currentColor; color: inherit; border-radius: var(--ab-radius); padding: 8px 12px; cursor: pointer; font-family: inherit; box-shadow: var(--ab-shadow-bolt); transition: transform 0.05s, box-shadow 0.05s; }
  .ghost:hover { transform: translate(-1px, -1px); box-shadow: 3px 3px 0 #000; background: var(--ab-yellow); color: #000; border-color: #000; }
  .ghost:active { transform: translate(2px, 2px); box-shadow: 0 0 0 #000; }

  @media (max-width: 720px) {
    nav { gap: 8px; padding: 10px 12px; }
    .wb-title { display: none; }
    .logo { height: 36px; }
    .sep { display: none; }
    .search { display: none; }
    .status-pip { display: none; }
    .ghost { padding: 6px 10px; font-size: 11px; }
  }
</style>
