import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const html = await readFile(new URL("../UST_AUCTION_ui-baseline-v5.html", import.meta.url), "utf8");
const v4 = await readFile(new URL("../UST_AUCTION_ui-baseline-v4.html", import.meta.url), "utf8");
const source = await readFile(new URL("../scripts/tentative_schedule_v1.js", import.meta.url), "utf8");
const snapshotText = html.match(/<script type="application\/json" id="ust-tentative-schedule-v1">([^<]*)<\/script>/)?.[1];

function merger() {
  const window = {};
  vm.runInNewContext(source, {
    document: { getElementById: () => ({ textContent: snapshotText }) },
    window,
  });
  return window;
}

async function runLoader(fetch) {
  const loader = html.match(/<script id="standalone-live-data-script">([\s\S]*?)<\/script>/)?.[1];
  const window = merger();
  let start;
  let resolveRender;
  const finished = new Promise((resolve) => { resolveRender = resolve; });
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : ["2026-10-22T04:00:00Z"])); }
  }
  window.location = { href: "file:///UST_AUCTION_ui-baseline-v5.html" };
  window.addEventListener = (_, callback) => { start = callback; };
  window.__UST_RENDER_AUCTIONS__ = (data) => resolveRender(data);
  vm.runInNewContext(loader, {
    AbortController, Date: FixedDate, URL, fetch, setTimeout, clearTimeout,
    requestAnimationFrame: (callback) => callback(),
    document: { readyState: "loading", documentElement: { lang: "ko" }, getElementById: () => ({}), querySelector: () => null },
    MutationObserver: class { observe() {} },
    localStorage: { getItem: () => null, setItem: () => {} },
    window,
  });
  start();
  return finished;
}

test("v5 embeds a sourced Treasury XML snapshot and preserves v4 as a separate version", () => {
  const snapshot = JSON.parse(snapshotText);
  assert.equal(snapshot.version, 1);
  assert.match(snapshot.sourceUrl, /^https:\/\/home\.treasury\.gov\/.*\.xml$/);
  assert.equal(snapshot.sourceSha256, "c1f4049f6e94f994591f84f184a21ef3d41a61dd7ba6ce3a01dddd4edf9d2908");
  assert.equal(snapshot.capturedAt, "2026-10-22");
  assert.ok(snapshot.rows.some((row) => row.auctionDate === "2026-11-19" && row.tips === "Y"));
  assert.ok(snapshot.rows.some((row) => row.auctionDate === "2026-11-30" && row.type === "BILL"));
  assert.ok(!v4.includes('id="ust-tentative-schedule-v1"'));
  assert.ok(html.includes('id="ust-tentative-schedule-v1"'));
});

test("official announcement or result replaces the matching tentative event", () => {
  const { __UST_MERGE_TENTATIVE__: merge } = merger();
  const today = "2026-10-22";
  const until = "2027-01-20";
  const original = merge([], [], today, until);
  const planned = original.find((row) => row.auctionDate === "2026-10-26" && row.type === "Note" && row.term === "2-Year");
  assert.ok(planned?.tentative);
  assert.equal(planned.offeringAmount, null);
  assert.equal(planned.closingTimeCompetitive, "");

  const official = {
    auction_date: "2026-10-26", security_type: "Note", security_term: "2-Year",
    original_security_term: "2-Year", cusip: "OFFICIAL", bid_to_cover_ratio: null,
  };
  const announced = { auctionDate: "2026-10-26", type: "Note", term: "2-Year", cusip: "OFFICIAL" };
  const merged = merge([official], [announced], today, until);
  assert.equal(merged.filter((row) => row.auctionDate === "2026-10-26" && row.type === "Note" && row.term === "2-Year").length, 1);
  assert.equal(merged.find((row) => row.cusip === "OFFICIAL")?.tentative, undefined);

  const result = { ...official, bid_to_cover_ratio: "2.5" };
  const afterResult = merge([result], [], today, until);
  assert.ok(!afterResult.some((row) => row.auctionDate === "2026-10-26" && row.type === "Note" && row.term === "2-Year"));
});

test("reopened bills match by auction term, not their different original term", async () => {
  const { __UST_MERGE_TENTATIVE__: merge } = merger();
  const official = ["4-Week", "8-Week"].map((term) => ({
    auction_date: "2026-10-29", security_type: "Bill", security_term: term,
    original_security_term: "17-Week", cusip: term, bid_to_cover_ratio: null,
  }));
  const announced = official.map((row) => ({
    auctionDate: row.auction_date, type: "Bill", term: row.security_term, cusip: row.cusip,
  }));
  const merged = merge(official, announced, "2026-10-22", "2027-01-20");
  assert.equal(merged.filter((row) => row.auctionDate === "2026-10-29" && row.type === "Bill").length, 2);
  assert.ok(merged.filter((row) => row.auctionDate === "2026-10-29" && row.type === "Bill").every((row) => !row.tentative));

  const rendered = await runLoader(async () => ({ ok: true, json: async () => ({
    data: [{ ...official[0], bid_to_cover_ratio: "2.83" }],
    meta: { "total-pages": 1, "total-count": 1 },
  }) }));
  assert.equal(rendered.results[0].term, "4-Week");
  assert.ok(!rendered.upcoming.some((row) => row.auctionDate === "2026-10-29" && row.term === "4-Week"));
});

