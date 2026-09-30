export type AuctionDateRange = {
  from: string;
  to: string;
};

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function dateParts(value: string) {
  const match = ISO_DATE.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return { year, month, day };
}

function formatDate(year: number, month: number, day: number) {
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function lastDayOfMonth(year: number, month: number) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && dateParts(value) !== null;
}

export function isoDateFromInstant(value: Date) {
  return formatDate(value.getUTCFullYear(), value.getUTCMonth() + 1, value.getUTCDate());
}

export function shiftCalendarYears(value: string, years: number) {
  const parts = dateParts(value);
  if (!parts || !Number.isInteger(years)) throw new Error("A valid date and whole calendar-year offset are required");
  const year = parts.year + years;
  return formatDate(year, parts.month, Math.min(parts.day, lastDayOfMonth(year, parts.month)));
}

export function shiftCalendarMonths(value: string, months: number) {
  const parts = dateParts(value);
  if (!parts || !Number.isInteger(months)) throw new Error("A valid date and whole calendar-month offset are required");
  const monthIndex = parts.year * 12 + parts.month - 1 + months;
  const year = Math.floor(monthIndex / 12);
  const month = monthIndex - year * 12 + 1;
  return formatDate(year, month, Math.min(parts.day, lastDayOfMonth(year, month)));
}

export function defaultAuctionDateRange(today = new Date()): AuctionDateRange {
  const to = isoDateFromInstant(today);
  return { from: shiftCalendarYears(to, -2), to };
}

export function validateAuctionDateRange(from: unknown, to: unknown): string | null {
  if (!from || !to) return "시작일과 종료일을 모두 입력해 주세요.";
  if (!isIsoDate(from) || !isIsoDate(to)) return "조회기간은 YYYY-MM-DD 형식의 올바른 날짜여야 합니다.";
  if (from > to) return "시작일은 종료일보다 늦을 수 없습니다.";
  return null;
}

function firstParameter(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export function resolveAuctionDateRange(
  parameters: { from?: string | string[]; to?: string | string[] } | undefined,
  today = new Date(),
): AuctionDateRange {
  const defaults = defaultAuctionDateRange(today);
  const from = firstParameter(parameters?.from);
  const to = firstParameter(parameters?.to);
  return validateAuctionDateRange(from, to) === null ? { from: from!, to: to! } : defaults;
}

export function isAuctionInDateRange(auctionDate: string, range: AuctionDateRange) {
  return isIsoDate(auctionDate) && auctionDate >= range.from && auctionDate <= range.to;
}

export function filterAuctionsByDateRange<T extends { auctionDate: string }>(rows: T[], range: AuctionDateRange) {
  return rows.filter(row => isAuctionInDateRange(row.auctionDate, range));
}
