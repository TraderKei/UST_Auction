import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadSource } from "./source-loader.mjs";

const { subscriptionPercent, subscription, awardMix, priorResult, percentagePointChange, signedPoints } = loadSource("../lib/auction-display.ts");
const { normalizeFiscalAuction } = loadSource("../lib/treasury.ts");
const Dashboard = loadSource("../app/AuctionDashboard.tsx").default;
const Reference = loadSource("../app/AuctionReference.tsx").default;
const base = {
  cusip: "TEST00001", auctionDate: "2026-08-20", announcementDate: "2026-08-13",
  issueDate: "2026-08-31", maturityDate: "2036-08-31", type: "Note", term: "10-Year",
  securityTerm: "10-Year", offeringAmount: 42e9, closingTimeCompetitive: "01:00 PM",
  reopening: true, cmb: false, bidToCover: 2.48, stopRate: 4.325, stopLabel: "High yield",
  investmentRate: null, couponRate: 4.25, pricePer100: 99.8125, totalTendered: 104.16e9,
  totalAccepted: 42e9, dealerAccepted: 6.3e9, directAccepted: 8.4e9, indirectAccepted: 25.2e9,
};
const props = { upcoming: [], results: [base], source: "unavailable", updatedAt: "2026-08-21T06:30:00Z" };
const visibleText = html => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("응찰률: 2.48 → 248.0%, 결측값은 N/A, 0은 0.0%", () => {
  assert.equal(subscriptionPercent(2.48), 248);
  assert.equal(subscription(2.48), "248.0%");
  assert.equal(subscription(0), "0.0%");
  for (const value of [null, undefined, NaN, Infinity, -1]) assert.equal(subscription(value), "N/A");
});

test("기본 화면은 다크 UST AUCTION 결과 대시보드", async () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.match(html, /UST AUCTION/);
  for (const label of ["주요 입찰 결과", "최근 입찰", "참여자별 낙찰 비중", "시장 동향", "최근 입찰 결과", "예정 입찰 일정"]) assert.ok(html.includes(label), label);
  assert.match(css, /--bg:\s*#071522/);
  assert.match(css, /color-scheme:\s*dark/);
  assert.doesNotMatch(visibleText(html), /FV Terminal|BID\s*\/\s*COVER|Bid-to-cover|\bBTC\b|\d+(?:\.\d+)?\s*[×x]/i);
  assert.match(visibleText(html), /248\.0%/);
  assert.match(html, /응찰률 \(%\)/);
});

test("응찰률 차트 좌표·축도 % 단위이며 누락값을 0으로 만들지 않음", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  assert.match(html, /aria-label="응찰률 \(%\) 차트"/);
  const chart = html.match(/<svg[^>]+aria-label="응찰률 \(%\) 차트"[\s\S]*?<\/svg>/)?.[0];
  assert.ok(chart);
  assert.match(chart, /248\.0%/);
  assert.doesNotMatch(chart, /2\.48/);
  assert.doesNotMatch(html, /\d+(?:\.\d+)?\s+times|NaN|Infinity/);
  const missing = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [{ ...base, bidToCover: null }] }));
  assert.match(missing, /N\/A/);
  assert.doesNotMatch(visibleText(missing), /248\.0%|NaN|Infinity/);
});

test("빈 데이터에서도 정상 렌더링하고 임의 시장금리를 만들지 않음", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [] }));
  assert.match(html, /결과 없음/);
  assert.match(html, /미연결/);
  assert.doesNotMatch(html, /NaN|Infinity|VERIFIED SNAPSHOT/);
});

test("배정 비중 합계는 100%, 누락 데이터는 N/A 처리", () => {
  assert.deepEqual(awardMix(base), [60, 20, 15, 5]);
  assert.equal(awardMix({ ...base, directAccepted: null }), null);
  assert.equal(awardMix({ ...base, totalAccepted: 0 }), null);
  assert.equal(awardMix({ ...base, indirectAccepted: 100e9 }), null);
});

test("이전 결과는 같은 종류·만기, 이전 날짜만 사용", () => {
  const prior = { ...base, auctionDate: "2026-07-20" };
  assert.equal(priorResult(base, [{ ...base, type: "Bill" }, base, prior]), prior);
  assert.equal(priorResult(base, [base, { ...prior, term: "2-Year" }]), undefined);
});

