import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the dark Treasury auction terminal without sample fallback (offline)", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new Error("Offline UI test"); });
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>UST AUCTION — 미국 국채 입찰<\/title>/i);
  assert.match(html, /UST AUCTION/);
  assert.match(html, /최근 입찰 결과/);
  assert.match(html, /예정 입찰 일정/);
  assert.match(html, /시장 동향/);
  assert.match(html, /data-theme="dark"/);
  assert.match(html, /공식 API 수신에 실패했습니다/);
  assert.match(html, /표본값으로 대체하지 않습니다/);
  assert.match(html, /결과 없음/);
  assert.doesNotMatch(html, /282\.0/);
  const visible = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "").replace(/<[^>]+>/g, " ");
  assert.doesNotMatch(visible, /CUSIP|Bid\s*\/\s*cover|Bid-to-cover|\bBTC\b|\d+(?:\.\d+)?\s*×/i);
  assert.match(html, /Fiscal Data/);
  assert.doesNotMatch(html, /codex-preview|Building your site|react-loading-skeleton/i);
});

test("preserves the existing API field map and SQL design files (not DB execution)", async () => {
  const [dashboard, ddl, design] = await Promise.all([
    readFile(new URL("../app/AuctionReference.tsx", import.meta.url), "utf8"),
    readFile(new URL("../db/treasury_auction_schema.sql", import.meta.url), "utf8"),
    readFile(new URL("../docs/API_AND_DB_DESIGN.md", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /API 필드/);
  assert.match(dashboard, /highDiscountMargin/);
  assert.match(ddl, /CREATE VIEW v_auction_monitor/);
  assert.match(ddl, /CONSTRAINT uq_auction_business_key UNIQUE \(cusip, auction_date, issue_date\)/);
  assert.match(design, /competitive tendered \/ public offering amount/i);
  await assert.rejects(access(new URL("../app/_sites-preview/", import.meta.url)));
});
