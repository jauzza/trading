import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } }, { waitUntil() {}, passThroughOnException() {} });
}

test("server renders OPEN / TEN and the corrected-cache loading shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /OPEN \/ TEN/);
  assert.match(html, /Loading corrected cached research/);
  assert.match(html, /2026 remains untouched/);
  assert.match(html, /NO LIVE TRADING/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});

test("secrets and live-trading claims never enter rendered HTML", async () => {
  const html = await (await render()).text();
  assert.doesNotMatch(html, /DATABENTO_API_KEY|FRED_API_KEY|db-[A-Za-z0-9]+/);
  assert.match(html, /NO EDGE CLAIM IS PERMITTED/);
  assert.doesNotMatch(html, /SYNTHETIC DEMO DATA/);
  assert.doesNotMatch(html, /LIVE CONNECTED|broker connected/i);
});

test("Phase 7 Pattern Laboratory replaces the invalid Phase 5 headline", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(source, /PHASE 7 · PATTERN LABORATORY/);
  assert.match(source, /INVALID LOOKAHEAD HISTORICAL RESULT/);
  assert.match(source, /AFTER BEST 1%/);
  assert.match(source, /Every finding is labeled by when it was actually knowable/);
  assert.doesNotMatch(source, /Justified for C01, still sealed/);
});