test("only future tentative rows within 90 days appear, including bills", () => {
  const { __UST_MERGE_TENTATIVE__: merge } = merger();
  const rows = merge([], [], "2026-10-22", "2027-01-20");
  assert.ok(rows.length > 20);
  assert.ok(rows.every((row) => row.auctionDate >= "2026-10-22" && row.auctionDate <= "2027-01-20"));
  assert.ok(rows.some((row) => row.auctionDate === "2026-11-19" && row.type === "TIPS"));
  assert.ok(rows.some((row) => row.auctionDate === "2026-11-30" && row.type === "Bill"));
  assert.ok(rows.some((row) => row.tentativeUnconfirmed));
});

test("the v5 live loader supplies announced and remaining tentative rows together", async () => {
  const official = [
    { cusip: "RESULT", auction_date: "2026-10-21", security_type: "Note", security_term: "2-Year", bid_to_cover_ratio: "2.5" },
    { cusip: "ANNOUNCED", auction_date: "2026-10-26", security_type: "Note", security_term: "2-Year", bid_to_cover_ratio: null },
  ];
  const rendered = await runLoader(async () => ({ ok: true, json: async () => ({
    data: official, meta: { "total-pages": 1, "total-count": official.length },
  }) }));
  assert.equal(rendered.source, "live");
  assert.equal(rendered.results.length, 1);
  assert.ok(rendered.upcoming.some((row) => row.cusip === "ANNOUNCED"));
  assert.ok(rendered.upcoming.some((row) => row.tentative && row.auctionDate === "2026-11-19"));
  assert.equal(rendered.upcoming.filter((row) => row.auctionDate === "2026-10-26" && row.type === "Note" && row.term === "2-Year").length, 1);
});

test("a failed Fiscal API keeps only the dated tentative schedule", async () => {
  const rendered = await runLoader(async () => { throw new Error("offline"); });
  assert.equal(rendered.source, "unavailable");
  assert.equal(rendered.results.length, 0);
  assert.ok(rendered.upcoming.length > 20);
  assert.ok(rendered.upcoming.every((row) => row.tentative));
});

test("v5 script, labels, and offline schedule path are connected", () => {
  for (const [, id, script] of html.matchAll(/<script id="([^"]+)">([\s\S]*?)<\/script>/g)) {
    assert.doesNotThrow(() => new Function(script), id);
  }
  assert.match(html, /window\.__UST_MERGE_TENTATIVE__\(rows, officialUpcoming, todayText, upcomingTo\)/);
  assert.match(html, /upcoming: window\.__UST_MERGE_TENTATIVE__\(\[\], \[\], todayText, upcomingTo\)/);
  assert.match(html, /status: auction\.tentative \? "tentative" : "upcoming"/);
  assert.match(html, /const tentativeCount = datedEvents\.filter/);
  assert.match(html, /className:"tentative-badge"/);
  assert.match(html, /excludeBills: false/);
});

test("tentative calendar events use the same color as the legend in every theme", () => {
  const css = html.match(/<style id="ust-v5-tentative-styles">([\s\S]*?)<\/style>/)?.[1];
  assert.ok(css);
  assert.match(css, /\.auction-month-calendar\{--ust-tentative-color:#76529b\}/);
  assert.match(css, /:root \.auction-month-calendar \.auction-calendar-event\.is-tentative\{[^}]*background:var\(--ust-tentative-color\)/);
  assert.match(css, /\.auction-calendar-legend i\.tentative\{background:var\(--ust-tentative-color\)\}/);
});

test("selecting October 29 tentative 4W does not select October 22 4W", () => {
  const start = html.indexOf("    function findAndSelect(event, message) {");
  const end = html.indexOf("    function render() {", start);
  const selectSource = start >= 0 && end > start ? html.slice(start, end).trim() : "";
  assert.ok(selectSource);
  assert.match(html, /"data-auction-key":F\(i\)/);

  const { __UST_MERGE_TENTATIVE__: merge } = merger();
  const upcoming = merge([], [], "2026-10-22", "2027-01-20");
  const october22 = upcoming.find((row) => row.auctionDate === "2026-10-22" && row.term === "4-Week");
  const october29 = upcoming.find((row) => row.auctionDate === "2026-10-29" && row.term === "4-Week");
  assert.ok(october22 && october29);
  const clicks = [];
  const rows = [october22, october29].map((auction) => ({
    querySelector: () => ({
      getAttribute: (name) => name === "data-auction-key" ? `${auction.cusip}-${auction.auctionDate}` : null,
      click: () => clicks.push(auction.auctionDate),
    }),
  }));
  const state = { selectedKey: "" };
  const message = { textContent: "" };
  const context = {
    event: { auction: october29, status: "tentative", display: { full: "2026-10-29 · 원문 ET" } },
    message, state, window: {}, document: { querySelectorAll: () => rows },
    koreanTerm: () => "4주 단기채",
    auctionKey: (auction, status) => `${status}|${auction.cusip}|${auction.auctionDate}`,
    render: () => {},
  };
  vm.runInNewContext(`${selectSource}\nfindAndSelect(event, message);`, context);
  assert.deepEqual(clicks, ["2026-10-29"]);
  assert.match(message.textContent, /2026-10-29.*잠정/);
  assert.match(state.selectedKey, /2026-10-29/);

  context.event = { ...context.event, auction: { ...october29, cusip: "unmatched" } };
  vm.runInNewContext(`${selectSource}\nfindAndSelect(event, message);`, context);
  assert.deepEqual(clicks, ["2026-10-29"]);
  assert.match(message.textContent, /찾지 못했습니다/);
});
