"use client";

import { useMemo, useRef, useState } from "react";
import type { TreasuryAuction } from "../lib/treasury";
import { defaultAuctionDateRange, filterAuctionsByDateRange, validateAuctionDateRange } from "../lib/auction-date-range";
import { resolveAuctionFilter, type AuctionFilterId } from "../lib/auction-filter";
import { average, awardMix, percent, percentagePointChange, priorResult, securityName, signedPoints, stopName, subscription, subscriptionPercent } from "../lib/auction-display";
import { auctionDateTime, dateOnly, displayInstant, scheduleRows, zoneLabel, type DisplayZone } from "../lib/auction-time";
import { AllocationChart, AuctionLineChart, SubscriptionChart } from "./AuctionCharts";
import AuctionReference from "./AuctionReference";

type Props = {
  upcoming: TreasuryAuction[];
  results: TreasuryAuction[];
  source: "fiscal-api" | "unavailable";
  updatedAt: string;
  sourceUrl?: string;
  sourceRange?: string;
  sourceError?: string;
  initialZone?: DisplayZone;
  initialFilter?: AuctionFilterId;
  resultFrom?: string;
  resultTo?: string;
  defaultResultFrom?: string;
  defaultResultTo?: string;
};
type View = "market" | "api" | "database";
type Tab = "calendar" | "results";
const rowKey = (row: TreasuryAuction) => `${row.cusip}-${row.auctionDate}`;
const money = (value: number | null | undefined) => value == null ? "N/A" : `$${(value / 1e9).toFixed(1)}B`;
const price = (value: number | null | undefined) => value == null ? "N/A" : value.toFixed(4);
type AuctionFilterDefinition = {
  id: string;
  label: string;
  type?: TreasuryAuction["type"];
  term?: string;
};
export const auctionFilters = [
  { id: "all", label: "전체" },
  { id: "bill", label: "단기채", type: "Bill" },
  { id: "note-2", label: "2년", type: "Note", term: "2-Year" },
  { id: "note-3", label: "3년", type: "Note", term: "3-Year" },
  { id: "note-5", label: "5년", type: "Note", term: "5-Year" },
  { id: "note-7", label: "7년", type: "Note", term: "7-Year" },
  { id: "note-10", label: "10년", type: "Note", term: "10-Year" },
  { id: "bond-20", label: "20년", type: "Bond", term: "20-Year" },
  { id: "bond-30", label: "30년", type: "Bond", term: "30-Year" },
  { id: "tips", label: "물가연동채", type: "TIPS" },
  { id: "frn", label: "변동금리채", type: "FRN" },
] as const satisfies readonly AuctionFilterDefinition[];
export function matchesAuctionFilter(row: TreasuryAuction, filterId: AuctionFilterId): boolean {
  const definition: AuctionFilterDefinition | undefined = auctionFilters.find(filter => filter.id === filterId);
  if (!definition) return false;
  if (!definition.type) return true;
  if (row.type !== definition.type) return false;
  return !definition.term || row.term === definition.term || row.securityTerm === definition.term;
}

export const filterAuctionRows = (rows: TreasuryAuction[], filterId: AuctionFilterId) => rows.filter(row => matchesAuctionFilter(row, filterId));

export const filterResultRows = (rows: TreasuryAuction[], filterId: AuctionFilterId, from: string, to: string) =>
  filterAuctionRows(filterAuctionsByDateRange(rows, { from, to }), filterId);

function AuctionDate({ row, zone, withTime = false }: { row: TreasuryAuction | undefined; zone: DisplayZone; withTime?: boolean }) {
  const value = auctionDateTime(row, zone);
  return <span className="date-cell"><span>{value.date}</span><small>{withTime ? `${value.time} · ` : ""}{value.basis}</small></span>;
}
function CalendarDate({ value }: { value: string | undefined }) {
  return <span className="date-cell"><span>{dateOnly(value)}</span><small>원문 ET · 시각 없음</small></span>;
}

