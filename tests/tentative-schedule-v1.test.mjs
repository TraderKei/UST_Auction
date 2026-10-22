import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const html = await readFile(new URL("../UST_AUCTION_ui-baseline-v5.html", import.meta.url), "utf8");
const v4 = await readFile(new URL("../UST_AUCTION_ui-baseline-v4.html", import.meta.url), "utf8");
const source = await readFile(new URL("../scripts/tentative_schedule_v1.js", import.meta.url), "utf8");
const snapshotText = html.match(/<script type="application\/json" id="ust-tentative-schedule-v1">([^<]*)<\/script>/)?.[1];

function merger(documentOverride) {
  const window = {};
  vm.runInNewContext(source, {
    document: documentOverride || { getElementById: () => ({ textContent: snapshotText }) },
    window, Date, setTimeout, clearTimeout,
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
  assert.match(html, /<title>UST AUCTION · UI Baseline v5<\/title>/);
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
  const bill = rendered.upcoming.find((row) => row.auctionDate === "2026-10-22" && row.type === "Bill" && row.term === "4-Week");
  assert.equal(bill?.offeringAmount, 110000000000);
  assert.equal(bill?.closingTimeCompetitive, "11:30 AM");
  assert.equal(bill?.tentative, undefined);
  assert.equal(rendered.upcoming.filter((row) => row.auctionDate === "2026-10-26" && row.type === "Note" && row.term === "2-Year").length, 1);
});

test("a failed Fiscal API retains verified TreasuryDirect announcements and tentative rows", async () => {
  const rendered = await runLoader(async () => { throw new Error("offline"); });
  assert.equal(rendered.source, "unavailable");
  assert.equal(rendered.results.length, 0);
  assert.ok(rendered.upcoming.length > 20);
  assert.ok(rendered.upcoming.some((row) => row.auctionDate === "2026-10-22" && row.term === "4-Week" && row.offeringAmount === 110000000000 && !row.tentative));
  assert.ok(rendered.upcoming.some((row) => row.tentative));
});

test("v5 script, labels, and offline schedule path are connected", () => {
  for (const [, id, script] of html.matchAll(/<script id="([^"]+)">([\s\S]*?)<\/script>/g)) {
    assert.doesNotThrow(() => new Function(script), id);
  }
  assert.match(html, /window\.__UST_MERGE_TENTATIVE__\(rows, officialUpcoming, todayText, upcomingTo\)/);
  assert.match(html, /upcoming: window\.__UST_MERGE_TENTATIVE__\(announced, announced\.map\(normalize\), todayText, upcomingTo\)/);
  assert.match(html, /window\.__UST_AUGMENT_OFFICIAL__\(fiscalRows, treasuryDirectRows, todayText, upcomingTo\)/);
  assert.match(html, /status: auction\.tentative \? "tentative" : "upcoming"/);
  assert.match(html, /const tentativeCount = datedEvents\.filter/);
  assert.match(html, /className:"tentative-badge"/);
  assert.match(html, /excludeBills: false/);
  assert.match(html, /<script id="ust-results-excel-v1">/);
  assert.ok(html.indexOf('<script id="ust-results-excel-v1">') < html.indexOf('<script id="ust-vue-dashboard-runtime">'));
  assert.match(html, /className:"date-range-form"[^\n]*?children:\[e\("button",\{type:"button",className:"results-export"/);
  assert.match(html, /onClick:\(\)=>window\.__UST_RESULTS_EXCEL_V1__\.download\(\)/);
  assert.doesNotMatch(html, /"\\uC790\\uB8CC \\uAE30\\uC900 \\uC2DC\\uAC01 \\uC774\\uD6C4 \\uC608\\uC815"/);
});

test("tentative calendar events use the same color as the legend in every theme", () => {
  const css = html.match(/<style id="ust-v5-tentative-styles">([\s\S]*?)<\/style>/)?.[1];
  assert.ok(css);
  assert.match(css, /:root\{--ust-tentative-color:#3b4650/);
  assert.match(css, /html\[data-ust-theme="light"\]\{--ust-tentative-color:#e3e8ed/);
  assert.match(css, /:root \.auction-month-calendar \.auction-calendar-event\.is-tentative\{[^}]*background:var\(--ust-tentative-color\)/);
  assert.match(css, /\.auction-calendar-legend i\.tentative\{background:var\(--ust-tentative-color\)\}/);
  assert.match(css, /\.released\.is-result\{background:#245c91/);
  assert.match(css, /\.released\.is-upcoming\{background:var\(--ust-upcoming-swatch\)/);
  assert.match(css, /\.released\.is-tentative\{background:var\(--ust-tentative-color\)/);
  assert.match(html, /className:`released \$\{\$==="results"\?"is-result":C\?\.tentative\?"is-tentative":"is-upcoming"\}`/);
});

test("calendar footer has no links and the upcoming badge uses a muted color with white text", () => {
  const calendar = html.match(/<script id="auction-month-calendar-script">([\s\S]*?)<\/script>/)?.[1];
  const css = html.match(/<style id="ust-v5-tentative-styles">([\s\S]*?)<\/style>/)?.[1];
  assert.ok(calendar && css);
  assert.match(calendar, /provenance\.textContent = "잠정 일정은 공식 공고 전까지 변경될 수 있습니다\."/);
  assert.doesNotMatch(calendar, /provenance\.append\(|provenance\.innerHTML|announcedLink|link\.href = info\.sourceUrl/);
  const scheduleNote = html.match(/className:"schedule-note",children:\[([\s\S]*?)\]\}\),e\("div",\{className:"table-wrap"/)?.[1];
  assert.ok(scheduleNote);
  const noteStrings = [...scheduleNote.matchAll(/"(?:\\.|[^"\\])*"/g)].map(([literal]) => literal);
  assert.equal(JSON.parse(noteStrings.at(-1)), "잠정 일정은 공식 공고 전까지 변경될 수 있습니다.");
  assert.deepEqual(noteStrings.map((literal) => JSON.parse(literal)), ["잠정 일정은 공식 공고 전까지 변경될 수 있습니다."]);
  assert.match(css, /\.auction-calendar-source,:root \.auction-month-calendar \.auction-calendar-message\{margin:0\}/);
  assert.match(css, /\.auction-calendar-message\{margin-top:-6px\}/);
  assert.match(css, /--ust-upcoming-swatch:#755b42/);
  assert.match(css, /--ust-upcoming-swatch:#8a6b4a/);
  assert.match(css, /\.auction-calendar-legend i\.upcoming\{background:var\(--ust-upcoming-swatch\)\}/);
  assert.match(css, /\.released\.is-upcoming\{background:var\(--ust-upcoming-swatch\);color:#fff/);
});

test("market rates show four decimals and the header omits data as-of text", () => {
  const dashboard = html.match(/<script id="ust-vue-dashboard-runtime">([\s\S]*?)<\/script>/)?.[1];
  const preferences = html.match(/<script id="ust-v4-preferences">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(dashboard && preferences);
  assert.match(dashboard, /i\.rate\.toFixed\(4\)/);
  assert.doesNotMatch(dashboard, /i\.rate\.toFixed\(2\)/);
  assert.doesNotMatch(preferences, /sourceTime|\.ust-asof/);
});

test("tentative badge matches reopening badge size and all chart axes keep dates only", () => {
  const css = html.match(/<style id="ust-v5-tentative-styles">([\s\S]*?)<\/style>/)?.[1];
  const dashboard = html.match(/<script id="ust-vue-dashboard-runtime">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(css && dashboard);
  assert.match(css, /\.tentative-badge\{[^}]*margin-left:4px;padding:1px 5px;[^}]*font-size:11px/);
  assert.match(html, /\.reopen-badge\{[^}]*margin-left:4px;padding:1px 5px;font-size:11px/);
  assert.match(dashboard, /function be\(\{row:t,zone:n,x:s\}\)[\s\S]*?className:"axis-date"/);
  assert.doesNotMatch(dashboard, /className:"axis-term"/);
  assert.match(dashboard, /e\(be,\{row:l,zone:s,x:/);
});

test("English mode translates new calendar and acquisition messages", () => {
  const table = JSON.parse(html.match(/<script type="application\/json" id="ust-translation-table">(.*?)<\/script>/s)?.[1]);
  const entries = table.slice().sort((a, b) => b.ko.length - a.ko.length);
  const preferences = html.match(/<script id="ust-v4-preferences">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(preferences);
  const translationFunction = preferences.slice(preferences.indexOf("function translated(text)"), preferences.indexOf("function syncText(node)"));
  const translate = new Function("entries", `${translationFunction}; return translated;`)(entries);
  for (const source of [
    "2026년 10월 · 한국 KST 기준 · 결과 12건 · 공고 4건 · 잠정 3건",
    "잠정 일정은 공식 공고 전까지 변경될 수 있습니다.",
    "미국 재무부 Fiscal Data 및 TreasuryDirect 공식 API 자료입니다. 조회 범위 2026-01-01~2026-10-22, 결과 50건, 공고 5건, 잠정 20건.",
    "잠정 · 공고 확인 필요",
    "4주 단기채 잠정을 선택했습니다.",
  ]) assert.doesNotMatch(translate(source), /[가-힣]/, source);
  assert.equal(translate("건"), " items");
  const dashboard = html.match(/<script id="ust-vue-dashboard-runtime">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(dashboard);
  for (const [, literal] of dashboard.matchAll(/("(?:\\.|[^"\\])*")/g)) {
    let source;
    try { source = JSON.parse(literal); } catch { continue; }
    if (/[가-힣]/.test(source)) assert.doesNotMatch(translate(source), /[가-힣]/, source);
  }
  assert.match(preferences, /state\.language === 'ko' \? '한국어' : 'Korean'/);
  assert.match(preferences, /UI Baseline v5/);
});

test("TreasuryDirect announcement supersedes 22 October tentative 4W without duplicating Fiscal Data", () => {
  const snapshot = JSON.parse(snapshotText);
  const { __UST_AUGMENT_OFFICIAL__: augment, __UST_MERGE_TENTATIVE__: merge } = merger();
  const rows = augment([], snapshot.announcedRows, "2026-10-22", "2027-01-20");
  const bill = rows.find((row) => row.auction_date === "2026-10-22" && row.security_term === "4-Week");
  assert.equal(bill?.offering_amt, "110000000000");
  assert.equal(bill?.announcemt_date, "2026-10-20");
  const upcoming = merge(rows, rows.map((row) => ({ auctionDate: row.auction_date, type: "Bill", term: row.security_term, cusip: row.cusip })), "2026-10-22", "2027-01-20");
  assert.ok(!upcoming.some((row) => row.auctionDate === "2026-10-22" && row.term === "4-Week" && row.tentative));
  const fiscal = { ...bill, offering_amt: "111000000000" };
  const deduped = augment([fiscal], snapshot.announcedRows, "2026-10-22", "2027-01-20");
  assert.equal(deduped.filter((row) => row.auction_date === "2026-10-22" && row.security_term === "4-Week").length, 1);
  assert.equal(deduped.find((row) => row.security_term === "4-Week")?.offering_amt, "111000000000");
  const placeholder = { ...snapshot.announcedRows.find((row) => row.securityTerm === "4-Week"), treasuryOfferingAnnouncementPressReleaseFileName: "" };
  assert.equal(augment([], [placeholder], "2026-10-22", "2027-01-20").length, 0);
});

test("22 October 10-day cash management bill is officially marked as a reopening", () => {
  const snapshot = JSON.parse(snapshotText);
  const bill = snapshot.announcedRows.find((row) => row.cusip === "912797UM7");
  assert.equal(bill?.competitiveAuctionCloseDate, "2026-10-22T00:00:00");
  assert.equal(bill?.securityTerm, "10-Day");
  assert.equal(bill?.originalSecurityTerm, "26-Week");
  assert.equal(bill?.reopening, "Yes");
  assert.equal(bill?.cashManagementBill, "Yes");
});

test("live TreasuryDirect response replaces the embedded announcement snapshot", async () => {
  let deliver;
  const document = {
    getElementById: () => ({ textContent: snapshotText }),
    createElement: () => ({ remove() {} }),
    head: { appendChild: (script) => deliver(script) },
  };
  const window = merger(document);
  const latest = { ...JSON.parse(snapshotText).announcedRows.find((row) => row.securityTerm === "4-Week"), offeringAmount: "111000000000" };
  deliver = (script) => {
    const callback = new URL(script.src).searchParams.get("callback");
    window[callback]([latest]);
  };
  assert.equal((await window.__UST_LOAD_OFFICIAL_ANNOUNCEMENTS__())[0].offeringAmount, "111000000000");
  deliver = (script) => script.onerror();
  assert.ok((await window.__UST_LOAD_OFFICIAL_ANNOUNCEMENTS__()).some((row) => row.securityTerm === "4-Week" && row.offeringAmount === "110000000000"));
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
