import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadSource } from "./source-loader.mjs";

const { subscriptionPercent, subscription, subscriptionRollingSeries, awardMix, priorResult, percentagePointChange, signedPoints } = loadSource("../lib/auction-display.ts");
const { normalizeFiscalAuction } = loadSource("../lib/treasury.ts");
const { defaultAuctionDateRange, filterAuctionsByDateRange, isIsoDate, resolveAuctionDateRange, shiftCalendarMonths, shiftCalendarYears, validateAuctionDateRange } = loadSource("../lib/auction-date-range.ts");
const { AUCTION_FILTER_IDS, resolveAuctionFilter } = loadSource("../lib/auction-filter.ts");
const dashboardModule = loadSource("../app/AuctionDashboard.tsx");
const Dashboard = dashboardModule.default;
const { auctionFilters, matchesAuctionFilter, filterAuctionRows, filterResultRows } = dashboardModule;
const Reference = loadSource("../app/AuctionReference.tsx").default;
const base = {
  cusip: "TEST00001", auctionDate: "2026-08-20", announcementDate: "2026-08-13",
  issueDate: "2026-08-31", maturityDate: "2036-08-31", type: "Note", term: "10-Year",
  securityTerm: "10-Year", offeringAmount: 42e9, closingTimeCompetitive: "01:00 PM",
  reopening: true, cmb: false, bidToCover: 2.48, stopRate: 4.325, stopLabel: "High yield",
  investmentRate: null, couponRate: 4.25, pricePer100: 99.8125, totalTendered: 104.16e9,
  totalAccepted: 42e9, dealerAccepted: 6.3e9, directAccepted: 8.4e9, indirectAccepted: 25.2e9,
};
const props = {
  upcoming: [], results: [base], source: "unavailable", updatedAt: "2026-08-21T06:30:00Z",
  resultFrom: "2024-08-21", resultTo: "2026-08-21", defaultResultFrom: "2024-08-21", defaultResultTo: "2026-08-21",
};
const visibleText = html => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("기본 조회기간은 달력 기준 최근 2년이며 윤년·월말을 안전하게 처리", () => {
  assert.deepEqual(defaultAuctionDateRange(new Date("2026-09-30T23:59:59Z")), { from: "2024-09-30", to: "2026-09-30" });
  assert.equal(shiftCalendarYears("2024-02-29", -2), "2022-02-28");
  assert.equal(shiftCalendarMonths("2024-03-31", -1), "2024-02-29");
  assert.equal(isIsoDate("2026-02-29"), false);
  assert.equal(isIsoDate("2024-02-29"), true);
});

test("URL 조회기간은 엄격히 검증하고 잘못된 값은 최근 2년으로 복구", () => {
  const today = new Date("2026-09-30T12:00:00Z");
  assert.deepEqual(resolveAuctionDateRange({ from: "2020-01-01", to: "2020-12-31" }, today), { from: "2020-01-01", to: "2020-12-31" });
  for (const parameters of [
    { from: "2026-02-29", to: "2026-09-30" },
    { from: "2026-10-01", to: "2026-09-30" },
    { from: "", to: "2026-09-30" },
  ]) assert.deepEqual(resolveAuctionDateRange(parameters, today), { from: "2024-09-30", to: "2026-09-30" });
  assert.equal(validateAuctionDateRange("", "2026-09-30"), "시작일과 종료일을 모두 입력해 주세요.");
  assert.equal(validateAuctionDateRange("2026-10-01", "2026-09-30"), "시작일은 종료일보다 늦을 수 없습니다.");
});

test("URL 만기 필터는 허용 목록만 복원하고 날짜 복구와 독립적으로 유지", () => {
  assert.deepEqual(AUCTION_FILTER_IDS, ["all", "bill", "note-2", "note-3", "note-5", "note-7", "note-10", "bond-20", "bond-30", "tips", "frn"]);
  assert.equal(resolveAuctionFilter("note-10"), "note-10");
  assert.equal(resolveAuctionFilter(["bond-20", "all"]), "bond-20");
  assert.equal(resolveAuctionFilter("not-a-filter"), "all");
  assert.equal(resolveAuctionFilter(undefined), "all");
  assert.deepEqual(resolveAuctionDateRange({ from: "bad", to: "2026-09-30" }, new Date("2026-09-30T12:00:00Z")), { from: "2024-09-30", to: "2026-09-30" });
  assert.equal(resolveAuctionFilter("note-10"), "note-10");
});

