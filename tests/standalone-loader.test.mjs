import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const loader = await readFile(new URL("../standalone-live-data.js", import.meta.url), "utf8");
const store = new Map();
const row = (cusip, date) => ({
  cusip, auction_date: date, security_type: "Note", security_term: "2-Year",
  bid_to_cover_ratio: "2.5", offering_amt: "1000000000",
});

async function run(fetch) {
  let start;
  let rendered;
  let resolveRender;
  const finished = new Promise((resolve) => { resolveRender = resolve; });
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : ["2026-10-07T04:00:00.000Z"])); }
  }
  const context = {
    AbortController, Date: FixedDate, URL, fetch, setTimeout, clearTimeout,
    requestAnimationFrame: (callback) => callback(),
    document: {
      readyState: "loading",
      getElementById: () => ({}),
      querySelector: () => null,
    },
    MutationObserver: class { observe() {} },
    localStorage: {
      getItem: (key) => store.get(key) ?? null,
      setItem: (key, value) => store.set(key, value),
    },
    window: {
      location: { href: "file:///auction.html" },
      addEventListener: (_, callback) => { start = callback; },
      __UST_RENDER_AUCTIONS__: (data) => { rendered = data; resolveRender(); },
    },
  };
  vm.runInNewContext(loader, context);
  start();
  await finished;
  return rendered;
}

test("standalone loader retries a transient page failure and caches complete official rows", async () => {
  store.clear();
  let firstPageAttempts = 0;
  const rendered = await run(async (url) => {
    const page = Number(url.searchParams.get("page[number]"));
    if (page === 1 && ++firstPageAttempts === 1) throw new Error("temporary network error");
    return {
      ok: true,
      json: async () => ({
        data: page === 1 ? [row("AAA", "2026-10-06")] : [row("BBB", "2026-10-05")],
        meta: { "total-pages": 2, "total-count": 2 },
      }),
    };
  });
  assert.equal(firstPageAttempts, 2);
  assert.equal(rendered.source, "live");
  assert.equal(rendered.results.length, 2);
  assert.equal(JSON.parse(store.get("ust-auction-official-rows-v1")).rows.length, 2);
});

test("standalone loader restores dated official cache when live retrieval fails", async () => {
  store.clear();
  store.set("ust-auction-official-rows-v1", JSON.stringify({
    from: "2022-09-07", to: "2027-01-05",
    retrievedAt: "2026-10-07T04:00:00.000Z",
    rows: [row("AAA", "2026-10-06"), row("BBB", "2026-10-05")],
  }));
  const rendered = await run(async () => { throw new Error("network unavailable"); });
  assert.equal(rendered.source, "snapshot");
  assert.equal(rendered.results.length, 2);
  assert.equal(rendered.updatedAt, "2026-10-07T04:00:00.000Z");
});