export default function AuctionDashboard({ upcoming, results, source, updatedAt, sourceUrl, sourceRange, sourceError, initialZone = "KST", initialFilter = "all", resultFrom, resultTo, defaultResultFrom, defaultResultTo }: Props) {
  const fallbackRange = defaultAuctionDateRange();
  const initialFrom = resultFrom ?? fallbackRange.from;
  const initialTo = resultTo ?? fallbackRange.to;
  const resetFrom = defaultResultFrom ?? fallbackRange.from;
  const resetTo = defaultResultTo ?? fallbackRange.to;
  const [view, setView] = useState<View>("market");
  const [tab, setTab] = useState<Tab>("results");
  const [zone, setZone] = useState<DisplayZone>(initialZone);
  const [filter, setFilter] = useState<AuctionFilterId>(() => resolveAuctionFilter(initialFilter));
  const [selectedKey, setSelectedKey] = useState("");
  const [fromInput, setFromInput] = useState(initialFrom);
  const [toInput, setToInput] = useState(initialTo);
  const [rangeError, setRangeError] = useState("");
  const resultRef = useRef<HTMLElement>(null);
  const calendarRef = useRef<HTMLElement>(null);
  const planned = useMemo(() => scheduleRows(upcoming, updatedAt), [upcoming, updatedAt]);
  const resultRows = useMemo(() => filterResultRows(results, filter, initialFrom, initialTo), [results, filter, initialFrom, initialTo]);
  const calendarRows = planned;
  const filtered = tab === "calendar" ? calendarRows : resultRows;
  const selectedRow = filtered.find(row => rowKey(row) === selectedKey) ?? filtered[0];
  const selectedResult = tab === "results" ? selectedRow : priorResult(selectedRow, results);
  const previous = priorResult(selectedResult, results);
  const mix = awardMix(selectedResult);
  const previousMix = awardMix(previous);
  const sameTermRows = selectedResult ? results.filter(row => row.type === selectedResult.type && row.term === selectedResult.term && (row.auctionDate < selectedResult.auctionDate || rowKey(row) === rowKey(selectedResult)))
    .sort((a, b) => b.auctionDate.localeCompare(a.auctionDate)) : [];
  const historicalRows = sameTermRows.filter(row => row.auctionDate < selectedResult!.auctionDate).slice(0, 6);
  const validPrevious = historicalRows.map(row => subscriptionPercent(row.bidToCover)).filter((value): value is number => value != null);
  const avgSubscription = average(validPrevious);
  const subscriptionDelta = percentagePointChange(subscriptionPercent(selectedResult?.bidToCover), avgSubscription);
  const comparisonRows = sameTermRows.slice(0, 9).reverse();
  const subscriptionRows = [...sameTermRows].reverse();
  const stopRows = selectedResult ? [selectedResult, ...historicalRows].reverse() : [];
  const nextBill = planned.find(row => row.type === "Bill");
  const stamp = displayInstant(updatedAt, zone);
  const selectedTime = auctionDateTime(selectedRow, zone);
  const changeTab = (next: Tab) => {
    setView("market"); setTab(next); setSelectedKey("");
    (next === "calendar" ? calendarRef : resultRef).current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const changeFilter = (next: AuctionFilterId) => {
    setFilter(next);
    setSelectedKey("");
    const url = new URL(window.location.href);
    url.searchParams.set("filter", next);
    window.history.replaceState(window.history.state, "", url.toString());
  };
  const select = (row: TreasuryAuction, next: Tab) => { setView("market"); setTab(next); setSelectedKey(rowKey(row)); };
  const selectResult = (row: TreasuryAuction) => select(row, "results");
  const navigateToRange = (from: string, to: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("from", from);
    url.searchParams.set("to", to);
    url.searchParams.set("filter", filter);
    window.location.assign(url.toString());
  };
  const applyDateRange = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateAuctionDateRange(fromInput, toInput);
    if (error) { setRangeError(error); return; }
    setRangeError("");
    setSelectedKey("");
    navigateToRange(fromInput, toInput);
  };
  const resetDateRange = () => {
    setFromInput(resetFrom);
    setToInput(resetTo);
    setRangeError("");
    setSelectedKey("");
    navigateToRange(resetFrom, resetTo);
  };

  return <div className="terminal-shell" data-theme="dark">
    <header className="topbar">
      <button className="brand" onClick={() => { setView("market"); setTab("results"); setSelectedKey(""); }} aria-label="UST AUCTION 처음으로"><span className="bank" aria-hidden="true" /><span>UST AUCTION</span></button>
      <nav className="nav" aria-label="주요 메뉴">
        <button className={view === "market" && tab === "calendar" ? "active" : ""} aria-pressed={view === "market" && tab === "calendar"} onClick={() => changeTab("calendar")}>입찰 일정</button>
        <button className={view === "market" && tab === "results" ? "active" : ""} aria-pressed={view === "market" && tab === "results"} onClick={() => changeTab("results")}>입찰 결과</button>
        <button className={view === "api" ? "active" : ""} aria-pressed={view === "api"} onClick={() => setView("api")}>API 필드</button>
        <button className={view === "database" ? "active" : ""} aria-pressed={view === "database"} onClick={() => setView("database")}>데이터 구조</button>
      </nav>
      <div className="top-right"><div className="zone-switch" role="group" aria-label="날짜·시간 기준 선택">
        <button aria-pressed={zone === "KST"} className={zone === "KST" ? "selected" : ""} onClick={() => setZone("KST")}>한국 (KST)</button>
        <button aria-pressed={zone === "ET"} className={zone === "ET" ? "selected" : ""} onClick={() => setZone("ET")}>미국 동부 (ET)</button>
      </div><span className={`source-badge ${source}`}>{source === "fiscal-api" ? "공식 API 수신" : "수신 실패"}</span></div>
    </header>
    <div className="time-strip" aria-live="polite"><span>표시 기준: <b>{zoneLabel(zone)}</b> · 날짜 형식 YYYY-MM-DD</span><span>자료 기준: <b>{stamp.full}</b></span></div>
    <div className={`data-status ${source}`} role="status">
      {source === "fiscal-api"
        ? `미국 재무부 Fiscal Data 공식 API 자료입니다. 조회 범위: ${sourceRange ?? "확인 불가"}.`
        : `공식 API 수신에 실패했습니다. 표본값으로 대체하지 않습니다.${sourceError ? ` 원인: ${sourceError}` : ""}`}
      <span>N/A = 자료 없음 · 시각 없는 날짜는 원문 ET 유지</span>
    </div>

    {view === "market" ? <main className="dashboard">
      <aside className="left-rail">
        <section className="panel latest-panel">
          <header className="side-title"><h2 className="panel-heading">{tab === "results" && selectedRow === results[0] ? "최근 입찰" : "선택 입찰"}</h2><span className="released">{tab === "results" ? "결과" : "예정"}</span></header>
          <div className="latest-body">
            <div className="security-row"><h1>{securityName(selectedRow)}</h1>{selectedRow?.reopening && <span className="reopening">재발행</span>}</div>
            <div className="side-rule" />
            <dl className="facts">
              <div><dt>입찰일</dt><dd><AuctionDate row={selectedRow} zone={zone} /></dd></div>
              <div><dt>입찰시각</dt><dd>{selectedTime.time}<small className="basis-note">{selectedTime.basis}</small></dd></div>
              <div><dt>결제일</dt><dd><CalendarDate value={selectedRow?.issueDate} /></dd></div>
              <div><dt>발행금액</dt><dd>{money(selectedRow?.offeringAmount)}</dd></div>
              <div><dt>쿠폰금리</dt><dd>{percent(selectedRow?.couponRate, 3)}</dd></div>
              <div><dt>만기일</dt><dd><CalendarDate value={selectedRow?.maturityDate} /></dd></div>
            </dl>
            <div className="side-rule" /><p className="subtle">표나 차트에서 입찰을 선택하면 주요 결과가 바뀝니다.</p>
          </div>
        </section>
        <section className="panel quick">
          <h2 className="panel-heading">일정 한눈에 보기</h2>
          <div className="quick-item"><i className="quick-icon green" aria-hidden="true" /><div><small>다음 예정 입찰</small><b>{securityName(planned[0])}</b></div></div>
          {planned[0] && <p className="quick-date">{auctionDateTime(planned[0], zone).full}</p>}
          <div className="quick-item"><i className="quick-icon pink" aria-hidden="true" /><div><small>다음 단기채 입찰</small><b>{nextBill ? securityName(nextBill) : "자료 없음"}</b></div></div>
          {nextBill && <p className="quick-date">{auctionDateTime(nextBill, zone).full}</p>}
          <div className="quick-item"><small>표시 예정 물량 합계</small><b>{money(planned.reduce((sum, row) => sum + (row.offeringAmount ?? 0), 0))}</b></div>
          <div className="quick-item"><small>조회기간 표시 결과</small><b>{resultRows.length}건</b></div>
          <button className="calendar-btn" onClick={() => changeTab("calendar")}>예정 일정 보기 <span aria-hidden="true">→</span></button>
        </section>
      </aside>

      <section className="main-area" aria-label="입찰 대시보드">
        <section className="panel key-results">
          <div className="section-heading"><h2 className="panel-heading underlined">주요 입찰 결과</h2><span>{tab === "calendar" ? "직전 비교 결과: " : "선택 결과: "}{securityName(selectedResult)}{selectedResult ? ` · ${auctionDateTime(selectedResult, zone).full}` : ""}</span></div>
          <div className="kpis">
            <article className="kpi subscription-kpi"><h3>응찰률 (%)</h3><strong className="kpi-value green-text">{subscription(selectedResult?.bidToCover)}</strong><div className="kpi-bottom"><div><small>직전 평균 · 유효 {validPrevious.length}/{historicalRows.length}건</small><b>{percent(avgSubscription)}</b></div><div><small>평균 대비</small><b>{signedPoints(subscriptionDelta)}</b></div></div></article>
            <article className="kpi stop-kpi"><h3>{stopName(selectedResult)}</h3><strong className="kpi-value">{percent(selectedResult?.stopRate, 3)}</strong></article>
            {["간접낙찰률", "직접낙찰률", "PD낙찰률"].map((label, index) => {
              const difference = percentagePointChange(mix?.[index], previousMix?.[index]);
              return <article className="kpi bidder-kpi" key={label}><h3>{label}</h3><strong className="kpi-value green-text">{percent(mix?.[index])}</strong><div className="kpi-bottom"><div><small>직전 입찰 대비</small><b className={difference == null ? "subtle" : difference > 0 ? "green-text" : difference < 0 ? "red-text" : ""}>{signedPoints(difference)}</b></div></div></article>;
            })}
            <article className="kpi"><h3>Allotted at High</h3><strong className={`kpi-value ${selectedResult?.allottedAtHigh == null ? "unavailable" : ""}`}>{percent(selectedResult?.allottedAtHigh)}</strong><div className="kpi-bottom"><div><small>최고 낙찰금리 배정률</small><b>{selectedResult?.allottedAtHigh == null ? "원천 자료 없음" : "Fiscal Data 공식값"}</b></div></div></article>
          </div>
          <p className="comparison-note">낙찰률: 전체 낙찰액 대비 비중 · 증감: 동일 종류·만기의 직전 입찰 대비 %p{previous ? ` · 비교 입찰: ${auctionDateTime(previous, zone).full}` : " · 비교 자료 없음"}</p>
        </section>
        <section className="panel charts" aria-label="입찰 차트">
          <article className="chart-cell"><h2 className="panel-heading">낙찰 금리</h2><p className="chart-subtitle">{securityName(selectedResult)} · 동일 종류·만기 {stopRows.length}건</p><AuctionLineChart rows={stopRows} kind="stop" onSelect={selectResult} zone={zone} /><div className="legend"><span><i className="swatch blue" />{stopName(selectedResult)}</span></div></article>
          <article className="chart-cell"><h2 className="panel-heading">참여자별 낙찰 비중 (%)</h2><p className="chart-subtitle">{securityName(selectedResult)} · 동일 종류·만기 {comparisonRows.length}건 · 전체 낙찰액 기준</p><AllocationChart rows={comparisonRows} onSelect={selectResult} zone={zone} /><div className="legend"><span><i className="swatch green" />간접</span><span><i className="swatch blue" />직접</span><span><i className="swatch purple" />PD</span><span><i className="swatch gray" />기타</span></div></article>
          <article className="chart-cell"><h2 className="panel-heading">응찰률 (%)</h2><p className="chart-subtitle">{securityName(selectedResult)} · 동일 종류·만기 {subscriptionRows.length}건 · 장기 기준과 최근 흐름</p><SubscriptionChart rows={subscriptionRows} onSelect={selectResult} zone={zone} /><div className="legend"><span><i className="legend-dot" />개별 입찰값</span><span><i className="legend-line baseline" />24개월 평균</span><span><i className="swatch sigma-band" />24개월 평균 ±1σ</span><span><i className="legend-line current" />최근 6회 평균</span></div></article>
        </section>

        <div className="list-controls"><span>결과 입찰 종류</span><div className="filter-row" role="group" aria-label="국채 종류 및 명목 중·장기채 만기 필터">{auctionFilters.map(option => <button key={option.id} className={filter === option.id ? "selected" : ""} aria-pressed={filter === option.id} onClick={() => changeFilter(option.id)}>{option.label}</button>)}</div></div>
        <section className="bottom-row">
          <div className="auction-lists">
            <section className="panel results-panel" id="auction-results" ref={resultRef}>
              <div className="section-heading results-heading">
                <h2 className="panel-heading">최근 입찰 결과</h2>
                <form className="date-range-form" onSubmit={applyDateRange} noValidate>
                  <label htmlFor="auction-result-from"><span>From</span><input id="auction-result-from" name="from" type="date" value={fromInput} onChange={event => setFromInput(event.target.value)} /></label>
                  <label htmlFor="auction-result-to"><span>To</span><input id="auction-result-to" name="to" type="date" value={toInput} onChange={event => setToInput(event.target.value)} /></label>
                  <div className="date-range-actions"><button type="submit" className="date-range-submit">조회</button><button type="button" className="date-range-reset" onClick={resetDateRange}>최근 2년</button></div>
                  {rangeError && <p className="date-range-error" role="alert">{rangeError}</p>}
                </form>
              </div>
              {/* 키보드로 긴 표를 스크롤할 수 있게 하는 포커스 영역입니다. */}
              {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
              <div className="table-wrap" tabIndex={0} role="region" aria-label="최근 입찰 결과표"><table>
                <thead><tr><th>입찰일 · 기준</th><th>만기 / 종류</th><th>발행금액</th><th>낙찰금리 (%)</th><th>응찰률 (%)</th><th>배정률 (%)</th><th>간접 (%)</th><th>직접 (%)</th><th>PD (%)</th><th>낙찰가격 ($100)</th></tr></thead>
                <tbody>{resultRows.map(row => {
                  const allocation = awardMix(row);
                  const selected = tab === "results" && selectedRow && rowKey(selectedRow) === rowKey(row);
                  return <tr key={rowKey(row)} className={selected ? "row-selected" : ""} onClick={() => select(row, "results")}>
                    <td><button className="row-select" aria-label={`${auctionDateTime(row, zone).full} ${securityName(row)} 결과 선택`} aria-pressed={!!selected} onClick={() => select(row, "results")} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(row, "results"); } }}><AuctionDate row={row} zone={zone} /></button></td>
                    <td>{securityName(row)} {row.reopening && <span className="reopen-badge">재발행</span>}</td><td>{money(row.offeringAmount)}</td>
                    <td title={stopName(row)}>{percent(row.stopRate, 3)}</td><td className="subscription-cell">{subscription(row.bidToCover)}</td><td className={row.allottedAtHigh == null ? "unavailable" : ""}>{percent(row.allottedAtHigh)}</td>
                    <td>{percent(allocation?.[0])}</td><td>{percent(allocation?.[1])}</td><td>{percent(allocation?.[2])}</td><td>{price(row.pricePer100)}</td>
                  </tr>;
                })}{!resultRows.length && <tr><td colSpan={10} className="empty-state">결과 없음 · {initialFrom} ~ {initialTo} 기간과 조건에 맞는 입찰 결과가 없습니다.</td></tr>}</tbody>
              </table></div><div className="table-foot"><span>{initialFrom} ~ {initialTo} · {resultRows.length}건</span><span>{zoneLabel(zone)} · 시각 없는 자료는 원문 ET · 금액 USD · $B = 십억 달러</span></div>
            </section>
            <section className="panel schedule-panel" id="auction-calendar" ref={calendarRef}>
              <div className="section-heading"><h2 className="panel-heading">예정 입찰 일정</h2><span>{source === "fiscal-api" ? "자료 기준 시각 이후 예정" : "공식 API 수신 실패"}</span></div>
              <p className="schedule-note">기준 시각: {stamp.full} · {source === "fiscal-api" ? "발표되어 수신된 일정만 표시하며, 아직 공고되지 않은 계획은 포함하지 않습니다." : "표본 일정으로 대체하지 않았습니다."}</p>
              {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
              <div className="table-wrap" tabIndex={0} role="region" aria-label="예정 입찰 일정표"><table>
                <thead><tr><th>예정 입찰일시 · 기준</th><th>만기 / 종류</th><th>발행 예정액</th><th>결제일 (원문 ET)</th><th>직전 낙찰금리</th><th>직전 응찰률 (%)</th></tr></thead>
                <tbody>{calendarRows.map(row => {
                  const prior = priorResult(row, results);
                  const selected = tab === "calendar" && selectedRow && rowKey(selectedRow) === rowKey(row);
                  return <tr key={rowKey(row)} className={selected ? "row-selected" : ""} onClick={() => select(row, "calendar")}>
                    <td><button className="row-select" aria-label={`${auctionDateTime(row, zone).full} ${securityName(row)} 일정 선택`} aria-pressed={!!selected} onClick={() => select(row, "calendar")} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(row, "calendar"); } }}><AuctionDate row={row} zone={zone} withTime /></button></td>
                    <td>{securityName(row)} {row.reopening && <span className="reopen-badge">재발행</span>}</td><td>{money(row.offeringAmount)}</td><td><CalendarDate value={row.issueDate} /></td><td>{percent(prior?.stopRate, 3)}</td><td>{subscription(prior?.bidToCover)}</td>
                  </tr>;
                })}{!calendarRows.length && <tr><td colSpan={6} className="empty-state">조건에 맞는 예정 일정이 없습니다. 미공고·미수신 계획은 표시하지 않습니다.</td></tr>}</tbody>
              </table></div><div className="table-foot"><span>예정 {calendarRows.length}건 · 결과표와 함께 표시</span><span>{zoneLabel(zone)}</span></div>
            </section>
          </div>
          <aside className="panel market"><h2 className="panel-heading">시장 동향</h2>{["10년물 금리", "2년물 금리", "30년물 금리"].map(label => <div className="market-card" key={label}><div><span>{label}</span><small>미연결</small></div><strong>N/A</strong><div className="market-placeholder" aria-hidden="true" /></div>)}<p className="market-asof">시장금리·기준 시각은 후속 단계에서 검증합니다. 입찰금리로 대체하지 않습니다.</p></aside>
        </section>
      </section>
    </main> : <AuctionReference view={view} />}
    <footer><span>출처: <a href={sourceUrl ?? "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/treasury-securities-auctions-data"} target="_blank" rel="noreferrer">미국 재무부 · Fiscal Data</a></span><span>금액 USD · 표시 시각 {zoneLabel(zone)}</span><span>화면 검토용 · 투자 판단용 아님</span></footer>
  </div>;
}
