"use client";

import type { TreasuryAuction } from "../lib/treasury";
import { awardMix, percent, securityName, stopName, subscriptionPercent, termName } from "../lib/auction-display";
import { auctionDateTime, type DisplayZone } from "../lib/auction-time";

const key = (row: TreasuryAuction) => `${row.cusip}-${row.auctionDate}`;
type ChartProps = { rows: TreasuryAuction[]; onSelect: (row: TreasuryAuction) => void; zone: DisplayZone };
const showDate = (index: number, count: number) => index === 0 || index === count - 1 || index === Math.floor((count - 1) / 2);
function DateAxis({ row, zone, x }: { row: TreasuryAuction; zone: DisplayZone; x: number }) {
  const date = auctionDateTime(row, zone);
  return <><text className="axis-date" x={x} y="196" textAnchor="middle">{date.date}</text><text className="axis-term" x={x} y="210" textAnchor="middle">{termName(row.term)} · {date.converted ? zone : "원문 ET"}</text></>;
}

export function AuctionLineChart({ rows, kind, onSelect, zone }: ChartProps & { kind: "stop" | "subscription" }) {
  const isSubscription = kind === "subscription";
  const points = rows.flatMap(row => {
    const value = isSubscription ? subscriptionPercent(row.bidToCover) : row.stopRate;
    return value == null || !Number.isFinite(value) ? [] : [{ row, value }];
  });
  const values = points.map(point => point.value);
  const padding = Math.max(isSubscription ? 20 : 0.05, (Math.max(...values) - Math.min(...values)) * 0.2);
  const min = values.length ? (isSubscription ? Math.max(0, Math.min(...values) - padding) : Math.min(...values) - padding) : 0;
  const max = values.length ? Math.max(...values) + padding : 1;
  const y = (value: number) => 175 - (value - min) / (max - min) * 150;
  const x = (index: number) => points.length === 1 ? 190 : 50 + index / (points.length - 1) * 270;
  const coordinates = points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ");
  const label = isSubscription ? "응찰률 (%) 차트" : "낙찰 금리 (%) 차트";
  const color = isSubscription ? "#ff5268" : "#4385f5";
  return <div className="chart-box">
    {!points.length ? <div className="chart-empty">표시할 데이터 없음</div> : <svg viewBox="0 0 350 218" role="img" aria-label={label}>
      <title>{`${label} — ${points.length}개 입찰`}</title>
      <defs><linearGradient id={`area-${kind}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".25" /><stop offset="100%" stopColor={color} stopOpacity=".02" /></linearGradient></defs>
      {[0, 1, 2, 3].map(index => {
        const value = min + (max - min) * index / 3;
        return <g key={index}><line x1="45" x2="338" y1={y(value)} y2={y(value)} className="grid-line" /><text x="39" y={y(value) + 4} textAnchor="end">{percent(value, isSubscription ? 0 : 2)}</text></g>;
      })}
      {points.length > 1 && <><polygon points={`${x(0)},175 ${coordinates} ${x(points.length - 1)},175`} fill={`url(#area-${kind})`} /><polyline points={coordinates} fill="none" stroke={color} strokeWidth="2.3" strokeLinejoin="round" /></>}
      {points.map((point, index) => <g key={key(point.row)}>
        <circle cx={x(index)} cy={y(point.value)} r="4" fill={color} role="button" tabIndex={0}
          aria-label={`${auctionDateTime(point.row, zone).full} ${securityName(point.row)} ${isSubscription ? "응찰률" : stopName(point.row)} ${percent(point.value, isSubscription ? 1 : 3)}`}
          onClick={() => onSelect(point.row)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(point.row); } }}>
          <title>{`${auctionDateTime(point.row, zone).full} · ${securityName(point.row)}: ${percent(point.value, isSubscription ? 1 : 3)}`}</title>
        </circle>
        {showDate(index, points.length) && <DateAxis row={point.row} zone={zone} x={x(index)} />}
      </g>)}
      <text x="330" y="14" textAnchor="end" style={{ fill: color }} className="chart-last-value">{percent(points[points.length - 1].value, isSubscription ? 1 : 3)}</text>
    </svg>}
  </div>;
}

export function AllocationChart({ rows, onSelect, zone }: ChartProps) {
  const width = 270 / Math.max(1, rows.length);
  return <div className="chart-box">
    {!rows.length ? <div className="chart-empty">배정 데이터 없음</div> : <svg viewBox="0 0 350 218" role="img" aria-label="참여자별 낙찰 비중 — 전체 낙찰액 기준 100% 누적 막대 차트">
      <title>입찰별 배정 비중. 기타 금액을 포함한 전체 낙찰액 기준.</title>
      {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1="45" x2="338" y1={175 - value * 1.5} y2={175 - value * 1.5} className="grid-line" /><text x="39" y={179 - value * 1.5} textAnchor="end">{value}%</text></g>)}
      {rows.map((row, index) => {
        const mix = awardMix(row);
        let cursor = 175;
        return <g key={key(row)} role="button" tabIndex={0} aria-label={`${auctionDateTime(row, zone).full} ${securityName(row)} 배정 상세`}
          onClick={() => onSelect(row)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(row); } }}>
          <title>{`${auctionDateTime(row, zone).full} · ${securityName(row)}${mix ? ` — 간접 ${percent(mix[0])}, 직접 ${percent(mix[1])}, PD ${percent(mix[2])}, 기타 ${percent(mix[3])}` : " — 배정 데이터 없음"}`}</title>
          {mix ? [2, 1, 0, 3].map(category => {
            const value = mix[category];
            cursor -= value * 1.5;
            return <rect key={category} x={50 + index * width} y={cursor} width={Math.min(34, width - 3)} height={value * 1.5} fill={["#79ba55", "#4b78f4", "#9950c6", "#5c7186"][category]} />;
          }) : <text x={50 + index * width} y="100">N/A</text>}
          {showDate(index, rows.length) && <DateAxis row={row} zone={zone} x={50 + index * width + Math.min(34, width - 3) / 2} />}
        </g>;
      })}
    </svg>}
  </div>;
}
