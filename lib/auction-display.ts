import type { TreasuryAuction } from "./treasury";

// 원본 API 배수는 보존하고, 화면 경계에서만 백분율로 변환합니다.
export function subscriptionPercent(ratio: number | null | undefined): number | null {
  return ratio != null && Number.isFinite(ratio) && ratio >= 0 ? ratio * 100 : null;
}

export function percent(value: number | null | undefined, digits = 1): string {
  return value != null && Number.isFinite(value) ? `${value.toFixed(digits)}%` : "N/A";
}

export const subscription = (ratio: number | null | undefined) => percent(subscriptionPercent(ratio));

export function awardMix(row: TreasuryAuction | undefined): number[] | null {
  if (!row || row.totalAccepted == null || row.totalAccepted <= 0) return null;
  const values = [row.indirectAccepted, row.directAccepted, row.dealerAccepted];
  if (values.some(value => value == null || !Number.isFinite(value) || value < 0)) return null;
  const shares = values.map(value => value! / row.totalAccepted! * 100);
  const sum = shares.reduce((a, b) => a + b, 0);
  if (sum > 100.01) return null;
  return [...shares, Math.max(0, 100 - sum)];
}

export function priorResult(row: TreasuryAuction | undefined, results: TreasuryAuction[]) {
  return row ? results.filter(result => result.type === row.type && result.term === row.term && result.auctionDate < row.auctionDate)
    .sort((a, b) => b.auctionDate.localeCompare(a.auctionDate))[0] : undefined;
}

export function average(values: Array<number | null | undefined>): number | null {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  return valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null;
}

export type SubscriptionRollingPoint = {
  row: TreasuryAuction;
  value: number;
  average6: number | null;
  average24Months: number | null;
  lower24Months: number | null;
  upper24Months: number | null;
};

function utcDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return Number.isNaN(date.getTime()) ? null : date;
}

function subtractUtcMonths(value: Date, months: number) {
  const year = value.getUTCFullYear();
  const month = value.getUTCMonth() - months;
  const day = value.getUTCDate();
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return Date.UTC(year, month, Math.min(day, lastDay));
}

function populationStandardDeviation(values: number[], mean: number) {
  return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
}

// 입력 시리즈 내부에서만, 각 입찰일 현재와 과거 관측치만 사용합니다.
export function subscriptionRollingSeries(rows: TreasuryAuction[]): SubscriptionRollingPoint[] {
  const validPoints = rows
    .map(row => ({ row, date: utcDate(row.auctionDate), value: subscriptionPercent(row.bidToCover) }))
    .filter((point): point is { row: TreasuryAuction; date: Date; value: number } => point.date != null && point.value != null);
  const groups = new Map<string, typeof validPoints>();
  for (const point of validPoints) {
    const series = `${point.row.type}\u0000${point.row.term}`;
    groups.set(series, [...(groups.get(series) ?? []), point]);
  }

  return [...groups.values()].flatMap(group => {
    const points = group.sort((a, b) => a.date.getTime() - b.date.getTime() || a.row.cusip.localeCompare(b.row.cusip));
    const firstObservation = points[0].date.getTime();
    return points.map((point, index) => {
      const sixValues = points.slice(Math.max(0, index - 5), index + 1).map(item => item.value);
      const cutoff = subtractUtcMonths(point.date, 24);
      const windowValues = points
        .slice(0, index + 1)
        .filter(item => item.date.getTime() > cutoff)
        .map(item => item.value);
      // 데이터 조회 시작점 때문에 불완전한 24개월 창을 기준선으로 오인하지 않도록 숨깁니다.
      const hasFull24Months = firstObservation <= cutoff;
      const mean = hasFull24Months ? average(windowValues) : null;
      const deviation = mean != null ? populationStandardDeviation(windowValues, mean) : null;
      return {
        row: point.row,
        value: point.value,
        average6: sixValues.length === 6 ? average(sixValues) : null,
        average24Months: mean,
        lower24Months: mean != null && deviation != null ? mean - deviation : null,
        upper24Months: mean != null && deviation != null ? mean + deviation : null,
      };
    });
  }).sort((a, b) => a.row.auctionDate.localeCompare(b.row.auctionDate) || a.row.cusip.localeCompare(b.row.cusip));
}

export function percentagePointChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  return current != null && previous != null && Number.isFinite(current) && Number.isFinite(previous) ? current - previous : null;
}

export function signedPoints(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "비교 자료 없음";
  const rounded = Number(value.toFixed(1));
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}%p`;
}

const typeNames: Record<string, string> = { Bill: "단기채", Note: "중기채", Bond: "장기채", TIPS: "물가연동채", FRN: "변동금리채" };
export const typeName = (type: string) => typeNames[type] ?? type;
export const termName = (term: string) => term.replace(/-Year(s)?/gi, "년").replace(/-Week(s)?/gi, "주").replace(/-Month(s)?/gi, "개월");
export const securityName = (row: TreasuryAuction | undefined) => row ? `${termName(row.term)} ${typeName(row.type)}` : "결과 없음";
export const stopName = (row: TreasuryAuction | undefined) => row?.type === "Bill" || row?.cmb ? "High Rate (Stop)" : row?.type === "TIPS" ? "실질금리 (Stop)" : row?.type === "FRN" ? "할인마진 (Stop)" : "High Yield (Stop)";
