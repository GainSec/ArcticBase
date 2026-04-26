// Parent-side window.workbench bridge handler. Listens for postMessage events from served-HTML
// iframes and routes them to the API. Mounted once at the SPA root.

import { api } from "./api";

interface IncomingMessage {
  __ab: string; // request id
  type: "save" | "saveAll" | "load" | "loadAll" | "submit";
  payload: unknown;
  ctx: { workbench: string; object: string };
}

interface RemoteSubscribe {
  __ab_remote_subscribe?: boolean;
  __ab_remote_unsubscribe?: boolean;
  ctx: { workbench: string; object: string };
}

function isIncoming(d: unknown): d is IncomingMessage {
  return !!d && typeof d === "object" && "__ab" in (d as Record<string, unknown>);
}

function isRemoteSub(d: unknown): d is RemoteSubscribe {
  if (!d || typeof d !== "object") return false;
  const o = d as Record<string, unknown>;
  return o.__ab_remote_subscribe === true || o.__ab_remote_unsubscribe === true;
}

// Tracks active remote-change subscriptions so we poll once per (slug, oid) regardless of how
// many iframes ask. Each entry: { source, slug, oid, lastVersion, timer }.
type Sub = { source: Window; slug: string; oid: string; lastVersion: number; timer: ReturnType<typeof setInterval> };
const subs: Sub[] = [];

async function poll(s: Sub) {
  try {
    const events = await api.listResponses(s.slug, s.oid, s.lastVersion);
    for (const ev of events) {
      s.lastVersion = Math.max(s.lastVersion, ev.version);
      try { s.source.postMessage({ __ab_remote: true, event: ev }, "*"); }
      catch { /* iframe gone */ }
    }
  } catch { /* network blip — retry on next tick */ }
}

export function installBridge(): () => void {
  const handler = async (ev: MessageEvent) => {
    if (isRemoteSub(ev.data)) {
      const { workbench, object } = ev.data.ctx;
      if (ev.data.__ab_remote_subscribe) {
        const src = ev.source;
        if (!src || !("postMessage" in src)) return;
        const existing = subs.find(s => s.source === src && s.slug === workbench && s.oid === object);
        if (existing) return;
        const sub: Sub = {
          source: src as Window,
          slug: workbench,
          oid: object,
          lastVersion: 0,
          timer: setInterval(() => poll(sub), 3000),
        };
        // Initialize lastVersion to the current latest so we don't replay history.
        api.latestResponse(workbench, object).then((latest) => {
          if (latest) sub.lastVersion = latest.version;
        }).catch(() => {});
        subs.push(sub);
      } else if (ev.data.__ab_remote_unsubscribe) {
        const idx = subs.findIndex(s => s.source === ev.source && s.slug === workbench && s.oid === object);
        if (idx >= 0) {
          clearInterval(subs[idx].timer);
          subs.splice(idx, 1);
        }
      }
      return;
    }
    if (!isIncoming(ev.data)) return;
    const msg = ev.data;
    const { workbench, object } = msg.ctx;
    let result: unknown = null;
    try {
      switch (msg.type) {
        case "save": {
          const p = msg.payload as { key: string; value: unknown };
          await api.appendResponse(workbench, object, {
            kind: "autosave",
            payload: { [p.key]: p.value },
          });
          result = { ok: true };
          break;
        }
        case "saveAll": {
          await api.appendResponse(workbench, object, {
            kind: "autosave",
            payload: msg.payload as Record<string, unknown>,
          });
          result = { ok: true };
          break;
        }
        case "load": {
          const latest = await api.latestResponse(workbench, object);
          const p = msg.payload as { key: string };
          result = latest ? (latest.payload as Record<string, unknown>)[p.key] : null;
          break;
        }
        case "loadAll": {
          const latest = await api.latestResponse(workbench, object);
          result = latest ? latest.payload : {};
          break;
        }
        case "submit": {
          const ev2 = await api.appendResponse(workbench, object, {
            kind: "submit",
            payload: msg.payload as Record<string, unknown>,
          });
          result = { version: ev2.version };
          break;
        }
      }
    } catch (err) {
      result = { error: String(err) };
    }
    if (ev.source && "postMessage" in ev.source) {
      (ev.source as Window).postMessage({ __ab: msg.__ab, result }, "*");
    }
  };
  window.addEventListener("message", handler);
  return () => {
    window.removeEventListener("message", handler);
    while (subs.length) {
      const s = subs.pop()!;
      clearInterval(s.timer);
    }
  };
}
