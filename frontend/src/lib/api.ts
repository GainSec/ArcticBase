// Arctic Base API client. Single-origin; relative URLs.

export type Banner =
  | { kind: "upload"; ref: string }
  | { kind: "url"; ref: string };

export interface WorkbenchMeta {
  version: number;
  slug: string;
  title: string;
  description: string;
  url: string | null;
  ip: string | null;
  local_path: string | null;
  tags: string[];
  banner: Banner | null;
  custom_fields: Record<string, string>;
  created_at: string;
  updated_at: string;
  last_accessed_at: string | null;
}

export type ObjectKind = "md" | "html" | "approval-html" | "image" | "qa-form" | "file" | "runbook";

export interface ObjectMeta {
  version: number;
  id: string;
  kind: ObjectKind;
  title: string;
  description: string;
  drawer: string;
  filename: string;
  mime: string;
  size_bytes: number;
  etag: string;
  created_at: string;
  updated_at: string;
  state_version: number;
  order: number;
  last_accessed_at: string | null;
  pinned: boolean;
  archived: boolean;
}

export interface TypographyStyle {
  fontFamily?: string;
  fontSize?: string;
  fontWeight?: string;
  lineHeight?: string;
  letterSpacing?: string;
}

export interface ThemeTokens {
  name?: string;
  core: Record<string, string>;
  typography: Record<string, TypographyStyle>;
  rounded: Record<string, string>;
  spacing: Record<string, string>;
  custom: Record<string, string>;
}

export interface Theme {
  tokens: ThemeTokens;
  prose: string;
  assets: string[];
}

export type ResponseKind = "submit" | "autosave" | "agent-edit";
export type Submitter = "user" | "agent" | "system";

export interface ResponseEvent {
  version: number;
  object_id: string;
  submitted_at: string;
  submitted_by: Submitter;
  kind: ResponseKind;
  payload: Record<string, unknown>;
}

class HttpError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
  }
}

async function req<T>(method: string, url: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(url, { method, ...init });
  if (!r.ok) {
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      body = await r.text();
    }
    throw new HttpError(r.status, body, `${method} ${url} failed: ${r.status}`);
  }
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("json")) return (await r.json()) as T;
  return (await r.text()) as unknown as T;
}

