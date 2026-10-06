import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlUrl = new URL("../UST_AUCTION_ui-baseline-v2.html", import.meta.url);
const loaderUrl = new URL("../standalone-live-data.js", import.meta.url);
const connectedRenderer = "je=document.getElementById(`root`);window.__UST_AUCTION_DATA__=Ae;if(!je)throw Error(`Missing application root`);window.__UST_AUCTION_ROOT__=(0,ee.createRoot)(je),window.__UST_AUCTION_ROOT__.render(x.createElement(ke,Ae)),window.__UST_RENDER_AUCTIONS__=e=>(window.__UST_AUCTION_DATA__=e,window.__UST_AUCTION_ROOT__.render(x.createElement(ke,e)))";
const loaderTag = '<script src="./standalone-live-data.js"></script>';
const connectedAllottedCard = "(0,A.jsx)(`strong`,{className:T?.allottedAtHigh==null?`kpi-value unavailable`:`kpi-value`,children:S(T?.allottedAtHigh)}),(0,A.jsx)(`div`,{className:`kpi-bottom`,children:(0,A.jsxs)(`div`,{children:[(0,A.jsx)(`small`,{children:`최고 낙찰금리 배정률`}),(0,A.jsx)(`b`,{children:T?.allottedAtHigh==null?`자료 미연결`:`allocation_pctage`})]})})";
const connectedAllottedCell = "(0,A.jsx)(`td`,{className:e.allottedAtHigh==null?`unavailable`:``,children:S(e.allottedAtHigh)})";
const connectedAllocationSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:n===`live`?[se(T),` · 동일 종류·만기 `,ge.length,`건 · 전체 낙찰액 기준`]:[`최근 `,ge.length,`건 · 전체 낙찰액 기준`]})";
const connectedSubscriptionSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:[se(T),` · 동일 종류·만기 `,subscriptionRows.length,`건 · 장기 기준과 최근 흐름`]})";
const connectedSubscriptionChart = "(0,A.jsx)(Me,{rows:subscriptionRows,onSelect:Ae,zone:l})";
const connectedSubscriptionLegend = "(0,A.jsxs)(`div`,{className:`legend`,children:[(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`legend-dot`}),`개별 입찰값`]}),(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`legend-line baseline`}),`24개월 평균`]}),(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`swatch sigma-band`}),`24개월 평균 ±1σ`]}),(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`legend-line current`}),`최근 6회 평균`]})]})";

async function sources() {
  const [html, loader] = await Promise.all([
    readFile(htmlUrl, "utf8"),
    readFile(loaderUrl, "utf8"),
  ]);
  return { html, loader };
}

