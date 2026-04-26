<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { EditorState } from "@codemirror/state";
  import { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view";
  import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
  import { syntaxHighlighting, defaultHighlightStyle, indentOnInput, bracketMatching } from "@codemirror/language";
  import { markdown } from "@codemirror/lang-markdown";
  import { html } from "@codemirror/lang-html";
  import { oneDark } from "@codemirror/theme-one-dark";
  import { api } from "../api";
  import { navigate } from "../router";

  export let slug: string;
  export let oid: string;

  let host: HTMLDivElement;
  let view: EditorView | null = null;
  let etag = "";
  let saving = false;
  let saved = false;
  let error: string | null = null;
  let kind = "";
  let title = "";
  let dirty = false;
  let uploadingImage = false;

  function lang(meta_kind: string, filename: string) {
    if (meta_kind === "md" || filename.endsWith(".md")) return markdown();
    return html();
  }

  onMount(async () => {
    try {
      const meta = await api.getObject(slug, oid);
      kind = meta.kind;
      title = meta.title;
      const { text, etag: e } = await api.getObjectContentText(slug, oid);
      etag = e;
      view = new EditorView({
        parent: host,
        state: EditorState.create({
          doc: text,
          extensions: [
            lineNumbers(),
            highlightActiveLine(),
            history(),
            keymap.of([...defaultKeymap, ...historyKeymap]),
            indentOnInput(),
            bracketMatching(),
            syntaxHighlighting(defaultHighlightStyle),
            lang(meta.kind, meta.filename),
            oneDark,
            EditorView.updateListener.of((u) => {
              if (u.docChanged) {
                dirty = true;
                saved = false;
              }
            }),
            EditorView.domEventHandlers({
              paste: (event) => { handlePaste(event); return false; },
              drop:  (event) => { handleDrop(event); return false; },
              dragover: (event) => { event.preventDefault(); return false; },
            }),
          ],
        }),
      });
    } catch (e) {
      error = String(e);
    }
  });

  function pickImage(items: ArrayLike<DataTransferItem | File>): File | null {
    for (let i = 0; i < items.length; i++) {
      const it = (items as any)[i];
      const f = it instanceof File ? it : (typeof it.getAsFile === "function" ? it.getAsFile() : null);
      if (f && /^image\//.test(f.type)) return f;
    }
    return null;
  }

  async function handlePaste(ev: ClipboardEvent) {
    const items = ev.clipboardData?.items;
    if (!items) return;
    const f = pickImage(items);
    if (!f) return;
    ev.preventDefault();
    await uploadAndInsert(f);
  }

  async function handleDrop(ev: DragEvent) {
    const files = ev.dataTransfer?.files;
    if (!files || files.length === 0) return;
    const f = pickImage(files);
    if (!f) return;
    ev.preventDefault();
    await uploadAndInsert(f);
  }

  async function uploadAndInsert(file: File) {
    if (!view) return;
    uploadingImage = true;
    try {
      const titleHint = file.name || `pasted-${Date.now()}.png`;
      const obj = await api.uploadObject(
        slug,
        { kind: "image", title: titleHint, drawer: "images" },
        file,
      );
      const url = `/api/workbenches/${slug}/objects/${obj.id}/content`;
      const isMd = kind === "md" || (kind ? false : titleHint.endsWith(".md"));
      const snippet = isMd
        ? `![${titleHint}](${url})`
        : `<img src="${url}" alt="${titleHint}">`;
      const pos = view.state.selection.main.head;
      view.dispatch({
        changes: { from: pos, insert: snippet },
        selection: { anchor: pos + snippet.length },
      });
    } catch (e) {
      alert("Image upload failed: " + e);
    } finally {
      uploadingImage = false;
    }
  }

  onDestroy(() => view?.destroy());

  async function save() {
    if (!view) return;
    saving = true;
    error = null;
    try {
      const text = view.state.doc.toString();
      const r = await api.putObjectContent(slug, oid, text, etag);
      etag = r.etag;
      saved = true;
      dirty = false;
    } catch (e) {
      const err = String(e);
      if (err.includes("412")) {
        error = "Stale: another writer modified this file. Reload to see latest, then re-edit.";
      } else {
        error = err;
      }
    } finally {
      saving = false;
    }
  }

  async function reload() {
    if (!view) return;
    const { text, etag: e } = await api.getObjectContentText(slug, oid);
    etag = e;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: text },
    });
    dirty = false;
    error = null;
  }
</script>

<div class="wrap">
  <div class="bar">
    <button class="back" on:click={() => navigate(`/wb/${slug}`)}>← Back</button>
    <span class="title">{title || oid}</span>
    <span class="kind">{kind}</span>
    <span class="spacer"></span>
    {#if uploadingImage}<span class="status dirty">uploading image…</span>{/if}
    {#if dirty}<span class="status dirty">unsaved</span>{/if}
    {#if saved}<span class="status ok">saved</span>{/if}
    <button on:click={reload}>Reload</button>
    <button class="primary" on:click={save} disabled={saving || !dirty}>
      {saving ? "Saving…" : "Save"}
    </button>
  </div>
  {#if error}<div class="error">{error}</div>{/if}
  <div class="editor" bind:this={host}></div>
</div>

<style>
  .wrap { display: flex; flex-direction: column; height: calc(100vh - 53px); }
  .bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: var(--ab-surface); border-bottom: 2px solid #000; flex-wrap: wrap; font-family: var(--ab-font-body); }
  .title { font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; font-size: 13px; }
  .kind { font-family: var(--ab-font-mono); font-size: 10px; padding: 2px 8px; background: var(--ab-bg); border: 1px solid var(--ab-rule); border-radius: 2px; color: var(--ab-muted); text-transform: uppercase; letter-spacing: 0.06em; }
  .spacer { flex: 1; }
  .status { font-size: 10px; padding: 3px 8px; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
  .dirty { background: #422c00; color: var(--ab-tertiary); }
  .ok { background: #133a23; color: #6dd58c; }
  button { background: var(--ab-bg); border: 1.5px solid var(--ab-rule); color: var(--ab-ink); padding: 7px 12px; border-radius: var(--ab-radius); cursor: pointer; font: inherit; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
  button.primary { background: var(--ab-primary-bright); border-color: #000; color: var(--ab-on-primary); box-shadow: 2px 2px 0 #000; }
  button.primary:hover { transform: translate(-1px, -1px); box-shadow: 3px 3px 0 #000; }
  button.back { background: transparent; border: none; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { background: var(--ab-bg); color: var(--ab-error); padding: 8px 16px; border-bottom: 2px solid var(--ab-error); font-family: var(--ab-font-mono); font-size: 12px; }
  .editor { flex: 1; min-height: 0; overflow: auto; }
  :global(.cm-editor) { height: 100%; }
</style>
