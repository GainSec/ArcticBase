import { expect, test, type Page, type Route } from "@playwright/test";

const timestamp = "2026-11-18T12:00:00Z";
function workbench(slug: string) {
  return { version: 1, slug, title: `Workbench ${slug}`, description: "", tags: ["test"],
    banner: null, custom_fields: {}, created_at: timestamp, updated_at: timestamp,
    last_accessed_at: timestamp, url: null, ip: null, local_path: null };
}
function object(id = "doc", kind = "html") {
  return { version: 1, id, kind, title: `Document ${id}`, description: "", drawer: "",
    filename: `${id}.html`, mime: "text/html", size_bytes: 1024, etag: "test-etag",
    created_at: timestamp, updated_at: timestamp, last_accessed_at: timestamp,
    state_version: 0, order: 0, pinned: false, archived: false };
}
const theme = { tokens: { core: { bg: "#111", surface: "#222", ink: "#eee" },
  typography: {}, rounded: {}, spacing: {}, custom: {} }, prose: "", assets: [] };
const json = (route: Route, value: unknown, status = 200) => route.fulfill({ status, json: value });
function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return { promise, release };
}

async function navigate(page: Page, path: string) {
  await page.evaluate((path) => {
    history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

async function fixtures(page: Page, slugs = ["alpha"], hook?: (route: Route, path: string) => Promise<boolean>) {
  const requests: string[] = [];
  const unexpected: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    if (hook && await hook(route, path)) return;
    if (path === "/api/workbenches") return json(route, slugs.map(workbench));
    const m = path.match(/^\/api\/workbenches\/([^/]+)(.*)$/);
    if (m) {
      const [, slug, suffix] = m;
      if (suffix === "") return json(route, workbench(slug));
      if (suffix === "/theme") return json(route, theme);
      if (suffix === "/banner") return route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg"/>' });
      if (suffix === "/objects") return json(route, [object()]);
      const obj = suffix.match(/^\/objects\/([^/]+)(.*)$/);
      if (obj) {
        const [, id, tail] = obj;
        if (!tail) return json(route, object(id));
        if (tail === "/render") return route.fulfill({ contentType: "text/html", body: `<h1>Rendered ${id}</h1>` });
        if (tail === "/content") return route.fulfill({ contentType: "application/json", body: '{"steps":[]}' });
      }
    }
    unexpected.push(`${route.request().method()} ${path}`);
    return json(route, { detail: "Unmocked API request" }, 500);
  });
  return { requests, unexpected };
}

test("cards are usable while statistics are pending and enrichment uses at most four requests", async ({ page }) => {
  const held = gate();
  const slugs = Array.from({ length: 12 }, (_, i) => `bench-${i}`);
  let active = 0, peak = 0;
  const { unexpected } = await fixtures(page, slugs, async (route, path) => {
    if (!path.endsWith("/objects")) return false;
    active++; peak = Math.max(peak, active);
    await held.promise;
    active--;
    await json(route, [object()]);
    return true;
  });
  await page.goto("/");
  try {
    await expect(page.locator(".card-title")).toHaveCount(12, { timeout: 2000 });
    await expect(page.locator(".card").first()).toContainText("Loading");
    expect(peak).toBeLessThanOrEqual(4);
  } finally { held.release(); }
  await expect(page.locator(".meter-pct").first()).toHaveText("10%");
  await expect(page.locator(".console-body")).toContainText(/total objects\.+\s+12/);
  expect(peak).toBeLessThanOrEqual(4);
  expect(unexpected).toEqual([]);
});

test("failed statistics stay unavailable while successful and empty workbenches remain usable", async ({ page }) => {
  await fixtures(page, ["alpha", "broken", "empty"], async (route, path) => {
    if (path === "/api/workbenches/broken/objects") { await json(route, {}, 500); return true; }
    if (path === "/api/workbenches/empty/objects") { await json(route, []); return true; }
    return false;
  });
  await page.goto("/");
  const broken = page.locator(".card").filter({ hasText: "Workbench broken" });
  await expect(broken).toContainText("Unavailable");
  await expect(broken.getByRole("button")).toBeEnabled();
  await expect(page.locator(".card").filter({ hasText: "Workbench empty" })).toContainText("VIEW SCHEMATICS");
  await expect(page.locator(".console-body")).toContainText(/partial/i);
});

test("leaving the dashboard aborts statistics and stops queued work", async ({ page }) => {
  const held = gate();
  const slugs = Array.from({ length: 12 }, (_, i) => `bench-${i}`);
  let foreground = false, backgroundRequests = 0, aborted = 0;
  page.on("requestfailed", (request) => {
    if (new URL(request.url()).pathname.endsWith("/objects")) aborted++;
  });
  await fixtures(page, slugs, async (route, path) => {
    if (path === "/api/workbenches/bench-0") foreground = true;
    if (!path.endsWith("/objects") || foreground) return false;
    backgroundRequests++;
    await held.promise;
    await json(route, []).catch(() => {});
    return true;
  });
  await page.goto("/");
  try {
    await expect(page.locator(".card-title")).toHaveCount(12, { timeout: 2000 });
    await expect.poll(() => backgroundRequests).toBe(4);
    await page.locator(".cta-card").first().click();
    await expect(page.getByRole("heading", { name: "Workbench bench-0", exact: true })).toBeVisible();
    await expect.poll(() => aborted).toBe(4);
    held.release();
    await page.evaluate(() => new Promise(requestAnimationFrame));
    expect(backgroundRequests).toBe(4);
  } finally { held.release(); }
});

test("a workbench loads each resource once and refreshes objects only when archive visibility changes", async ({ page }) => {
  const { requests, unexpected } = await fixtures(page);
  await page.goto("/wb/alpha");
  await expect(page.getByRole("heading", { name: "Workbench alpha", exact: true })).toBeVisible();
  await expect(page.getByText("Document doc", { exact: true })).toBeVisible();
  // Drain already queued Svelte updates before counting the initial load.
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  for (const path of ["/api/workbenches/alpha", "/api/workbenches/alpha/theme", "/api/workbenches/alpha/objects"]) {
    expect(requests.filter((p) => p === path), path).toHaveLength(1);
  }
  await page.getByRole("checkbox", { name: "Show archived" }).check();
  await expect.poll(() => requests.filter((p) => p.endsWith("/objects")).length).toBe(2);
  expect(unexpected).toEqual([]);
});

for (const kind of ["html", "md", "image", "runbook"]) {
  test(`${kind} viewer reuses the metadata already loaded by the route`, async ({ page }) => {
    const { requests } = await fixtures(page, ["alpha"], async (route, path) => {
      if (path === "/api/workbenches/alpha/objects/doc") { await json(route, object("doc", kind)); return true; }
      return false;
    });
    await page.goto("/wb/alpha/o/doc");
    if (kind === "html" || kind === "md") {
      await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered doc");
    } else if (kind === "image") {
      await expect(page.locator(".canvas img")).toBeVisible();
    } else {
      await expect(page.getByText("No steps yet.", { exact: false })).toBeVisible();
    }
    expect(requests.filter((p) => p === "/api/workbenches/alpha/objects/doc")).toHaveLength(1);
    if (kind === "runbook") {
      expect(requests.filter((p) => p === "/api/workbenches/alpha")).toHaveLength(1);
      expect(requests.filter((p) => p === "/api/workbenches/alpha/theme")).toHaveLength(1);
    }
  });
}

test("all failed statistics settle as unavailable instead of loading forever", async ({ page }) => {
  const held = gate();
  await fixtures(page, ["alpha"], async (route, path) => {
    if (!path.endsWith("/objects")) return false;
    await held.promise;
    await json(route, {}, 500);
    return true;
  });
  await page.goto("/");
  await expect(page.locator(".card")).toContainText("Loading");
  held.release();
  await expect(page.locator(".card")).toContainText("Unavailable");
  await expect(page.locator(".console-body")).toContainText(/total objects\.+\s+unavailable/);
});

test("workbench resources start concurrently even when metadata is slow", async ({ page }) => {
  const held = gate();
  const { requests } = await fixtures(page, ["alpha"], async (route, path) => {
    if (path !== "/api/workbenches/alpha") return false;
    await held.promise;
    await json(route, workbench("alpha"));
    return true;
  });
  await page.goto("/wb/alpha");
  try {
    await expect.poll(() => requests.includes("/api/workbenches/alpha/objects")).toBe(true);
    expect(requests).toContain("/api/workbenches/alpha/theme");
  } finally { held.release(); }
  await expect(page.getByRole("heading", { name: "Workbench alpha", exact: true })).toBeVisible();
});

test("switching documents of the same kind replaces the viewer and ignores late metadata", async ({ page }) => {
  const held = gate();
  let slowStarted = false;
  await fixtures(page, ["alpha"], async (route, path) => {
    if (path !== "/api/workbenches/alpha/objects/slow") return false;
    slowStarted = true;
    await held.promise;
    await json(route, object("slow"));
    return true;
  });
  await page.goto("/wb/alpha/o/one");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered one");
  await navigate(page, "/wb/alpha/o/two");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered two");
  await navigate(page, "/wb/alpha/o/slow");
  await expect.poll(() => slowStarted).toBe(true);
  await navigate(page, "/wb/alpha/o/three");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered three");
  held.release();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator(".bar .title")).toHaveText("Document three");
});