test("KPI 평균도 %이고 차이는 %p: 248.0% - 236.0% = +12.0%p", () => {
  const previous = { ...base, auctionDate: "2026-07-20", bidToCover: 2.36 };
  const unrelated = { ...base, type: "Bill", term: "4-Week", bidToCover: 9, auctionDate: "2026-07-21" };
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [base, previous, unrelated] }));
  const kpi = html.match(/<article class="kpi subscription-kpi">[\s\S]*?<\/article>/)?.[0];
  assert.ok(kpi);
  assert.match(kpi, /248\.0%/);
  assert.match(kpi, /236\.0%/);
  assert.match(kpi, /\+12\.0%p/);
  assert.doesNotMatch(kpi, /900\.0%/);
});

test("KPI 6개의 순서가 요구와 일치하고 Price KPI가 없음", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  const headings = [...html.matchAll(/<article class="kpi[^"]*"><h3>(.*?)<\/h3>/g)].map(match => match[1]);
  assert.deepEqual(headings, ["응찰률 (%)", "High Yield (Stop)", "간접낙찰률", "직접낙찰률", "PD낙찰률", "Allotted at High"]);
  assert.match(html, /낙찰가격 \(\$100\)/); // 하단 결과표의 가격은 요청 범위 밖이므로 유지
});

test("CUSIP는 화면·접근성 문구·툴팁·참고 화면에서 제거", () => {
  for (const component of [React.createElement(Dashboard, props), React.createElement(Reference, { view: "api" }), React.createElement(Reference, { view: "database" })]) {
    const html = renderToStaticMarkup(component);
    assert.doesNotMatch(html, /cusip|TEST00001/i);
  }
});

test("간접·직접·PD 직전 대비 증감은 +/−/0 %p로 표시", () => {
  const previous = { ...base, auctionDate: "2026-07-20", indirectAccepted: 23.1e9, directAccepted: 10.5e9 };
  const other = { ...previous, type: "Bill", auctionDate: "2026-08-19", indirectAccepted: 0 };
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [base, previous, other] }));
  const cards = [...html.matchAll(/<article class="kpi bidder-kpi">([\s\S]*?)<\/article>/g)].map(match => visibleText(match[1]));
  assert.equal(cards.length, 3);
  assert.match(cards[0], /간접낙찰률 60\.0% 직전 입찰 대비 \+5\.0%p/);
  assert.match(cards[1], /직접낙찰률 20\.0% 직전 입찰 대비 -5\.0%p/);
  assert.match(cards[2], /PD낙찰률 15\.0% 직전 입찰 대비 0\.0%p/);
  assert.equal(percentagePointChange(60, 55), 5);
  assert.equal(percentagePointChange(60, null), null);
  assert.equal(signedPoints(-0.000001), "0.0%p");
});

test("직전 자료 또는 낙찰액이 없으면 증감을 만들지 않음", () => {
  const missingPrevious = { ...base, auctionDate: "2026-07-20", directAccepted: null };
  for (const results of [[base], [base, missingPrevious]]) {
    const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results }));
    const cards = [...html.matchAll(/<article class="kpi bidder-kpi">([\s\S]*?)<\/article>/g)];
    for (const card of cards) assert.match(card[1], /비교 자료 없음/);
  }
});

test("한국/ET 날짜·자료 기준 시각·차트가 같은 시간대 규칙 사용", () => {
  const korean = renderToStaticMarkup(React.createElement(Dashboard, props));
  const eastern = renderToStaticMarkup(React.createElement(Dashboard, { ...props, initialZone: "ET" }));
  assert.match(korean, /2026-08-21 02:00 · 한국 KST/);
  assert.match(eastern, /2026-08-20 13:00 · 미국 동부 ET/);
  assert.match(korean, /2026-08-21 15:30 · 한국 KST/);
  assert.match(eastern, /2026-08-21 02:30 · 미국 동부 ET/);
  for (const html of [korean, eastern]) {
    assert.match(html, /2026-08-31<\/span><small>원문 ET · 시각 없음/);
    assert.match(html, /2036-08-31<\/span><small>원문 ET · 시각 없음/);
    assert.doesNotMatch(html, /Aug |Jul |\d{2}\/\d{2}\/\d{4}/);
  }
  assert.match(korean, /class="axis-date"[^>]*>2026-08-21<\/text>/);
  assert.match(eastern, /class="axis-date"[^>]*>2026-08-20<\/text>/);
});

