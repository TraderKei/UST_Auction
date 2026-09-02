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
