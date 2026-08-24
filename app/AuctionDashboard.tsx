"use client";

import { useMemo, useState } from "react";
import type { TreasuryAuction } from "../lib/treasury";

type Props = {
  upcoming: TreasuryAuction[];
  results: TreasuryAuction[];
  source: "live" | "snapshot";
  updatedAt: string;
};
type View = "market" | "api" | "database";
type Tab = "calendar" | "results";

const rowKey = (row: TreasuryAuction) => `${row.cusip}-${row.auctionDate}`;
const compactMoney = (value: number | null) =>
  value == null ? "—" : `$${(value / 1e9).toFixed(value < 10e9 ? 1 : 0)}B`;
const share = (value: number | null, total: number | null) =>
  value != null && total ? Math.max(0, (value / total) * 100) : 0;
const dateParts = (iso: string) => {
  const d = new Date(iso);
  return {
    date: d.toLocaleDateString("en-US", { month: "short", day: "2-digit", timeZone: "UTC" }).toUpperCase(),
    day: d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }).toUpperCase(),
  };
};
const fullDate = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit", timeZone: "UTC" }) : "—";
const rate = (value: number | null) => (value == null ? "—" : `${value.toFixed(3)}%`);
const shortTerm = (term: string) => term.replace("-Year", "Y").replace("-Week", "W");

const extractionGroups = [
  {
    title: "Identity & instrument",
    tone: "blue",
    fields: [
      ["cusip", "Permanent security identifier"],
      ["type / securityType", "Bill, Note, Bond, TIPS or FRN"],
      ["term / securityTerm", "Auction tenor and issued tenor"],
      ["maturityDate", "Final maturity"],
      ["reopening / CMB", "Original issue and special bill flags"],
    ],
  },
  {
    title: "Calendar & terms",
    tone: "violet",
    fields: [
      ["announcementDate", "Terms become official"],
      ["auctionDate", "Competitive auction date"],
      ["issueDate", "Settlement and issue date"],
      ["closingTimeCompetitive", "Institutional bid deadline (ET)"],
      ["offeringAmount", "Headline public offering"],
    ],
  },
  {
    title: "Clearing result",
    tone: "mint",
    fields: [
      ["highYield / highDiscountRate", "Type-aware stop metric"],
      ["highInvestmentRate / spread", "Bill return or FRN spread"],
      ["pricePer100", "Uniform auction price"],
      ["bidToCoverRatio", "Primary demand signal"],
      ["allocationPercentage", "Proration at the stop"],
    ],
  },
  {
    title: "Demand composition",
    tone: "amber",
    fields: [
      ["competitiveTendered / Accepted", "Competitive demand and awards"],
      ["primaryDealer…", "Dealer bids and take-down"],
      ["directBidder…", "Direct bidder participation"],
      ["indirectBidder…", "Institutional and foreign proxy"],
      ["SOMA / FIMA / retail", "Official and noncompetitive awards"],
    ],
  },
];

const tableCards = [
  { name: "security_master", key: "cusip", copy: "Stable security reference data", cols: "type · original_term · maturity_date · tips · frn" },
  { name: "auction", key: "auction_id", copy: "One row per announced auction", cols: "cusip · auction_date · issue_date · offering_amount · status" },
  { name: "auction_result", key: "auction_id", copy: "One-to-one clearing outcome", cols: "stop_value · stop_metric · bid_to_cover · price_per_100" },
  { name: "bidder_allocation", key: "auction_id + bidder_type", copy: "Normalized bidder take-down", cols: "tendered_amount · accepted_amount · acceptance_rate" },
  { name: "source_snapshot", key: "snapshot_id", copy: "Immutable API lineage", cols: "endpoint · fetched_at · payload_hash · raw_payload" },
  { name: "auction_source_link", key: "auction_id + snapshot_id", copy: "Record-to-payload traceability", cols: "auction_id · snapshot_id" },
];

