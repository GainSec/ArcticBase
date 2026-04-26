<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { EditorState } from "@codemirror/state";
  import { EditorView, keymap, lineNumbers } from "@codemirror/view";
  import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
  import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from "@codemirror/language";
  import { markdown } from "@codemirror/lang-markdown";
  import { oneDark } from "@codemirror/theme-one-dark";
  import { api, type Theme } from "../api";
  import { navigate } from "../router";
  import ThemeWrapper from "./ThemeWrapper.svelte";

  export let slug: string;

  const STARTER = `---
name: New Theme
core:
  bg: '#fafafa'
  surface: '#ffffff'
  ink: '#1a1a1a'
  muted: '#5c5c5c'
  rule: '#d9d3c7'
  accent: '#7a1f1f'
  accent-2: '#2a5562'
  success: '#2c6e3a'
  error: '#a52a2a'
typography:
  body: { fontFamily: '"Charter","Palatino","Georgia",serif', fontSize: '16px', fontWeight: '400', lineHeight: '1.55' }
  mono: { fontFamily: '"JetBrains Mono","Menlo",monospace', fontSize: '13px', fontWeight: '400', lineHeight: '1.4' }
rounded: { sm: '0.25rem', md: '0.5rem', lg: '1rem' }
spacing: { unit: '8px', gutter: '24px', margin: '32px' }
custom: {}
---

# Workbench Theme

Describe brand voice and component metaphors here.
`;

  let host: HTMLDivElement;
  let view: EditorView | null = null;
  let theme: Theme | null = null;
  let raw = "";
  let saving = false;
  let saved = false;
  let error: string | null = null;

  onMount(async () => {
    try {
      raw = await api.getThemeRaw(slug);
    } catch {
      raw = STARTER;
    }
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: raw,
        extensions: [
          lineNumbers(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          indentOnInput(),
          syntaxHighlighting(defaultHighlightStyle),
          markdown(),
          oneDark,
          EditorView.updateListener.of((u) => {
            if (u.docChanged) saved = false;
          }),
        ],
      }),
    });
    try {
      theme = await api.getTheme(slug);
    } catch {
      theme = null;
    }
  });

  onDestroy(() => view?.destroy());

  async function save() {
    if (!view) return;
    saving = true;
    error = null;
    try {
      const text = view.state.doc.toString();
      theme = await api.putTheme(slug, text);
      saved = true;
    } catch (e) {
      error = String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="wrap">
  <div class="bar">
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← Back</button>
    <span class="title">Theme</span>
    <span class="spacer"></span>
    {#if saved}<span class="ok">saved</span>{/if}
    <button class="primary" on:click={save} disabled={saving}>
      {saving ? "Saving…" : "Save"}
    </button>
  </div>
  {#if error}<div class="error">{error}</div>{/if}
  <div class="panes">
    <div class="editor" bind:this={host}></div>
    <div class="preview">
      {#if theme}
        <ThemeWrapper {theme}>
          <div class="preview-inner">
            <h1>{theme.tokens.name || "Untitled"}</h1>
            <p>Body text in <code>--wb-font-body</code>. Accent: <span class="accent">accent</span> — Success: <span class="success">success</span> — Error: <span class="err">error</span>.</p>
            <button class="btn">Themed button</button>
            <pre>code in --wb-font-mono</pre>
          </div>
        </ThemeWrapper>
      {:else}
        <p class="no-theme">No valid theme yet.</p>
      {/if}
    </div>
  </div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: calc(100vh - 53px); }
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: var(--ab-surface); border-bottom: 2px solid #000; font-family: var(--ab-font-body); }
  .title { font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }
  .spacer { flex: 1; }
  .ok { font-size: 10px; padding: 3px 8px; border-radius: 2px; background: #133a23; color: #6dd58c; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
  button { background: var(--ab-bg); border: 1.5px solid var(--ab-rule); color: inherit; padding: 7px 12px; border-radius: var(--ab-radius); cursor: pointer; font: inherit; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  button.primary { background: var(--ab-primary-bright); border: 2px solid #000; color: var(--ab-on-primary); box-shadow: 2px 2px 0 #000; }
  button.primary:hover { transform: translate(-1px, -1px); box-shadow: 3px 3px 0 #000; }
  button.back { background: transparent; border: none; }
  button:disabled { opacity: 0.5; }
  .panes { flex: 1; min-height: 0; display: grid; grid-template-columns: 1fr 1fr; }
  @media (max-width: 800px) { .panes { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; } }
  .editor { overflow: auto; border-right: 2px solid #000; }
  :global(.cm-editor) { height: 100%; }
  .preview { overflow: auto; background: white; }
  .preview-inner { padding: 32px; }
  .accent { color: var(--wb-accent); font-weight: 600; }
  .success { color: var(--wb-success); }
  .err { color: var(--wb-error); }
  .btn { background: var(--wb-accent); color: var(--wb-bg); border: none; padding: 8px 16px; border-radius: var(--wb-rounded-md); cursor: pointer; }
  pre { background: var(--wb-surface); padding: 8px; border-radius: var(--wb-rounded-sm); font-family: var(--wb-font-mono); }
  .error { background: var(--ab-bg); color: var(--ab-error); padding: 8px 16px; border-bottom: 2px solid var(--ab-error); }
  .no-theme { padding: 32px; color: var(--ab-muted); }
</style>