test("결과 날짜 범위는 양쪽 경계를 포함하고 종류 필터와 AND로 결합", () => {
  const rows = [
    { ...base, cusip: "FROM", auctionDate: "2025-01-01", term: "2-Year", securityTerm: "2-Year" },
    { ...base, cusip: "MIDDLE", auctionDate: "2025-06-01", term: "2-Year", securityTerm: "2-Year" },
    { ...base, cusip: "OTHER", auctionDate: "2025-07-01", term: "10-Year", securityTerm: "10-Year" },
    { ...base, cusip: "TO", auctionDate: "2025-12-31", term: "2-Year", securityTerm: "2-Year" },
    { ...base, cusip: "OUTSIDE", auctionDate: "2026-01-01", term: "2-Year", securityTerm: "2-Year" },
  ];
  const range = { from: "2025-01-01", to: "2025-12-31" };
  assert.deepEqual(filterAuctionsByDateRange(rows, range).map(row => row.cusip), ["FROM", "MIDDLE", "OTHER", "TO"]);
  assert.deepEqual(filterResultRows(rows, "note-2", range.from, range.to).map(row => row.cusip), ["FROM", "MIDDLE", "TO"]);
  assert.deepEqual(filterResultRows(rows, "note-3", range.from, range.to), []);
});

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

test("필터는 명목 중·장기채를 만기별로 구분하고 FRN·TIPS를 섞지 않음", () => {
  assert.deepEqual(auctionFilters.map(filter => filter.label), ["전체", "단기채", "2년", "3년", "5년", "7년", "10년", "20년", "30년", "물가연동채", "변동금리채"]);
  const rows = [
    { ...base, cusip: "NOTE2", term: "2-Year", securityTerm: "2-Year" },
    { ...base, cusip: "NOTE3", term: "3-Year", securityTerm: "3-Year" },
    { ...base, cusip: "NOTE10", term: "9-Year 10-Month", securityTerm: "10-Year" },
    { ...base, cusip: "FRN2", type: "FRN", term: "2-Year", securityTerm: "2-Year" },
    { ...base, cusip: "BOND20", type: "Bond", term: "20-Year", securityTerm: "20-Year" },
    { ...base, cusip: "BOND30", type: "Bond", term: "30-Year", securityTerm: "30-Year" },
    { ...base, cusip: "TIPS10", type: "TIPS", term: "10-Year", securityTerm: "10-Year" },
    { ...base, cusip: "TIPS20", type: "TIPS", term: "20-Year", securityTerm: "20-Year" },
    { ...base, cusip: "TIPS30", type: "TIPS", term: "30-Year", securityTerm: "30-Year" },
  ];

  assert.deepEqual(filterAuctionRows(rows, "note-2").map(row => row.cusip), ["NOTE2"]);
  assert.deepEqual(filterAuctionRows(rows, "note-10").map(row => row.cusip), ["NOTE10"]);
  assert.deepEqual(filterAuctionRows(rows, "bond-20").map(row => row.cusip), ["BOND20"]);
  assert.deepEqual(filterAuctionRows(rows, "bond-30").map(row => row.cusip), ["BOND30"]);
  assert.deepEqual(filterAuctionRows(rows, "tips").map(row => row.cusip), ["TIPS10", "TIPS20", "TIPS30"]);
  assert.deepEqual(filterAuctionRows(rows, "frn").map(row => row.cusip), ["FRN2"]);
  assert.equal(matchesAuctionFilter(rows[2], "note-10"), true); // securityTerm 대체 경로
  assert.deepEqual(filterAuctionRows(rows, "note-5"), []);
});