export default function AuctionDashboard({ upcoming, results, source, updatedAt }: Props) {
  const [view, setView] = useState<View>("market");
  const [tab, setTab] = useState<Tab>("calendar");
  const [filter, setFilter] = useState("All");
  const [selectedKey, setSelectedKey] = useState(upcoming[0] ? rowKey(upcoming[0]) : results[0] ? rowKey(results[0]) : "");

  const universe = tab === "calendar" ? upcoming : results;
  const filtered = useMemo(
    () => universe.filter((row) => filter === "All" || row.type === filter),
    [universe, filter],
  );
  const rows = filtered.slice(0, 11);
  const selectedRow = filtered.find((row) => rowKey(row) === selectedKey) ?? rows[0] ?? filtered[0];
  const comparableResult = (row: TreasuryAuction | undefined) =>
    row ? results.find((result) => result.type === row.type && result.term === row.term && result.auctionDate < row.auctionDate)
      ?? results.find((result) => result.type === row.type && result.term === row.term) : undefined;
  const selectedResult = tab === "results"
    ? results.find((row) => rowKey(row) === selectedKey) ?? results[0]
    : comparableResult(selectedRow) ?? results[0];

  const totalSupply = upcoming.reduce((sum, row) => sum + row.offeringAmount, 0);
  const coverValues = results.flatMap((row) => row.bidToCover == null ? [] : [row.bidToCover]);
  const avgCover = coverValues.length ? coverValues.reduce((sum, value) => sum + value, 0) / coverValues.length : 0;
  const latestIndirect = selectedResult ? share(selectedResult.indirectAccepted, selectedResult.totalAccepted) : 0;
  const otherShare = selectedResult
    ? Math.max(0, 100 - share(selectedResult.indirectAccepted, selectedResult.totalAccepted) - share(selectedResult.directAccepted, selectedResult.totalAccepted) - share(selectedResult.dealerAccepted, selectedResult.totalAccepted))
    : 0;

  const chartRows = (tab === "calendar" ? upcoming : results)
    .filter((row) => filter === "All" || row.type === filter)
    .slice(0, 9)
    .reverse();
  const chartValues = chartRows.map((row) => tab === "calendar" ? row.offeringAmount / 1e9 : row.bidToCover ?? 0);
  const chartMax = Math.max(tab === "calendar" ? 110 : 3.6, ...chartValues);
  const chartSummary = tab === "calendar"
    ? compactMoney(chartRows.reduce((sum, row) => sum + row.offeringAmount, 0))
    : `${(chartRows.reduce((sum, row) => sum + (row.bidToCover ?? 0), 0) / Math.max(1, chartRows.filter((row) => row.bidToCover != null).length)).toFixed(2)}×`;

  const stamp = new Date(updatedAt).toLocaleString("en-US", {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/New_York", timeZoneName: "short",
  });
  const nav = (next: View) => {
    setView(next);
    if (next === "market") setTab("calendar");
  };
  const changeTab = (next: Tab) => {
    setTab(next);
    const nextRows = next === "calendar" ? upcoming : results;
    if (nextRows[0]) setSelectedKey(rowKey(nextRows[0]));
  };

  return (
    <main className="terminal-shell">
      <aside className="rail" aria-label="Product navigation">
        <div className="brand-mark">FV</div>
        <button className={`rail-item ${view === "market" ? "active" : ""}`} onClick={() => nav("market")} aria-label="Auction monitor"><span>AU</span><small>Monitor</small></button>
        <button className={`rail-item ${view === "api" ? "active" : ""}`} onClick={() => nav("api")} aria-label="API field map"><span>AP</span><small>Fields</small></button>
        <button className={`rail-item ${view === "database" ? "active" : ""}`} onClick={() => nav("database")} aria-label="Database blueprint"><span>DB</span><small>Model</small></button>
        <span className="rail-spacer" />
        <a className="rail-item help" href="https://www.treasurydirect.gov/auctions/upcoming/" target="_blank" rel="noreferrer" aria-label="TreasuryDirect source"><span>TD</span><small>Source</small></a>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><div className="eyebrow">FIXED INCOME / PRIMARY MARKET</div><h1>{view === "market" ? "U.S. Treasury Auctions" : view === "api" ? "TreasuryDirect Field Map" : "Auction Data Blueprint"}</h1></div>
          <div className="top-actions"><span className={`live-dot ${source}`} /><b>{source === "live" ? "LIVE API" : "VERIFIED SNAPSHOT"}</b><span className="clock">{stamp}</span></div>
        </header>

        <div className="ticker" aria-label="Auction context strip">
          <span>NEXT <b>{upcoming[0] ? `${dateParts(upcoming[0].auctionDate).date} · ${upcoming[0].term}` : "—"}</b></span>
          <span>OFFERING <b>{compactMoney(upcoming[0]?.offeringAmount ?? null)}</b></span>
          <span>LATEST STOP <b>{selectedResult ? `${rate(selectedResult.stopRate)} · ${selectedResult.term}` : "—"}</b></span>
          <span>BID / COVER <b>{selectedResult?.bidToCover?.toFixed(2) ?? "—"}×</b></span>
          <span className="source-note">SOURCE · TREASURYDIRECT TA_WS</span>
        </div>

        {view === "market" && <div className="content">
          <section className="hero-row">
            <div><div className="section-kicker">AUCTION PULSE</div><h2>Primary supply, distilled.</h2><p className="hero-copy">Official terms beside the latest comparable clearing signal.</p></div>
            <div className="metric"><span>Next auction</span><strong>{upcoming[0] ? dateParts(upcoming[0].auctionDate).date : "—"}</strong><small>{upcoming[0]?.term} {upcoming[0]?.type}</small></div>
            <div className="metric"><span>Announced supply</span><strong>{compactMoney(totalSupply)}</strong><small>{upcoming.length} upcoming lines</small></div>
            <div className="metric"><span>Avg. bid / cover</span><strong>{avgCover.toFixed(2)}×</strong><small className="positive">Latest {coverValues.length} auctions</small></div>
          </section>

          <section className="dashboard-grid">
            <article className="panel schedule-panel">
              <div className="panel-head panel-head-wrap">
                <div><span className="section-kicker">AUCTION TAPE</span><h3>{tab === "calendar" ? "Forward calendar + prior result" : "Recent clearing results"}</h3></div>
                <div className="panel-controls">
                  <div className="segmented tabs" aria-label="Dataset"><button className={tab === "calendar" ? "selected" : ""} onClick={() => changeTab("calendar")}>Calendar <b>{upcoming.length}</b></button><button className={tab === "results" ? "selected" : ""} onClick={() => changeTab("results")}>Results <b>{results.length}</b></button></div>
                  <div className="filter-row" aria-label="Security filter">{["All", "Bill", "Note", "Bond", "TIPS", "FRN"].map((name) => <button key={name} className={filter === name ? "selected" : ""} onClick={() => setFilter(name)}>{name}</button>)}</div>
                </div>
              </div>
              <div className="table-wrap"><table><thead><tr>{tab === "calendar" ? <><th>Auction</th><th>Security</th><th>Offering</th><th>Comp. close</th><th>Settlement</th><th>Last comparable</th></> : <><th>Auction</th><th>Security</th><th>Stop</th><th>Bid / cover</th><th>Offering</th><th>Indirect</th></>}</tr></thead>
                <tbody>{rows.map((row) => {
                  const dp = dateParts(row.auctionDate);
                  const prior = comparableResult(row);
                  const indirect = share(row.indirectAccepted, row.totalAccepted);
                  return <tr key={rowKey(row)} className={selectedRow && rowKey(selectedRow) === rowKey(row) ? "row-selected" : ""} onClick={() => setSelectedKey(rowKey(row))}>
                    <td><b>{dp.date}</b><small>{dp.day}</small></td>
                    <td><div className="security-cell"><b>{row.term}</b><span className={`type-badge ${row.type.toLowerCase()}`}>{row.type}</span></div><small>{row.cusip}{row.reopening ? " · REOPEN" : ""}</small></td>
                    {tab === "calendar" ? <>
                      <td className="mono strong">{compactMoney(row.offeringAmount)}</td>
                      <td><b className="mono">{row.closingTimeCompetitive}</b><small>Eastern Time</small></td>
                      <td><b>{fullDate(row.issueDate)}</b><small>Matures {fullDate(row.maturityDate)}</small></td>
                      <td><b className="mono">{prior ? rate(prior.stopRate) : "—"}</b><small>{prior ? `${prior.stopLabel} · ${prior.bidToCover?.toFixed(2) ?? "—"}×` : "No comparable result"}</small></td>
                    </> : <>
                      <td><b className="mono">{rate(row.stopRate)}</b><small>{row.stopLabel}</small></td>
                      <td><b className="mono cover">{row.bidToCover?.toFixed(2)}×</b><small>{compactMoney(row.totalTendered)} tendered</small></td>
                      <td className="mono strong">{compactMoney(row.offeringAmount)}</td>
                      <td><b className="mono">{indirect.toFixed(1)}%</b><small>{compactMoney(row.indirectAccepted)} accepted</small></td>
                    </>}
                  </tr>;
                })}{!rows.length && <tr><td colSpan={6} className="empty-state">No {filter} auctions in this window.</td></tr>}</tbody>
              </table></div>
              <div className="table-foot"><span><i /> Select a row to update the context panels</span><span>Times ET · amounts USD · source TreasuryDirect</span></div>
            </article>

            <div className="right-stack">
              <article className="panel chart-panel">
                <div className="panel-head"><div><span className="section-kicker">{tab === "calendar" ? "SUPPLY PROFILE" : "DEMAND SIGNAL"}</span><h3>{tab === "calendar" ? "Upcoming offering size" : "Bid-to-cover trend"}</h3></div><span className="range">LATEST {chartRows.length}</span></div>
                <div className="chart-summary"><strong>{chartSummary}</strong><span>{tab === "calendar" ? "displayed supply" : "window average"}</span></div>
                <div className="bar-chart" aria-label={tab === "calendar" ? "Upcoming offering amount bar chart" : "Recent bid-to-cover bar chart"}>{chartRows.map((row, index) => {
                  const value = chartValues[index];
                  return <button className="bar-column" key={rowKey(row)} onClick={() => setSelectedKey(rowKey(row))} aria-label={`${row.term} ${tab === "calendar" ? compactMoney(row.offeringAmount) : `${row.bidToCover} times`}`}>
                    <span className="bar-value">{tab === "calendar" ? `$${Math.round(value)}B` : value.toFixed(2)}</span>
                    <div className={`bar ${selectedRow && rowKey(selectedRow) === rowKey(row) ? "focus" : ""}`} style={{ height: `${(value / chartMax) * 100}%` }} />
                    <small>{shortTerm(row.term)}</small>
                  </button>;
                })}</div>
              </article>

              {selectedResult && <article className="panel allocation-panel">
                <div className="panel-head"><div><span className="section-kicker">{tab === "calendar" ? "LAST COMPARABLE RESULT" : "SELECTED RESULT"}</span><h3>{selectedResult.term} {selectedResult.type}</h3></div><span className="cusip">{selectedResult.cusip}</span></div>
                <div className="allocation-hero"><div><span>{selectedResult.stopLabel}</span><strong>{rate(selectedResult.stopRate)}</strong></div><div><span>Bid / cover</span><strong>{selectedResult.bidToCover?.toFixed(2) ?? "—"}×</strong></div><div><span>Indirect</span><strong>{latestIndirect.toFixed(1)}%</strong></div></div>
                <div className="mix-label"><span>Award mix</span><b>{compactMoney(selectedResult.totalAccepted)} total accepted</b></div>
                <div className="mix-bar" aria-label="Accepted awards by bidder type"><span className="indirect" style={{ width: `${share(selectedResult.indirectAccepted, selectedResult.totalAccepted)}%` }} /><span className="direct" style={{ width: `${share(selectedResult.directAccepted, selectedResult.totalAccepted)}%` }} /><span className="dealer" style={{ width: `${share(selectedResult.dealerAccepted, selectedResult.totalAccepted)}%` }} /><span className="other" style={{ width: `${otherShare}%` }} /></div>
                <div className="legend"><span><i className="indirect" />Indirect <b>{share(selectedResult.indirectAccepted, selectedResult.totalAccepted).toFixed(1)}%</b></span><span><i className="direct" />Direct <b>{share(selectedResult.directAccepted, selectedResult.totalAccepted).toFixed(1)}%</b></span><span><i className="dealer" />Dealer <b>{share(selectedResult.dealerAccepted, selectedResult.totalAccepted).toFixed(1)}%</b></span><span><i className="other" />Other <b>{otherShare.toFixed(1)}%</b></span></div>
              </article>}
            </div>
          </section>
        </div>}

        {view === "api" && <div className="content reference-page">
          <section className="reference-hero"><div><span className="section-kicker">120 RAW FIELDS → COMPACT CORE MODEL</span><h2>Extract signal. Retain lineage.</h2><p>The two TreasuryDirect feeds share the same wide string-based schema. Announcement records leave outcome fields blank; result records populate them. The serving layer converts empty strings to NULL and chooses a security-aware stop metric.</p></div><div className="endpoint-stack"><code>GET /TA_WS/securities/announced?format=json</code><code>GET /TA_WS/securities/auctioned?format=json&amp;day=45</code></div></section>
          <div className="extraction-grid">{extractionGroups.map((group, groupIndex) => <article className={`field-card ${group.tone}`} key={group.title}><div className="field-card-head"><span>{String(groupIndex + 1).padStart(2, "0")}</span><h3>{group.title}</h3></div>{group.fields.map(([field, copy]) => <div className="field-row" key={field}><code>{field}</code><p>{copy}</p></div>)}</article>)}</div>
          <section className="logic-strip"><div><span>01</span><b>Parse</b><small>"" → NULL · money → DECIMAL(20,2) · market dates → DATE</small></div><div><span>02</span><b>Unify stop</b><small>Bill = highDiscountRate · coupon = highYield · FRN = highDiscountMargin</small></div><div><span>03</span><b>Match prior</b><small>Same security type + term, latest result before the auction date</small></div><div><span>04</span><b>Preserve</b><small>Raw JSON + SHA-256 payload hash retained for audit replay</small></div></section>
        </div>}

        {view === "database" && <div className="content reference-page">
          <section className="reference-hero database-hero"><div><span className="section-kicker">POSTGRESQL · IDEMPOTENT · AUDITABLE</span><h2>Normalized core, terminal-ready view.</h2><p>Stable instrument identity, auction events, one-to-one results and repeating bidder allocations are separated. Immutable source snapshots make every displayed value traceable to TreasuryDirect.</p></div><div className="db-stat"><span>Core tables</span><strong>6</strong><small>+ 2 serving views</small></div></section>
          <section className="pipeline" aria-label="Data processing flow"><div><span>INGEST</span><b>TreasuryDirect API</b><small>15-minute baseline poll</small></div><i>→</i><div><span>RAW</span><b>source_snapshot</b><small>Immutable JSONB</small></div><i>→</i><div><span>CORE</span><b>auction + result</b><small>Typed relational data</small></div><i>→</i><div><span>SERVE</span><b>v_auction_monitor</b><small>Schedule + prior result</small></div></section>
          <div className="schema-grid">{tableCards.map((table) => <article className="schema-card" key={table.name}><div className="schema-top"><h3>{table.name}</h3><span>{table.key}</span></div><p>{table.copy}</p><code>{table.cols}</code></article>)}</div>
          <section className="index-panel"><div><span className="section-kicker">QUERY-FIRST INDEXES</span><h3>Optimized for the terminal’s hot paths</h3></div><div className="index-list"><code>(status, auction_date) WHERE status != 'resulted'</code><span>Forward calendar</span><code>(security_term, auction_date DESC)</code><span>Comparable prior result</span><code>(cusip, auction_date DESC)</code><span>Security history</span></div></section>
        </div>}
      </section>
    </main>
  );
}
