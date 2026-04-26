// Minimal hash-free pathname router.

import { writable, type Readable } from "svelte/store";

export interface Route {
  path: string;
  params: Record<string, string>;
  query: URLSearchParams;
}

function parse(): Route {
  const url = new URL(window.location.href);
  return { path: url.pathname, params: {}, query: url.searchParams };
}

const _route = writable<Route>(parse());

export const route: Readable<Route> = { subscribe: _route.subscribe };

window.addEventListener("popstate", () => _route.set(parse()));

export function navigate(path: string): void {
  if (path === window.location.pathname + window.location.search) return;
  history.pushState({}, "", path);
  _route.set(parse());
}

export function match(pattern: string, pathname: string): Record<string, string> | null {
  const a = pattern.split("/").filter(Boolean);
  const b = pathname.split("/").filter(Boolean);
  if (a.length !== b.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith(":")) params[a[i].slice(1)] = decodeURIComponent(b[i]);
    else if (a[i] !== b[i]) return null;
  }
  return params;
}