test("시각 없는 결과는 KST를 선택해도 원문 날짜·ET 표시 유지", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [{ ...base, closingTimeCompetitive: "" }] }));
  assert.match(html, /2026-08-20 · 원문 ET · 시각 없음\/확인 불가/);
  assert.match(html, /class="axis-date"[^>]*>2026-08-20<\/text>/);
  assert.doesNotMatch(html, /2026-08-21 02:00/);
});

test("최근 결과와 향후 수신 일정이 기본 화면에 동시에 표시", () => {
  const upcoming = [{ ...base, auctionDate: "2026-08-25" }];
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, source: "fiscal-api", sourceRange: "2024-09-23~2026-12-22", upcoming }));
  assert.match(html, /aria-label="최근 입찰 결과표"/);
  assert.match(html, /aria-label="예정 입찰 일정표"/);
  assert.match(html, /2026-08-26 02:00 · 한국 KST 10년 중기채 일정 선택/);
  assert.match(html, /예정 1건/);
  assert.match(html, /아직 공고되지 않은 계획은 포함하지 않습니다/);
});

test("API 실패 시 표본 일정으로 대체하지 않음", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, upcoming: [{ ...base, auctionDate: "2026-08-25" }] }));
  assert.match(html, /공식 API 수신 실패/);
  assert.match(html, /표본 일정으로 대체하지 않았습니다/);
});

test("Allotted at High 공식값을 표시하고 결측은 N/A로 유지", () => {
  const available = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [{ ...base, allottedAtHigh: 33.42 }] }));
  assert.match(available, /Allotted at High[\s\S]*33\.4%[\s\S]*Fiscal Data 공식값/);
  const missing = renderToStaticMarkup(React.createElement(Dashboard, props));
  assert.match(missing, /Allotted at High[\s\S]*N\/A[\s\S]*원천 자료 없음/);
});

test("운영 로더에 하드코딩된 표본 입찰 데이터가 없음", async () => {
  const source = await readFile(new URL("../lib/treasury.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /fallbackUpcoming|fallbackResults|resultSeed|912797SU2/);
  assert.match(source, /api\.fiscaldata\.treasury\.gov/);
});

test("Fiscal Data snake_case를 상품별 Stop과 Allotted at High로 정규화", () => {
  const tips = normalizeFiscalAuction({
    cusip: "TEST", security_type: "Note", security_term: "9-Year 10-Month", original_security_term: "10-Year",
    inflation_index_security: "Yes", floating_rate: "No", auction_date: "2026-09-22", offering_amt: "18000000000",
    high_yield: "2.125", bid_to_cover_ratio: "2.48", allocation_pctage: "33.42", reopening: "Yes",
  });
  assert.equal(tips.type, "TIPS");
  assert.equal(tips.term, "10-Year");
  assert.equal(tips.stopRate, 2.125);
  assert.equal(tips.stopLabel, "High real yield");
  assert.equal(tips.allottedAtHigh, 33.42);
  assert.equal(tips.offeringAmount, 18e9);
  assert.equal(tips.reopening, true);

  const frn = normalizeFiscalAuction({ security_type: "Note", floating_rate: "Yes", high_discnt_margin: "0.075" });
  assert.equal(frn.type, "FRN");
  assert.equal(frn.stopRate, 0.075);
  assert.equal(frn.stopLabel, "Discount margin");
});

test("금리 종류를 구분하고 유효 평균 표본 수를 정확히 표시", () => {
  for (const [type, expected] of [["Bill", "High Rate (Stop)"], ["TIPS", "실질금리 (Stop)"], ["FRN", "할인마진 (Stop)"]]) {
    const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [{ ...base, type }] }));
    assert.ok(html.includes(`<h3>${expected}</h3>`));
  }
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [base, { ...base, auctionDate: "2026-07-20", bidToCover: null }, { ...base, auctionDate: "2026-06-20", bidToCover: 2.36 }] }));
  assert.match(html, /직전 평균 · 유효 1\/2건/);
});
