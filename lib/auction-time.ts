import type { TreasuryAuction } from "./treasury";

export type DisplayZone = "KST" | "ET";
export const ZONES = { KST: "Asia/Seoul", ET: "America/New_York" } as const;
export const zoneLabel = (zone: DisplayZone) => zone === "KST" ? "한국 KST" : "미국 동부 ET";

const formatters = Object.fromEntries(Object.entries(ZONES).map(([key, timeZone]) => [key,
  new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }),
])) as Record<DisplayZone, Intl.DateTimeFormat>;

function parts(value: Date, zone: DisplayZone) {
  return Object.fromEntries(formatters[zone].formatToParts(value).map(part => [part.type, part.value]));
}

export function dateOnly(value: string | undefined): string {
  const match = value?.match(/^(\d{4}-\d{2}-\d{2})(?:$|T)/);
  if (!match) return "N/A";
  const parsed = new Date(`${match[1]}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === match[1] ? match[1] : "N/A";
}

export function displayInstant(value: string | Date | null | undefined, zone: DisplayZone) {
  // 시간대가 없는 시각 문자열을 실행 컴퓨터의 현지 시각으로 추정하지 않습니다.
  const date = value instanceof Date ? value : typeof value === "string" && /(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? new Date(value) : null;
  if (!date || !Number.isFinite(date.getTime())) return { date: "N/A", time: "N/A", basis: zoneLabel(zone), full: `N/A · ${zoneLabel(zone)}` };
  const p = parts(date, zone);
  const day = `${p.year}-${p.month}-${p.day}`;
  const time = `${p.hour}:${p.minute}`;
  return { date: day, time, basis: zoneLabel(zone), full: `${day} ${time} · ${zoneLabel(zone)}` };
}

/** 기존 데이터 모델의 ET 입찰일+마감 시각을 실제 순간으로 변환합니다. */
export function auctionInstant(row: TreasuryAuction | undefined): Date | null {
  if (!row || dateOnly(row.auctionDate) === "N/A") return null;
  const time = row.closingTimeCompetitive?.trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?(?:\s+(?:ET|EST|EDT))?$/i);
  if (!time) return null;
  let hour = Number(time[1]);
  const minute = Number(time[2]), second = Number(time[3] ?? 0);
  if (minute > 59 || second > 59 || (time[4] ? hour < 1 || hour > 12 : hour > 23)) return null;
  if (time[4]) hour = hour % 12 + (time[4].toUpperCase() === "PM" ? 12 : 0);
  const [year, month, day] = dateOnly(row.auctionDate).split("-").map(Number);
  const wall = Date.UTC(year, month - 1, day, hour, minute, second);
  const wallAt = (milliseconds: number) => {
    const p = parts(new Date(milliseconds), "ET");
    return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute), Number(p.second));
  };
  let candidate = wall;
  for (let i = 0; i < 4; i++) candidate += wall - wallAt(candidate);
  // 서머타임 전환으로 존재하지 않거나 두 번 존재하는 현지 시각은 추정하지 않습니다.
  if (wallAt(candidate) !== wall || wallAt(candidate - 3600000) === wall || wallAt(candidate + 3600000) === wall) return null;
  return new Date(candidate);
}

export function auctionDateTime(row: TreasuryAuction | undefined, zone: DisplayZone) {
  const instant = auctionInstant(row);
  if (instant) return { ...displayInstant(instant, zone), converted: true };
  const date = dateOnly(row?.auctionDate);
  return { date, time: "N/A", basis: "원문 ET · 시각 없음/확인 불가", full: `${date} · 원문 ET · 시각 없음/확인 불가`, converted: false };
}

// 마감이 확인된 일정만 현재 시각과 비교합니다. 표본 여부는 호출 화면에서 별도로 표시합니다.
export function scheduleRows(rows: TreasuryAuction[], asOf: string) {
  const now = new Date(asOf).getTime();
  const localDay = displayInstant(asOf, "ET").date;
  return rows.filter(row => {
    const instant = auctionInstant(row);
    return instant ? instant.getTime() >= now : dateOnly(row.auctionDate) !== "N/A" && dateOnly(row.auctionDate) >= localDay;
  }).sort((a, b) => (auctionInstant(a)?.getTime() ?? new Date(`${dateOnly(a.auctionDate)}T23:59:59Z`).getTime()) - (auctionInstant(b)?.getTime() ?? new Date(`${dateOnly(b.auctionDate)}T23:59:59Z`).getTime()));
}