test("switching workbenches fetches fresh metadata and ignores late results", async ({ page }) => {
  const held = gate();
  let slowStarted = false;
  const { requests } = await fixtures(page, ["alpha", "beta"], async (route, path) => {
    if (path !== "/api/workbenches/slow") return false;
    slowStarted = true;
    await held.promise;
    await json(route, workbench("slow"));
    return true;
  });
  await page.goto("/wb/alpha");
  await expect(page.getByRole("heading", { name: "Workbench alpha", exact: true })).toBeVisible();
  await navigate(page, "/wb/beta");
  await expect(page.getByRole("heading", { name: "Workbench beta", exact: true })).toBeVisible();
  await navigate(page, "/wb/alpha");
  await expect(page.getByRole("heading", { name: "Workbench alpha", exact: true })).toBeVisible();
  expect(requests.filter((p) => p === "/api/workbenches/alpha")).toHaveLength(2);
  await navigate(page, "/wb/slow");
  await expect.poll(() => slowStarted).toBe(true);
  await navigate(page, "/wb/beta");
  await expect(page.getByRole("heading", { name: "Workbench beta", exact: true })).toBeVisible();
  held.release();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.locator(".wb-title")).toHaveText("SECTOR_WORKBENCH_BETA");
});

test("creating a workbench does not wait for dashboard statistics", async ({ page }) => {
  const held = gate();
  let created = false;
  await fixtures(page, ["alpha"], async (route, path) => {
    if (path === "/api/workbenches") {
      if (route.request().method() === "POST") {
        created = true;
        await json(route, workbench("new"), 201);
      } else await json(route, (created ? ["alpha", "new"] : ["alpha"]).map(workbench));
      return true;
    }
    if (path === "/api/workbenches/alpha/objects") {
      await held.promise;
      await json(route, []).catch(() => {});
      return true;
    }
    return false;
  });
  await page.goto("/");
  try {
    await expect(page.locator(".card-title")).toHaveCount(1);
    await page.getByRole("button", { name: "INITIALIZE NEW WORKBENCH" }).click();
    await page.locator("#newTitle").fill("New workbench");
    await page.getByRole("button", { name: "DEPLOY", exact: true }).click();
    await expect(page).toHaveURL(/\/wb\/new$/);
    await expect(page.getByRole("heading", { name: "Workbench new", exact: true })).toBeVisible();
  } finally { held.release(); }
});