test("standalone keeps one dashboard renderer and connects live data to the approved UI", async () => {
  const { html } = await sources();
  assert.equal(html.split(connectedRenderer).length, 2, "one renderer connection must exist");
  assert.equal(html.split(connectedAllottedCard).length, 2, "one Allotted at High connection must exist");
  assert.equal(html.split(connectedAllottedCell).length, 2, "one result-table allocation connection must exist");
  assert.equal(html.split(loaderTag).length, 2, "one live-data loader tag must exist");
  for (const connection of [connectedAllocationSubtitle, connectedSubscriptionSubtitle, connectedSubscriptionChart, connectedSubscriptionLegend]) assert.equal(html.split(connection).length, 2, "one chart data connection must exist");
  assert.match(html, /sameTermRows=/);
  assert.match(html, /function ustSubscriptionDate\(/);
});

test("standalone offers nominal maturity filters without mixing FRN or TIPS", async () => {
  const { html } = await sources();
  assert.match(html, /class="filter-row" role="group" aria-label="국채 종류 및 명목 중·장기채 만기 필터"/);
  for (const label of ["전체", "단기채", "2년", "3년", "5년", "7년", "10년", "20년", "30년", "물가연동채", "변동금리채"]) {
    assert.match(html, new RegExp(`>${label}<\\/button>`), label);
  }
  assert.doesNotMatch(html, />중기채<\/button>|>장기채<\/button>/);
  assert.match(html, /\{id:`note-2`,label:`2년`,type:`Note`,term:`2-Year`\}/);
  assert.match(html, /\{id:`note-10`,label:`10년`,type:`Note`,term:`10-Year`\}/);
  assert.match(html, /\{id:`bond-20`,label:`20년`,type:`Bond`,term:`20-Year`\}/);
  assert.match(html, /\{id:`bond-30`,label:`30년`,type:`Bond`,term:`30-Year`\}/);
  assert.match(html, /e\.type===n\.type&&\(!n\.term\|\|e\.term===n\.term\|\|e\.securityTerm===n\.term\)/);
  assert.match(html, /t\.filter\(e=>ustMatchesAuctionFilter\(e,d\)&&e\.auctionDate>=ustFrom&&e\.auctionDate<=ustTo\)/);
  assert.match(html, /y=_,b=s===`calendar`\?y:v/);
  assert.match(html, /className:`filter-row`,role:`group`/);
  assert.match(html, /className:d===e\.id\?`selected`/);
  assert.match(html, /\.filter-row\{flex-wrap:wrap;min-width:0\}/);
});

test("standalone reuses the baseline dashboard instead of creating another view", async () => {
  const { html, loader } = await sources();
  assert.match(html, /window\.__UST_RENDER_AUCTIONS__/);
  assert.match(loader, /window\.__UST_RENDER_AUCTIONS__\(\{/);
  assert.doesNotMatch(html, /official-live-view|official-live-tab|official-live-hero/);
  assert.doesNotMatch(loader, /createElement\(|insertAdjacentHTML|innerHTML\s*=/);
});

test("standalone inline scripts remain valid JavaScript", async () => {
  const { html } = await sources();
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
  assert.ok(scripts.length >= 2);
  for (const script of scripts) assert.doesNotThrow(() => new Function(script));
});

test("standalone bid-to-cover chart uses points, 24-month average ±1σ, and recent-six rolling average", async () => {
  const { html } = await sources();
  assert.match(html, /e\.type===T\.type&&e\.term===T\.term&&\(e\.auctionDate<T\.auctionDate\|\|M\(e\)===M\(T\)\)/);
  assert.match(html, /subscriptionRows=\[\.\.\.sameTermRows\]\.reverse\(\)/);
  assert.match(html, /function ustSubscriptionRollingSeries/);
  assert.match(html, /date\.getTime\(\)>a/);
  assert.match(html, /average6:i\.length===6/);
  assert.match(html, /average24Months:s/);
  assert.match(html, /className:`subscription-band`/);
  assert.match(html, /className:`subscription-average-24`/);
  assert.match(html, /className:`subscription-average-6`/);
  assert.match(html, /24개월 평균 ±1σ/);
  assert.doesNotMatch(html, /recentSubscriptionAverage|strokeDasharray:`5 4`/);
});

test("standalone loader follows every Fiscal Data page and rejects partial results", async () => {
  const { loader } = await sources();
  assert.match(loader, /api\.fiscaldata\.treasury\.gov/);
  assert.match(loader, /page\[number\]/);
  assert.match(loader, /total-pages/);
  assert.match(loader, /total-count/);
  assert.match(loader, /rows\.length !== totalCount/);
  assert.match(loader, /pagination incomplete/);
  assert.match(loader, /shiftCalendarMonths\(range\.from, -25\)/);
  assert.match(loader, /row\.auctionDate <= upcomingTo/);
});

test("standalone defaults to two years and exposes an accessible URL-backed date range", async () => {
  const { html, loader } = await sources();
  assert.match(html, /id:`auction-result-from`,name:`from`,type:`date`/);
  assert.match(html, /id:`auction-result-to`,name:`to`,type:`date`/);
  assert.match(html, /className:`date-range-submit`,children:`조회`/);
  assert.match(html, /className:`date-range-reset`[^}]*children:`최근 2년`/);
  assert.match(html, /className:`date-range-error`,role:`alert`/);
  assert.match(html, /e\.auctionDate>=ustFrom&&e\.auctionDate<=ustTo/);
  assert.match(html, /window\.location\.assign\(n\.toString\(\)\)/);
  assert.match(html, /useEffect\)\(\(\)=>\{ustSetFromInput\(ustFrom\),ustSetToInput\(ustTo\),f\(ustInitialFilter\(ustFilter\)\)\}/);
  assert.match(html, /ustFrom,` ~ `,ustTo,` · `,v\.length,`건`/);
  assert.match(html, /className:`section-heading results-heading`/);
  assert.doesNotMatch(html, /className:`section-heading`,children:\[\(0,A\.jsx\)\(`h2`,\{className:`panel-heading`,children:`최근 입찰 결과`\}\).*?className:`date-range-form`/);
  assert.match(html, /\.results-heading \{[^}]*flex-wrap: nowrap/);
  assert.match(html, /@media \(max-width: 600px\)[\s\S]*?\.date-range-form \{[^}]*flex-wrap: wrap/);
  assert.match(html, /@media \(max-width: 600px\)/);
  assert.match(loader, /const defaultRange = \(today\)/);
  assert.match(loader, /parameters\.get\("from"\)/);
  assert.match(loader, /parameters\.get\("to"\)/);
  assert.match(loader, /resultFrom: range\.from/);
  assert.match(loader, /defaultResultFrom: defaults\.from/);
});

test("standalone validates and preserves filter in URL, date actions, reload, and API failure", async () => {
  const { html, loader } = await sources();
  assert.match(loader, /FILTER_IDS = new Set\(\["all", "bill", "note-2"/);
  assert.match(loader, /FILTER_IDS\.has\(candidate\) \? candidate : "all"/);
  assert.equal((loader.match(/initialFilter,/g) ?? []).length, 2, "success and failure renders both preserve filter");
  assert.match(html, /function ustInitialFilter\(e\)/);
  assert.match(html, /Ee\.some\(e=>e\.id===t\)\?t:`all`/);
  assert.match(html, /n\.searchParams\.set\(`filter`,d\),window\.location\.assign/);
  assert.match(html, /t\.searchParams\.set\(`filter`,e\),window\.history\.replaceState/);
  assert.match(html, /onClick:\(\)=>ustChangeFilter\(e\.id\)/);
  assert.doesNotMatch(html, /c\(e\),f\(`all`\),m\(``\)/);
});

test("standalone keeps the full calendar and removes unavailable WI and Tail UI", async () => {
  const { html } = await sources();
  assert.match(html, /y=_,b=s===`calendar`\?y:v/);
  assert.doesNotMatch(html, /_\.filter\(e=>ustMatchesAuctionFilter\(e,d\)\)/);
  assert.doesNotMatch(html, /When-Issued|Tail \(bp\)/);
  assert.match(html, /className:`kpi stop-kpi`/);
  assert.match(html, /children:`결과 입찰 종류`/);
});

test("standalone adds a month-selectable overview calendar wired to the existing auction rows", async () => {
  const { html } = await sources();
  assert.match(html, /id="auction-month-calendar-styles"/);
  assert.match(html, /id="auction-month-calendar-script"/);
  assert.match(html, /className = "calendar-year"/);
  assert.match(html, /className = "calendar-month"/);
  assert.match(html, /\.dashboard \{ grid-template-columns: 360px minmax\(0, 1fr\); \}/);
  assert.match(html, /\.auction-calendar-head \.panel-heading \{[^}]*white-space: nowrap/);
  assert.match(html, /\.auction-calendar-nav \.calendar-year \{ width: 72px; \}/);
  assert.match(html, /\.auction-calendar-nav \.calendar-month \{ width: 64px; \}/);
  assert.match(html, /\.auction-calendar-nav select \{ height: 26px;/);
  assert.match(html, /\.auction-calendar-nav button \{ width: 28px;/);
  assert.match(html, /const state = \{[^}]*excludeBills: true/);
  assert.match(html, /className = "auction-calendar-filter"/);
  assert.match(html, /aria-label", "캘린더에서 단기채 일정 제외"/);
  assert.match(html, /!state\.excludeBills \|\| auction\.type !== "Bill"/);
  assert.match(html, /state\.excludeBills = excludeBills\.checked/);
  assert.match(html, /\.key-results \.underlined::after \{ content: none; \}/);
  assert.match(html, /\.key-results \.kpi \{ min-height: 132px; padding-block: 10px; \}/);
  assert.match(html, /const latest = events\.at\(-1\)\?\.display\.date\.slice\(0, 7\)/);
  assert.match(html, /: \[Number\(current\.year\), Number\(current\.month\)\]/);
  assert.match(html, /const zone = selectedZone\(\)/);
  assert.match(html, /displayAuction\(event\.auction, zone\)/);
  assert.match(html, /event\.display\.date === date/);
  assert.match(html, /\.zone-switch button/);
  assert.match(html, /\.key-results > \.section-heading \{ justify-content: flex-start/);
  assert.match(html, /event\.status === "result" \? "auction-results" : "auction-calendar"/);
  assert.match(html, /const auctionIdentity = \(auction\) => `\$\{auction\.auctionDate\}\|\$\{auction\.type \|\| ""\}\|\$\{auction\.term \|\| ""\}`/);
  assert.match(html, /existing\.status === "upcoming" && event\.status === "result"/);
  assert.match(html, /visibleResults\.findIndex\(\(auction\) => auctionRecordIdentity\(auction\) === auctionRecordIdentity\(event\.auction\)\)/);
  assert.match(html, /button\.click\(\)/);
  assert.match(html, /!host\?\.querySelector\("\.auction-month-calendar"\) \|\| state\.data !== window\.__UST_AUCTION_DATA__/);
  assert.match(html, /입찰 완료/);
  assert.match(html, /입찰 예정/);

  const match = html.match(/<script id="auction-month-calendar-script">([\s\S]*?)<\/script>/);
  assert.ok(match, "calendar script must exist");
  assert.doesNotThrow(() => new Function(match[1]));
});

test("standalone loader maps official result fields and has valid JavaScript", async () => {
  const { loader } = await sources();
  assert.doesNotThrow(() => new Function(loader));
  for (const field of [
    "inflation_index_security", "floating_rate", "high_discnt_rate", "high_discnt_margin",
    "high_yield", "bid_to_cover_ratio", "allocation_pctage", "primary_dealer_accepted",
    "direct_bidder_accepted", "indirect_bidder_accepted",
  ]) assert.ok(loader.includes(field), field);
  assert.match(loader, /allottedAtHigh: number\(row\.allocation_pctage\)/);
  assert.match(loader, /source: "live"/);
});

test("standalone loader never renders the saved sample after an API failure", async () => {
  const { loader } = await sources();
  assert.match(loader, /upcoming: \[\],\s*results: \[\],\s*source: "unavailable"/s);
  assert.match(loader, /표본값으로 대체하지 않습니다/);
  assert.doesNotMatch(loader, /fallbackUpcoming|fallbackResults|resultSeed|912797SU2/);
});
