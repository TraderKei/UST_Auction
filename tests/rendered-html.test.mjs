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

test("server-renders the Treasury auction terminal", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>FV Terminal — U\.S\. Treasury Auctions<\/title>/i);
  assert.match(html, /U\.S\. Treasury Auctions/);
  assert.match(html, /Forward calendar \+ prior result/);
  assert.match(html, /Upcoming offering size/);
  assert.match(html, /TreasuryDirect/);
  assert.doesNotMatch(html, /codex-preview|Building your site|react-loading-skeleton/i);
});

test("ships the API field map and executable database design", async () => {
  const [dashboard, ddl, design] = await Promise.all([
    readFile(new URL("../app/AuctionDashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../db/treasury_auction_schema.sql", import.meta.url), "utf8"),
    readFile(new URL("../docs/API_AND_DB_DESIGN.md", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /120 RAW FIELDS/);
  assert.match(dashboard, /highDiscountMargin/);
  assert.match(ddl, /CREATE VIEW v_auction_monitor/);
  assert.match(ddl, /CONSTRAINT uq_auction_business_key UNIQUE \(cusip, auction_date, issue_date\)/);
  assert.match(design, /competitive tendered \/ public offering amount/i);
  await assert.rejects(access(new URL("../app/_sites-preview/", import.meta.url)));
});