export const api = {
  // workbenches
  listWorkbenches: () => req<WorkbenchMeta[]>("GET", "/api/workbenches"),
  getWorkbench: (slug: string) => req<WorkbenchMeta>("GET", `/api/workbenches/${slug}`),
  createWorkbench: (body: { title: string; slug?: string; description?: string; tags?: string[]; url?: string; ip?: string; local_path?: string; }) =>
    req<WorkbenchMeta>("POST", "/api/workbenches", {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchWorkbench: (slug: string, patch: Partial<WorkbenchMeta>) =>
    req<WorkbenchMeta>("PATCH", `/api/workbenches/${slug}`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  archiveWorkbench: (slug: string) =>
    req<{ archive: string }>("DELETE", `/api/workbenches/${slug}`),
  listTrash: () =>
    req<{ archive: string }[]>("GET", "/api/workbenches/_trash/list"),
  restoreWorkbench: (archive: string) =>
    req<{ slug: string }>("POST", "/api/workbenches/_trash/restore", {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ archive }),
    }),
  duplicateWorkbench: (slug: string, newSlug?: string) =>
    req<WorkbenchMeta>("POST", `/api/workbenches/${slug}/duplicate`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ new_slug: newSlug }),
    }),
  // Returns blob URLs for client-side download buttons.
  exportWorkbenchUrl: (slug: string) => `/api/workbenches/${slug}/export`,
  bannerUrl: (slug: string) => `/api/workbenches/${slug}/banner`,
  trashDownloadUrl: (archive: string) => `/api/workbenches/_trash/${encodeURIComponent(archive)}/download`,
  purgeTrash: (archive: string) =>
    req<void>("DELETE", `/api/workbenches/_trash/${encodeURIComponent(archive)}`),

  // Response export helpers
  latestPayload: (slug: string, oid: string) =>
    req<Record<string, unknown>>("GET", `/api/workbenches/${slug}/objects/${oid}/responses/latest/payload`),
  responsesExportUrl: (slug: string, oid: string) =>
    `/api/workbenches/${slug}/objects/${oid}/responses/export`,

  // Snapshots
  listSnapshots: (slug: string) =>
    req<{ name: string; label: string; size_bytes: number; created_at: string }[]>(
      "GET",
      `/api/workbenches/${slug}/snapshots`,
    ),
  createSnapshot: (slug: string, label: string) =>
    req<{ name: string; label: string; size_bytes: number; created_at: string }>(
      "POST",
      `/api/workbenches/${slug}/snapshot`,
      {
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ label }),
      },
    ),
  snapshotDownloadUrl: (slug: string, name: string) =>
    `/api/workbenches/${slug}/snapshots/${encodeURIComponent(name)}/download`,
  restoreSnapshot: (slug: string, name: string, newSlug: string) =>
    req<WorkbenchMeta>(
      "POST",
      `/api/workbenches/${slug}/snapshots/${encodeURIComponent(name)}/restore`,
      {
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ new_slug: newSlug }),
      },
    ),
  deleteSnapshot: (slug: string, name: string) =>
    req<void>(
      "DELETE",
      `/api/workbenches/${slug}/snapshots/${encodeURIComponent(name)}`,
    ),

  // Audit log + static export
  auditLogUrl: (slug: string, download = true) =>
    `/api/workbenches/${slug}/audit${download ? "?download=true" : ""}`,
  staticExportUrl: (slug: string) => `/api/workbenches/${slug}/static-export`,

  // Self-test
  agentSelfTest: () =>
    req<{
      pass: boolean;
      steps: { name: string; ok: boolean; elapsed_ms: number; detail: string }[];
      total_ms: number;
    }>("POST", "/api/agent/self-test"),

  reorderWorkbenches: (slugs: string[]) =>
    req<void>("POST", "/api/workbenches/_reorder", {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ slugs }),
    }),
  reorderObjects: (slug: string, ids: string[]) =>
    req<void>("POST", `/api/workbenches/${slug}/objects/_reorder`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ids }),
    }),

  uploadThemeAsset: async (slug: string, path: string, file: File): Promise<void> => {
    const fd = new FormData();
    fd.set("upload", file);
    const r = await fetch(`/api/workbenches/${slug}/theme/assets/${encodeURIComponent(path)}`, {
      method: "PUT",
      body: fd,
    });
    if (!r.ok) throw new Error(`upload failed: ${r.status}`);
  },

  agentActivity: (limit = 100, agentOnly = true) =>
    req<{ events: { ts: number; method: string; path: string; status: number; elapsed_ms: number; request_id: string; is_agent: boolean }[] }>(
      "GET",
      `/api/agent/activity?limit=${limit}&agent_only=${agentOnly}`,
    ),

  // theme
  getTheme: (slug: string) => req<Theme>("GET", `/api/workbenches/${slug}/theme`),
  getThemeRaw: (slug: string) => req<string>("GET", `/api/workbenches/${slug}/theme/raw`),
  putTheme: (slug: string, raw: string) =>
    req<Theme>("PUT", `/api/workbenches/${slug}/theme`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ raw }),
    }),

  // objects
  listObjects: (slug: string, opts?: { includeArchived?: boolean }) =>
    req<ObjectMeta[]>(
      "GET",
      `/api/workbenches/${slug}/objects${opts?.includeArchived ? "?include_archived=true" : ""}`,
    ),
  getObject: (slug: string, oid: string) =>
    req<ObjectMeta>("GET", `/api/workbenches/${slug}/objects/${oid}`),
  createObject: (slug: string, body: { kind: ObjectKind; title: string; description?: string; drawer?: string; filename?: string; mime?: string; }) =>
    req<ObjectMeta>("POST", `/api/workbenches/${slug}/objects`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  uploadObject: async (
    slug: string,
    meta: { kind: ObjectKind; title: string; description?: string; drawer?: string; },
    file: File,
  ): Promise<ObjectMeta> => {
    const fd = new FormData();
    fd.set("meta", new Blob([JSON.stringify(meta)], { type: "application/json" }));
    fd.set("file", file);
    return req<ObjectMeta>("POST", `/api/workbenches/${slug}/objects`, { body: fd });
  },
  patchObject: (slug: string, oid: string, patch: Partial<ObjectMeta>) =>
    req<ObjectMeta>("PATCH", `/api/workbenches/${slug}/objects/${oid}`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteObject: (slug: string, oid: string) =>
    req<void>("DELETE", `/api/workbenches/${slug}/objects/${oid}`),

  getObjectContentText: async (slug: string, oid: string): Promise<{ text: string; etag: string }> => {
    const r = await fetch(`/api/workbenches/${slug}/objects/${oid}/content`);
    if (!r.ok) throw new HttpError(r.status, null, `content fetch failed: ${r.status}`);
    return { text: await r.text(), etag: r.headers.get("etag") || "" };
  },
  getObjectContentBlob: async (slug: string, oid: string): Promise<{ blob: Blob; etag: string }> => {
    const r = await fetch(`/api/workbenches/${slug}/objects/${oid}/content`);
    if (!r.ok) throw new HttpError(r.status, null, `content fetch failed: ${r.status}`);
    return { blob: await r.blob(), etag: r.headers.get("etag") || "" };
  },
  putObjectContent: (slug: string, oid: string, body: BodyInit, ifMatch?: string) =>
    req<{ meta: ObjectMeta; etag: string }>("PUT", `/api/workbenches/${slug}/objects/${oid}/content`, {
      headers: ifMatch ? { "if-match": ifMatch } : {},
      body,
    }),

  // responses
  listResponses: (slug: string, oid: string, sinceVersion = 0) =>
    req<ResponseEvent[]>("GET", `/api/workbenches/${slug}/objects/${oid}/responses?since_version=${sinceVersion}`),
  latestResponse: (slug: string, oid: string) =>
    req<ResponseEvent | null>("GET", `/api/workbenches/${slug}/objects/${oid}/responses/latest`),
  appendResponse: (slug: string, oid: string, body: { kind: ResponseKind; payload: unknown; submitted_by?: Submitter }) =>
    req<ResponseEvent>("POST", `/api/workbenches/${slug}/objects/${oid}/responses`, {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
};