test("결과·예정 표는 같은 필터 판별을 사용하고 필터 변경 시 선택을 초기화", async () => {
  const source = await readFile(new URL("../app/AuctionDashboard.tsx", import.meta.url), "utf8");
  assert.match(source, /filterResultRows\(results, filter, initialFrom, initialTo\)/);
  assert.match(source, /filterAuctionRows\(planned, filter\)/);
  assert.match(source, /const changeFilter = \(next: AuctionFilterId\) => \{[\s\S]*?setFilter\(next\);[\s\S]*?setSelectedKey\(""\);[\s\S]*?searchParams\.set\("filter", next\);[\s\S]*?history\.replaceState/);
  assert.match(source, /filtered\.find\(row => rowKey\(row\) === selectedKey\) \?\? filtered\[0\]/);
  assert.doesNotMatch(source, /setTab\(next\); setFilter\("all"\)/);

  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  assert.match(html, /role="group" aria-label="국채 종류 및 명목 중·장기채 만기 필터"/);
  assert.match(html, />2년<\/button>/);
  assert.match(html, />30년<\/button>/);
  assert.doesNotMatch(html, />중기채<\/button>|>장기채<\/button>/);
});

test("결과 기간 UI는 접근 가능한 두 캘린더·조회·초기화와 공유 가능한 URL을 제공", async () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  assert.match(html, /<label for="auction-result-from"><span>From<\/span>/);
  assert.match(html, /<input id="auction-result-from"[^>]*type="date"[^>]*value="2024-08-21"/);
  assert.match(html, /<label for="auction-result-to"><span>To<\/span>/);
  assert.match(html, /<input id="auction-result-to"[^>]*type="date"[^>]*value="2026-08-21"/);
  assert.match(html, />조회<\/button><button type="button" class="date-range-reset">최근 2년<\/button>/);
  assert.match(html, /2024-08-21 ~ 2026-08-21 · 1건/);
  assert.match(html, /<div class="section-heading results-heading"><h2 class="panel-heading">최근 입찰 결과<\/h2><form class="date-range-form"/);
  assert.doesNotMatch(html, /최근 입찰 결과<\/h2><\/div><form class="date-range-form"/);

  const source = await readFile(new URL("../app/AuctionDashboard.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.match(source, /url\.searchParams\.set\("from", from\)/);
  assert.match(source, /url\.searchParams\.set\("to", to\)/);
  assert.match(source, /url\.searchParams\.set\("filter", filter\)/);
  assert.match(source, /window\.location\.assign\(url\.toString\(\)\)/);
  assert.match(source, /role="alert"/);
  assert.match(css, /\.results-heading \{[^}]*flex-wrap: nowrap/);
  assert.match(css, /\.date-range-form \{[^}]*flex-wrap: nowrap/);
  assert.match(css, /@media \(max-width: 600px\)[\s\S]*?\.date-range-form \{[^}]*flex-wrap: wrap/);
});

test("URL에서 복원한 note-10은 날짜 범위와 AND로 적용되고 0건이면 KPI가 남지 않음", () => {
  const note2 = { ...base, cusip: "NOTE2", auctionDate: "2026-08-21", term: "2-Year", securityTerm: "2-Year" };
  const filteredHtml = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [note2, base], initialFilter: "note-10" }));
  assert.match(filteredHtml, /class="selected" aria-pressed="true">10년<\/button>/);
  assert.match(filteredHtml, /2024-08-21 ~ 2026-08-21 · 1건/);
  assert.doesNotMatch(filteredHtml, /NOTE2/);

  const emptyHtml = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [note2], initialFilter: "note-10" }));
  assert.match(emptyHtml, /결과 없음/);
  assert.match(visibleText(emptyHtml), /응찰률 \(%\) N\/A/);
});

test("0건 결과는 적용 기간을 표시하고 예정 일정에는 날짜 필터를 적용하지 않음", () => {
  const outside = { ...base, auctionDate: "2023-12-31" };
  const upcoming = { ...base, auctionDate: "2026-08-25" };
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [outside], upcoming: [upcoming] }));
  assert.match(html, /결과 없음 · 2024-08-21 ~ 2026-08-21 기간과 조건에 맞는 입찰 결과가 없습니다/);
  assert.match(html, /예정 1건/);
  assert.match(html, /2026-08-26 02:00 · 한국 KST/);
});

test("페이지는 URL 기간을 서버 조회에 전달하고 API는 롤링 워밍업과 고정 예정 범위를 사용", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const treasury = await readFile(new URL("../lib/treasury.ts", import.meta.url), "utf8");
  assert.match(page, /const parameters = await searchParams/);
  assert.match(page, /resolveAuctionDateRange\(parameters, today\)/);
  assert.match(page, /resolveAuctionFilter\(parameters\?\.filter\)/);
  assert.match(page, /initialFilter=\{initialFilter\}/);
  assert.match(page, /getTreasuryData\(resultRange\)/);
  assert.match(treasury, /shiftCalendarMonths\(visibleRange\.from, -25\)/);
  assert.match(treasury, /row\.auctionDate <= upcomingTo/);
});

test("응찰률 차트 좌표·축도 % 단위이며 누락값을 0으로 만들지 않음", () => {
  const html = renderToStaticMarkup(React.createElement(Dashboard, props));
  assert.match(html, /aria-label="응찰률 \(%\) 차트/);
  const chart = html.match(/<svg[^>]+aria-label="응찰률 \(%\) 차트[^>]*>[\s\S]*?<\/svg>/)?.[0];
  assert.ok(chart);
  assert.match(chart, /248\.0%/);
  assert.doesNotMatch(chart, /2\.48/);
  assert.doesNotMatch(html, /\d+(?:\.\d+)?\s+times|NaN|Infinity/);
  const missing = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [{ ...base, bidToCover: null }] }));
  assert.match(missing, /N\/A/);
  assert.doesNotMatch(visibleText(missing), /248\.0%|NaN|Infinity/);
});

