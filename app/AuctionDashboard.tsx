"use client";

import { useMemo, useState } from "react";
import type { TreasuryAuction } from "../lib/treasury";

type Props = { upcoming: TreasuryAuction[]; results: TreasuryAuction[]; source: "live" | "snapshot"; updatedAt: string };
type View = "market" | "api" | "database";
type Tab = "upcoming" | "results";

const compactMoney = (value: number | null) => value == null ? "—" : `$${(value / 1e9).toFixed(value < 10e9 ? 1 : 0)}B`;
const pct = (value: number | null, total: number | null) => value != null && total ? (value / total) * 100 : 0;
const dateParts = (iso: string) => {
  const d = new Date(iso);
  return { date: d.toLocaleDateString("en-US", { month: "short", day: "2-digit", timeZone: "UTC" }).toUpperCase(), day: d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }).toUpperCase() };
};
const fullDate = (iso: string) => iso ? new Date(iso).toLocaleDateString("en-US", { year:"numeric", month:"short", day:"2-digit", timeZone:"UTC" }) : "—";
const rate = (value: number | null) => value == null ? "—" : `${value.toFixed(3)}%`;

const extractionGroups = [
  { title:"Identity & instrument", tone:"blue", fields:[["cusip","Permanent security identifier"],["type / securityType","Bill, Note, Bond, TIPS, FRN"],["term / securityTerm","Display tenor and remaining tenor"],["maturityDate","Final maturity"],["reopening","Original issue vs reopening"]] },
  { title:"Calendar & terms", tone:"violet", fields:[["announcementDate","Terms become official"],["auctionDate","Competitive auction date"],["issueDate","Settlement / issue date"],["closingTimeCompetitive","Institutional bid deadline (ET)"],["offeringAmount","Headline supply amount"]] },
  { title:"Clearing result", tone:"mint", fields:[["highYield / highDiscountRate","Type-aware stop metric"],["highInvestmentRate","Bill bond-equivalent return"],["highDiscountMargin","FRN stop spread"],["pricePer100","Uniform auction price"],["bidToCoverRatio","Primary demand signal"]] },
  { title:"Demand composition", tone:"amber", fields:[["totalTendered / totalAccepted","Gross demand and awards"],["primaryDealerAccepted","Dealer take-down"],["directBidderAccepted","Direct bidder awards"],["indirectBidderAccepted","Foreign / institutional proxy"],["somaAccepted / fima…","Official-sector awards"]] },
];

const tableCards = [
  { name:"security_master", key:"cusip", copy:"Security-level reference data", cols:"type · original_term · maturity_date · tips · frn" },
  { name:"auction", key:"auction_id", copy:"One row per auction event", cols:"cusip · auction_date · issue_date · offering_amount · status" },
  { name:"auction_result", key:"auction_id", copy:"One-to-one clearing outcome", cols:"stop_value · stop_metric · bid_to_cover · price_per_100" },
  { name:"bidder_allocation", key:"auction_id + bidder_type", copy:"Normalized bidder take-down", cols:"tendered_amount · accepted_amount · accepted_pct" },
  { name:"source_snapshot", key:"snapshot_id", copy:"Immutable API lineage", cols:"endpoint · fetched_at · payload_hash · raw_payload" },
  { name:"auction_metric_daily", key:"as_of_date + bucket", copy:"Optional serving aggregate", cols:"supply · avg_bid_to_cover · indirect_pct · count" },
];

