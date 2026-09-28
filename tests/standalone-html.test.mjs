import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlUrl = new URL("../UST_AUCTION_ui-baseline-v2.html", import.meta.url);
const loaderUrl = new URL("../standalone-live-data.js", import.meta.url);
const baselineSha256 = "d5a19347baf26ea48fff6e159e7b0992fea67481fbd146804f9ff2b62e5f1b4e";
const originalHydration = "(0,ee.hydrateRoot)(je,x.createElement(ke,Ae))";
const connectedHydration = "window.__UST_AUCTION_ROOT__=(0,ee.hydrateRoot)(je,x.createElement(ke,Ae)),window.__UST_RENDER_AUCTIONS__=e=>window.__UST_AUCTION_ROOT__.render(x.createElement(ke,e))";
const loaderTag = '<script src="./standalone-live-data.js"></script>\n';
const originalAllottedCard = "(0,A.jsx)(`strong`,{className:`kpi-value unavailable`,children:`N/A`}),(0,A.jsx)(`div`,{className:`kpi-bottom`,children:(0,A.jsxs)(`div`,{children:[(0,A.jsx)(`small`,{children:`최고 낙찰금리 배정률`}),(0,A.jsx)(`b`,{children:`자료 미연결`})]})})";
const connectedAllottedCard = "(0,A.jsx)(`strong`,{className:T?.allottedAtHigh==null?`kpi-value unavailable`:`kpi-value`,children:S(T?.allottedAtHigh)}),(0,A.jsx)(`div`,{className:`kpi-bottom`,children:(0,A.jsxs)(`div`,{children:[(0,A.jsx)(`small`,{children:`최고 낙찰금리 배정률`}),(0,A.jsx)(`b`,{children:T?.allottedAtHigh==null?`자료 미연결`:`allocation_pctage`})]})})";
const originalAllottedCell = "(0,A.jsx)(`td`,{className:`unavailable`,children:`N/A`})";
const connectedAllottedCell = "(0,A.jsx)(`td`,{className:e.allottedAtHigh==null?`unavailable`:``,children:S(e.allottedAtHigh)})";
const originalAllocationSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:[`최근 `,ge.length,`건 · 전체 낙찰액 기준`]})";
const connectedAllocationSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:n===`live`?[se(T),` · 동일 종류·만기 `,ge.length,`건 · 전체 낙찰액 기준`]:[`최근 `,ge.length,`건 · 전체 낙찰액 기준`]})";
const originalSubscriptionSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:[`최근 `,ge.length,`건 · `,d===`All`?`전체 종류·만기`:oe(d),` · 입찰별 비교`]})";
const connectedSubscriptionSubtitle = "(0,A.jsxs)(`p`,{className:`chart-subtitle`,children:n===`live`?[se(T),` · 동일 종류·만기 `,ge.length,`건 · 입찰별 비교`]:[`최근 `,ge.length,`건 · `,d===`All`?`전체 종류·만기`:oe(d),` · 입찰별 비교`]})";
const originalSubscriptionChart = "(0,A.jsx)(j,{rows:ge,kind:`subscription`,onSelect:Ae,zone:l})";
const connectedSubscriptionChart = "n===`live`?(0,A.jsx)(Me,{rows:ge,kind:`subscription`,onSelect:Ae,zone:l,subscriptionAverage:recentSubscriptionAverage,subscriptionAverageCount:recentSubscriptionValues.length}):(0,A.jsx)(j,{rows:ge,kind:`subscription`,onSelect:Ae,zone:l})";
const originalSubscriptionLegend = "(0,A.jsx)(`div`,{className:`legend`,children:(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`swatch pink`}),`응찰률 (%)`]})})";
const connectedSubscriptionLegend = "(0,A.jsx)(`div`,{className:`legend`,children:n===`live`?(0,A.jsxs)(A.Fragment,{children:[(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`swatch pink`}),`응찰률 (%)`]}),(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`swatch`,style:{background:`transparent`,borderTop:`2px dashed #e5c581`,height:0}}),`최근 6개 평균 (`,recentSubscriptionValues.length,`개 유효) `,S(recentSubscriptionAverage,1)]})]}):(0,A.jsxs)(`span`,{children:[(0,A.jsx)(`i`,{className:`swatch pink`}),`응찰률 (%)`]})})";