test("배정·응찰률 차트는 선택 입찰과 동일한 종류·만기만 비교하고 롤링 기준 범례를 표시", () => {
  const sameTerm = [
    base,
    { ...base, auctionDate: "2026-07-20", bidToCover: 2.36 },
    { ...base, auctionDate: "2026-06-20", bidToCover: null },
    { ...base, auctionDate: "2026-05-20", bidToCover: 2.6 },
    { ...base, auctionDate: "2026-04-20", bidToCover: 2.4 },
    { ...base, auctionDate: "2026-03-20", bidToCover: 2.2 },
    { ...base, auctionDate: "2026-02-20", bidToCover: 2.5 },
  ];
  const sameDateOtherAuction = { ...base, cusip: "TEST00002", bidToCover: 9 };
  const unrelatedTerm = { ...base, auctionDate: "2026-08-19", term: "2-Year", securityTerm: "2-Year", bidToCover: 9 };
  const unrelatedType = { ...base, auctionDate: "2026-08-18", type: "Bond", term: "10-Year", securityTerm: "10-Year", bidToCover: 8 };
  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [base, sameDateOtherAuction, unrelatedTerm, unrelatedType, ...sameTerm.slice(1)] }));
  const allocation = html.match(/<svg[^>]+aria-label="참여자별 낙찰 비중[^>]*>[\s\S]*?<\/svg>/)?.[0];
  const subscriptionChart = html.match(/<svg[^>]+aria-label="응찰률 \(%\) 차트[^>]*>[\s\S]*?<\/svg>/)?.[0];
  assert.ok(allocation);
  assert.ok(subscriptionChart);
  assert.match(allocation, /10년 중기채/);
  assert.doesNotMatch(allocation, /2년 중기채|10년 장기채/);
  assert.match(subscriptionChart, /10년 중기채/);
  assert.doesNotMatch(subscriptionChart, /2년 중기채|10년 장기채|900\.0%|800\.0%/);
  assert.match(subscriptionChart, /개별 입찰값, 24개월 평균과 ±1σ, 최근 6회 평균/);
  assert.doesNotMatch(subscriptionChart, /<polyline[^>]+stroke="#ff5268"/);
  for (const label of ["개별 입찰값", "24개월 평균", "24개월 평균 ±1σ", "최근 6회 평균"]) assert.ok(html.includes(label), label);
});

test("응찰률 롤링 계산은 날짜순·시리즈별로 독립적이며 미래값과 결측값을 사용하지 않음", () => {
  const month = (year, index) => `${year + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}-15`;
  const noteRows = Array.from({ length: 26 }, (_, index) => ({
    ...base,
    cusip: `NOTE${index}`,
    auctionDate: month(2024, index),
    bidToCover: index === 7 ? null : 2 + index / 100,
  }));
  const unrelated = Array.from({ length: 26 }, (_, index) => ({
    ...base,
    cusip: `BILL${index}`,
    type: "Bill",
    term: "4-Week",
    auctionDate: month(2024, index),
    bidToCover: 9,
  }));
  const series = subscriptionRollingSeries([[...unrelated].reverse(), [...noteRows].reverse()].flat());
  const notes = series.filter(point => point.row.type === "Note");
  const bills = series.filter(point => point.row.type === "Bill");

  assert.equal(notes[4].average6, null);
  assert.equal(notes[6].average6, 203.5); // 결측 관측치는 제외하고 최근 유효 6회를 사용
  assert.equal(notes[22].average24Months, null);
  const expectedWindow = Array.from({ length: 24 }, (_, index) => index + 1)
    .filter(index => index !== 7)
    .map(index => 200 + index);
  const expectedMean = expectedWindow.reduce((sum, value) => sum + value, 0) / expectedWindow.length;
  const expectedSigma = Math.sqrt(expectedWindow.reduce((sum, value) => sum + (value - expectedMean) ** 2, 0) / expectedWindow.length);
  assert.ok(Math.abs(notes[23].average24Months - expectedMean) < 1e-9);
  assert.ok(Math.abs(notes[23].lower24Months - (expectedMean - expectedSigma)) < 1e-9);
  assert.ok(Math.abs(notes[23].upper24Months - (expectedMean + expectedSigma)) < 1e-9);
  assert.equal(bills[24].average24Months, 900);
  assert.equal(notes[23].row.auctionDate, "2026-01-15");

  const html = renderToStaticMarkup(React.createElement(Dashboard, { ...props, results: [...noteRows].reverse() }));
  const chart = html.match(/<svg[^>]+aria-label="응찰률 \(%\) 차트[^>]*>[\s\S]*?<\/svg>/)?.[0];
  assert.ok(chart);
  assert.match(chart, /class="subscription-band"/);
  assert.match(chart, /class="subscription-average-24"/);
  assert.match(chart, /class="subscription-average-6"/);
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
