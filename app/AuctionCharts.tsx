"use client";

import type { TreasuryAuction } from "../lib/treasury";
import { awardMix, percent, securityName, stopName, subscriptionPercent, subscriptionRollingSeries, termName } from "../lib/auction-display";
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

export function SubscriptionChart({ rows, onSelect, zone }: ChartProps) {
  const points = subscriptionRollingSeries(rows);
  const rolling24 = points.filter(point => point.average24Months != null && point.lower24Months != null && point.upper24Months != null);
  const rolling6 = points.filter(point => point.average6 != null);
  const values = points.flatMap(point => [point.value, point.lower24Months, point.upper24Months, point.average24Months, point.average6])
    .filter((value): value is number => value != null && Number.isFinite(value));
  const padding = values.length ? Math.max(10, (Math.max(...values) - Math.min(...values)) * 0.15) : 10;
  const min = values.length ? Math.max(0, Math.min(...values) - padding) : 0;
  const max = values.length ? Math.max(...values) + padding : 1;
  const y = (value: number) => 175 - (value - min) / Math.max(1, max - min) * 150;
  const times = points.map(point => Date.parse(`${point.row.auctionDate}T00:00:00Z`));
  const firstTime = times[0] ?? 0;
  const lastTime = times[times.length - 1] ?? firstTime;
  const xForTime = (time: number) => firstTime === lastTime ? 190 : 50 + (time - firstTime) / (lastTime - firstTime) * 270;
  const x = (point: typeof points[number]) => xForTime(Date.parse(`${point.row.auctionDate}T00:00:00Z`));
  const line = (series: typeof points, value: (point: typeof points[number]) => number | null) => series
    .map(point => `${x(point)},${y(value(point)!)}`).join(" ");
  const band = rolling24.length > 1
    ? `${line(rolling24, point => point.upper24Months)} ${[...rolling24].reverse().map(point => `${x(point)},${y(point.lower24Months!)}`).join(" ")}`
    : "";
  const label = "응찰률 (%) 차트, 개별 입찰값, 24개월 평균과 ±1σ, 최근 6회 평균";

  return <div className="chart-box">
    {!points.length ? <div className="chart-empty">표시할 데이터 없음</div> : <svg viewBox="0 0 350 218" role="img" aria-label={label}>
      <title>{`${label} — ${points.length}개 입찰`}</title>
      {[0, 1, 2, 3].map(index => {
        const value = min + (max - min) * index / 3;
        return <g key={index}><line x1="45" x2="338" y1={y(value)} y2={y(value)} className="grid-line" /><text x="39" y={y(value) + 4} textAnchor="end">{percent(value, 0)}</text></g>;
      })}
      {band && <polygon points={band} fill="#6f87a8" fillOpacity=".2" className="subscription-band" />}
      {rolling24.length > 1 && <polyline points={line(rolling24, point => point.average24Months)} fill="none" stroke="#9aabc1" strokeWidth="1.8" strokeLinejoin="round" className="subscription-average-24" />}
      {rolling6.length > 1 && <polyline points={line(rolling6, point => point.average6)} fill="none" stroke="#f3c969" strokeWidth="3.2" strokeLinejoin="round" className="subscription-average-6" />}
      {points.map((point, index) => <g key={key(point.row)}>
        <circle cx={x(point)} cy={y(point.value)} r="3.2" fill="#ff5268" stroke="#ffd0d6" strokeWidth=".7" role="button" tabIndex={0}
          aria-label={`${auctionDateTime(point.row, zone).full} ${securityName(point.row)} 응찰률 ${percent(point.value, 1)}`}
          onClick={() => onSelect(point.row)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(point.row); } }}>
          <title>{`${auctionDateTime(point.row, zone).full} · ${securityName(point.row)} · 응찰률 ${percent(point.value, 1)}`}</title>
        </circle>
        {showDate(index, points.length) && <DateAxis row={point.row} zone={zone} x={x(point)} />}
      </g>)}
      <text x="330" y="14" textAnchor="end" style={{ fill: "#ff7183" }} className="chart-last-value">{percent(points[points.length - 1].value, 1)}</text>
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