test("pinning, reordering, archiving, restoring and deletion preserve API behavior", async ({ page }) => {
  let objects = [object("one"), object("two")];
  const mutations: string[] = [];
  const { unexpected } = await fixtures(page, ["alpha"], async (route, path) => {
    const request = route.request();
    if (path.endsWith("/objects") && request.method() === "GET") {
      const archived = new URL(request.url()).searchParams.get("include_archived") === "true";
      await json(route, objects.filter((o) => archived || !o.archived));
      return true;
    }
    if (path.endsWith("/objects/_reorder")) {
      mutations.push("reorder");
      const ids = request.postDataJSON().ids as string[];
      objects = ids.map((id, order) => ({ ...objects.find((o) => o.id === id)!, order }));
      await route.fulfill({ status: 204 });
      return true;
    }
    const match = path.match(/\/objects\/(one|two)$/);
    if (match && request.method() === "PATCH") {
      mutations.push("patch");
      const index = objects.findIndex((o) => o.id === match[1]);
      objects[index] = { ...objects[index], ...request.postDataJSON() };
      await json(route, objects[index]);
      return true;
    }
    if (match && request.method() === "DELETE") {
      mutations.push("delete");
      objects = objects.filter((o) => o.id !== match[1]);
      await route.fulfill({ status: 204 });
      return true;
    }
    return false;
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/wb/alpha");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const first = page.locator(".obj-wrap").filter({ hasText: "Document one" });
  await first.getByTitle("Pin", { exact: true }).click();
  await expect(first.getByTitle("Unpin", { exact: true })).toBeVisible();
  await first.getByTitle("Move down", { exact: true }).click();
  await expect.poll(() => mutations.includes("reorder")).toBe(true);
  await first.getByTitle("Archive", { exact: true }).click();
  await expect(first).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Show archived" }).check();
  await expect(first).toContainText("ARCHIVED");
  await first.getByTitle("Unarchive", { exact: true }).click();
  await expect(first).not.toContainText("ARCHIVED");
  await first.getByTitle("Delete object", { exact: true }).click();
  await expect(first).toHaveCount(0);
  expect(mutations).toEqual(["patch", "reorder", "patch", "patch", "delete"]);
  expect(unexpected).toEqual([]);
});

test("same-workbench runbook navigation uses the latest theme and workbench metadata", async ({ page }) => {
  let visits = 0;
  const { requests } = await fixtures(page, ["alpha"], async (route, path) => {
    if (path === "/api/workbenches/alpha") {
      visits++;
      await json(route, { ...workbench("alpha"), title: visits === 1 ? "Original" : "Updated" });
      return true;
    }
    if (path === "/api/workbenches/alpha/theme") {
      await json(route, { ...theme, tokens: { ...theme.tokens, core: { ...theme.tokens.core, bg: visits === 1 ? "#111111" : "#334455" } } });
      return true;
    }
    if (path === "/api/workbenches/alpha/objects/runbook") {
      await json(route, object("runbook", "runbook"));
      return true;
    }
    return false;
  });
  await page.goto("/wb/alpha/o/doc");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered doc");
  await expect(page.locator(".wb-title")).toHaveText("SECTOR_ORIGINAL");
  await navigate(page, "/wb/alpha/o/runbook");
  await expect(page.getByText("No steps yet.", { exact: false })).toBeVisible();
  await expect(page.locator(".wb-title")).toHaveText("SECTOR_UPDATED");
  await expect(page.locator(".themed-wrap")).toHaveCSS("background-color", "rgb(51, 68, 85)");
  expect(requests.filter((p) => p === "/api/workbenches/alpha/theme")).toHaveLength(2);
});

test("last-file ties preserve workbench order when statistics finish out of order", async ({ page }) => {
  const held = gate();
  await fixtures(page, ["alpha", "beta"], async (route, path) => {
    if (path === "/api/workbenches/alpha/objects") {
      await held.promise;
      await json(route, [object("alpha")]);
      return true;
    }
    if (path === "/api/workbenches/beta/objects") {
      await json(route, [object("beta")]);
      return true;
    }
    return false;
  });
  await page.goto("/");
  await expect(page.locator(".console-body")).toContainText("beta/Document beta");
  held.release();
  await expect(page.locator(".console-body")).toContainText(/total objects\.+\s+2/);
  await expect(page.locator(".console-body")).toContainText("alpha/Document alpha");
});

test("equivalent object URLs keep the current viewer visible", async ({ page }) => {
  const { requests } = await fixtures(page);
  await page.goto("/wb/alpha/o/doc");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered doc");
  await navigate(page, "/wb/alpha/o/doc/");
  await expect(page.frameLocator("iframe").getByRole("heading")).toHaveText("Rendered doc");
  expect(requests.filter((p) => p === "/api/workbenches/alpha/objects/doc")).toHaveLength(1);
});