export default function AuctionDashboard({ upcoming, results, source, updatedAt }: Props) {
  const [view, setView] = useState<View>("market");
  const [tab, setTab] = useState<Tab>("upcoming");
  const [filter, setFilter] = useState("All");
  const [selectedCusip, setSelectedCusip] = useState(results[0]?.cusip ?? upcoming[0]?.cusip ?? "");

  const universe = tab === "upcoming" ? upcoming : results;
  const rows = useMemo(() => universe.filter((r) => filter === "All" || r.type === filter).slice(0, 10), [universe, filter]);
  const selected = results.find((r) => r.cusip === selectedCusip) ?? rows[0] ?? results[0];
  const totalSupply = upcoming.reduce((sum, row) => sum + row.offeringAmount, 0);
  const avgCover = results.length ? results.reduce((sum, row) => sum + (row.bidToCover ?? 0), 0) / results.filter((row) => row.bidToCover != null).length : 0;
  const demand = results.slice(0, 9).reverse();
  const maxDemand = Math.max(3.6, ...demand.map((d) => d.bidToCover ?? 0));
  const stamp = new Date(updatedAt).toLocaleString("en-US", { month:"short", day:"2-digit", hour:"2-digit", minute:"2-digit", timeZone:"America/New_York", timeZoneName:"short" });
  const nav = (next: View) => { setView(next); if (next === "market") setTab("upcoming"); };

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

        <div className="ticker" aria-label="Market context strip">
          <span>UST 2Y <b>3.684</b> <i>−1.8bp</i></span><span>UST 5Y <b>3.879</b> <i>−1.2bp</i></span><span>UST 10Y <b>4.214</b> <i className="up">+0.6bp</i></span><span>UST 30Y <b>4.842</b> <i className="up">+1.1bp</i></span><span className="source-note">SOURCE · U.S. TREASURY FISCAL SERVICE</span>
        </div>

        {view === "market" && <div className="content">
          <section className="hero-row">
            <div><div className="section-kicker">AUCTION PULSE</div><h2>Primary supply at a glance</h2><p className="hero-copy">Upcoming terms and clearing signals, distilled for the rates desk.</p></div>
            <div className="metric"><span>Next auction</span><strong>{upcoming[0] ? dateParts(upcoming[0].auctionDate).date : "—"}</strong><small>{upcoming[0]?.term} {upcoming[0]?.type}</small></div>
            <div className="metric"><span>Announced supply</span><strong>{compactMoney(totalSupply)}</strong><small>{upcoming.length} upcoming lines</small></div>
            <div className="metric"><span>Avg. bid / cover</span><strong>{avgCover.toFixed(2)}×</strong><small className="positive">Latest {results.length} auctions</small></div>
          </section>

          <section className="dashboard-grid">
            <article className="panel schedule-panel">
              <div className="panel-head panel-head-wrap">
                <div><span className="section-kicker">AUCTION TAPE</span><h3>{tab === "upcoming" ? "Forward calendar" : "Recent results"}</h3></div>
                <div className="panel-controls">
                  <div className="segmented tabs" aria-label="Dataset"><button className={tab === "upcoming" ? "selected" : ""} onClick={() => setTab("upcoming")}>Upcoming <b>{upcoming.length}</b></button><button className={tab === "results" ? "selected" : ""} onClick={() => setTab("results")}>Results <b>{results.length}</b></button></div>
                  <div className="filter-row" aria-label="Security filter">{["All","Bill","Note","Bond","TIPS","FRN"].map((name) => <button key={name} className={filter === name ? "selected" : ""} onClick={() => setFilter(name)}>{name}</button>)}</div>
                </div>
              </div>
              <div className="table-wrap"><table><thead><tr>{tab === "upcoming" ? <><th>Auction</th><th>Security</th><th>Offering</th><th>Competitive close</th><th>Issue</th><th>Type</th></> : <><th>Auction</th><th>Security</th><th>Stop</th><th>Bid / cover</th><th>Offering</th><th>Price</th></>}</tr></thead>
                <tbody>{rows.map((row) => { const dp = dateParts(row.auctionDate); return <tr key={`${row.cusip}-${row.auctionDate}`} className={selected?.cusip === row.cusip ? "row-selected" : ""} onClick={() => setSelectedCusip(row.cusip)}>
                  <td><b>{dp.date}</b><small>{dp.day}</small></td><td><b>{row.term}</b><small>{row.cusip}</small></td>{tab === "upcoming" ? <><td className="mono strong">{compactMoney(row.offeringAmount)}</td><td><b className="mono">{row.closingTimeCompetitive}</b><small>Eastern Time</small></td><td><b>{fullDate(row.issueDate)}</b><small>Matures {fullDate(row.maturityDate)}</small></td><td><span className={`type-badge ${row.type.toLowerCase()}`}>{row.type}</span>{row.reopening && <small>Reopening</small>}</td></> : <><td><b className="mono">{rate(row.stopRate)}</b><small>{row.stopLabel}</small></td><td><b className="mono cover">{row.bidToCover?.toFixed(2)}×</b><small>{compactMoney(row.totalTendered)} tendered</small></td><td className="mono strong">{compactMoney(row.offeringAmount)}</td><td><b className="mono">{row.pricePer100?.toFixed(4)}</b><small>per $100</small></td></>}
                </tr>})}{!rows.length && <tr><td colSpan={6} className="empty-state">No {filter} auctions in this window.</td></tr>}</tbody>
              </table></div>
              <div className="table-foot"><span><i /> Row click updates allocation detail</span><span>Times shown in ET · amounts USD</span></div>
            </article>

            <div className="right-stack">
              <article className="panel chart-panel">
                <div className="panel-head"><div><span className="section-kicker">DEMAND SIGNAL</span><h3>Bid-to-cover trend</h3></div><span className="range">LATEST {demand.length}</span></div>
                <div className="chart-summary"><strong>{avgCover.toFixed(2)}×</strong><span>window average</span></div>
                <div className="bar-chart" aria-label="Recent bid-to-cover bar chart">{demand.map((row) => <button className="bar-column" key={`${row.cusip}-${row.auctionDate}`} onClick={() => { setSelectedCusip(row.cusip); setTab("results"); }} aria-label={`${row.term} ${row.bidToCover} times`}><span className="bar-value">{row.bidToCover?.toFixed(2)}</span><div className={`bar ${selected?.cusip === row.cusip ? "focus" : ""}`} style={{height:`${((row.bidToCover ?? 0) / maxDemand) * 100}%`}} /><small>{row.term.replace("-Year","Y").replace("-Week","W")}</small></button>)}</div>
              </article>

              {selected && <article className="panel allocation-panel">
                <div className="panel-head"><div><span className="section-kicker">TAKE-DOWN</span><h3>{selected.term} {selected.type}</h3></div><span className="cusip">{selected.cusip}</span></div>
                <div className="allocation-hero"><div><span>{selected.stopLabel}</span><strong>{rate(selected.stopRate)}</strong></div><div><span>Bid / cover</span><strong>{selected.bidToCover?.toFixed(2) ?? "—"}×</strong></div><div><span>Auction</span><strong>{dateParts(selected.auctionDate).date}</strong></div></div>
                <div className="mix-label"><span>Award mix</span><b>{compactMoney(selected.totalAccepted)} accepted</b></div>
                <div className="mix-bar" aria-label="Accepted awards by bidder type"><span className="indirect" style={{width:`${pct(selected.indirectAccepted,selected.totalAccepted)}%`}}/><span className="direct" style={{width:`${pct(selected.directAccepted,selected.totalAccepted)}%`}}/><span className="dealer" style={{width:`${pct(selected.dealerAccepted,selected.totalAccepted)}%`}}/><span className="other" /></div>
                <div className="legend"><span><i className="indirect"/>Indirect <b>{pct(selected.indirectAccepted,selected.totalAccepted).toFixed(1)}%</b></span><span><i className="direct"/>Direct <b>{pct(selected.directAccepted,selected.totalAccepted).toFixed(1)}%</b></span><span><i className="dealer"/>Dealer <b>{pct(selected.dealerAccepted,selected.totalAccepted).toFixed(1)}%</b></span></div>
              </article>}
            </div>
          </section>
        </div>}

        {view === "api" && <div className="content reference-page">
          <section className="reference-hero"><div><span className="section-kicker">~100 RAW FIELDS → 24 ANALYTIC FIELDS</span><h2>Extract signal, retain lineage.</h2><p>The two TreasuryDirect feeds share one wide schema. Announcement rows leave outcome fields blank; result rows populate them. The serving model converts empty strings to NULL and applies a type-aware clearing metric.</p></div><div className="endpoint-stack"><code>GET /TA_WS/securities/announced?format=json</code><code>GET /TA_WS/securities/auctioned?format=json&amp;day=45</code></div></section>
          <div className="extraction-grid">{extractionGroups.map((group) => <article className={`field-card ${group.tone}`} key={group.title}><div className="field-card-head"><span>{String(extractionGroups.indexOf(group)+1).padStart(2,"0")}</span><h3>{group.title}</h3></div>{group.fields.map(([field,copy]) => <div className="field-row" key={field}><code>{field}</code><p>{copy}</p></div>)}</article>)}</div>
          <section className="logic-strip"><div><span>01</span><b>Parse</b><small>"" → NULL · money → DECIMAL(20,2) · ET dates → DATE/TIME</small></div><div><span>02</span><b>Unify stop</b><small>Bill = highDiscountRate · coupon = highYield · FRN = highDiscountMargin</small></div><div><span>03</span><b>Validate</b><small>Composite identity: cusip + auction_date + issue_date</small></div><div><span>04</span><b>Preserve</b><small>Store raw JSON and payload hash for audit replay</small></div></section>
        </div>}

        {view === "database" && <div className="content reference-page">
          <section className="reference-hero database-hero"><div><span className="section-kicker">POSTGRESQL · APPEND-SAFE · AUDITABLE</span><h2>A normalized core with a fast serving edge.</h2><p>The model separates stable instrument identity, auction events, results, and repeating bidder allocations. Raw snapshots make every transformed value traceable back to TreasuryDirect.</p></div><div className="db-stat"><span>Core tables</span><strong>5</strong><small>+ 1 optional aggregate</small></div></section>
          <section className="pipeline" aria-label="Data processing flow"><div><span>INGEST</span><b>TreasuryDirect API</b><small>15-minute polling</small></div><i>→</i><div><span>RAW</span><b>source_snapshot</b><small>Immutable JSONB</small></div><i>→</i><div><span>CORE</span><b>auction + result</b><small>Typed relational data</small></div><i>→</i><div><span>SERVE</span><b>v_auction_terminal</b><small>Desk-ready view</small></div></section>
          <div className="schema-grid">{tableCards.map((table) => <article className="schema-card" key={table.name}><div className="schema-top"><h3>{table.name}</h3><span>{table.key}</span></div><p>{table.copy}</p><code>{table.cols}</code></article>)}</div>
          <section className="index-panel"><div><span className="section-kicker">QUERY-FIRST INDEXES</span><h3>Optimized for the terminal’s three hot paths</h3></div><div className="index-list"><code>(auction_date DESC, security_type)</code><span>Recent tape & filters</span><code>(status, auction_date) WHERE status != 'resulted'</code><span>Upcoming calendar</span><code>(cusip, auction_date DESC)</code><span>Security history</span></div></section>
        </div>}
      </section>
    </main>
  );
}