async function sources() {
  const [html, loader] = await Promise.all([
    readFile(htmlUrl, "utf8"),
    readFile(loaderUrl, "utf8"),
  ]);
  return { html, loader };
}

test("standalone keeps the attached UI baseline byte-for-byte outside data wiring", async () => {
  const { html } = await sources();
  assert.equal(html.split(connectedHydration).length, 2, "one renderer connection must exist");
  assert.equal(html.split(connectedAllottedCard).length, 2, "one Allotted at High connection must exist");
  assert.equal(html.split(connectedAllottedCell).length, 2, "one result-table allocation connection must exist");
  assert.equal(html.split(loaderTag).length, 2, "one live-data loader tag must exist");
  for (const connection of [connectedAllocationSubtitle, connectedSubscriptionSubtitle, connectedSubscriptionChart, connectedSubscriptionLegend]) assert.equal(html.split(connection).length, 2, "one chart data connection must exist");
  const comparisonStart = html.indexOf("sameTermRows=");
  const comparisonEnd = html.indexOf("_e=T?", comparisonStart);
  const averageChartStart = html.indexOf("function Me({rows:e,kind:t,onSelect:n,zone:r,subscriptionAverage");
  const averageChartEnd = html.indexOf("function be(", averageChartStart);
  assert.ok(comparisonStart >= 0 && comparisonEnd >= 0, "comparison data wiring must exist");
  assert.ok(averageChartStart >= 0 && averageChartEnd >= 0, "average chart renderer must exist");
  const withoutAverageChart = html.slice(0, averageChartStart) + html.slice(averageChartEnd);
  const restored = withoutAverageChart
    .replace(connectedHydration, originalHydration)
    .replace(connectedAllottedCard, originalAllottedCard)
    .replace(connectedAllottedCell, originalAllottedCell)
    .replace(connectedAllocationSubtitle, originalAllocationSubtitle)
    .replace(connectedSubscriptionSubtitle, originalSubscriptionSubtitle)
    .replace(connectedSubscriptionChart, originalSubscriptionChart)
    .replace(connectedSubscriptionLegend, originalSubscriptionLegend)
    .replace(loaderTag, "");
  const restoredComparisonStart = restored.indexOf("sameTermRows=");
  const restoredComparisonEnd = restored.indexOf("_e=T?", restoredComparisonStart);
  const baselineRestored = restored.slice(0, restoredComparisonStart)
    + "ge=v.slice(0,9).reverse(),"
    + restored.slice(restoredComparisonEnd);
  assert.equal(createHash("sha256").update(baselineRestored).digest("hex"), baselineSha256);
});

test("standalone reuses the baseline dashboard instead of creating another view", async () => {
  const { html, loader } = await sources();
  assert.match(html, /window\.__UST_RENDER_AUCTIONS__/);
  assert.match(loader, /window\.__UST_RENDER_AUCTIONS__\(\{/);
  assert.doesNotMatch(html, /official-live-view|official-live-tab|official-live-hero/);
  assert.doesNotMatch(loader, /createElement\(|insertAdjacentHTML|innerHTML\s*=/);
});

test("standalone live charts use matching type and term with a recent-six average", async () => {
  const { html } = await sources();
  assert.match(html, /e\.type===T\.type&&e\.term===T\.term&&\(e\.auctionDate<T\.auctionDate\|\|M\(e\)===M\(T\)\)/);
  assert.match(html, /recentSubscriptionValues=.*?filter\(e=>e!=null\)\.slice\(0,6\)/);
  assert.match(html, /최근 6개 평균/);
  assert.match(html, /strokeDasharray:`5 4`/);
});

test("standalone loader follows every Fiscal Data page and rejects partial results", async () => {
  const { loader } = await sources();
  assert.match(loader, /api\.fiscaldata\.treasury\.gov/);
  assert.match(loader, /page\[number\]/);
  assert.match(loader, /total-pages/);
  assert.match(loader, /total-count/);
  assert.match(loader, /rows\.length !== totalCount/);
  assert.match(loader, /pagination incomplete/);
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
