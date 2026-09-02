import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./source-loader.mjs";

const { auctionInstant, auctionDateTime, dateOnly, displayInstant, scheduleRows } = loadSource("../lib/auction-time.ts");
const row = (auctionDate, closingTimeCompetitive = "01:00 PM") => ({ auctionDate, closingTimeCompetitive });

test("ET 서머타임은 13시간, 표준시에는 14시간 차이를 적용", () => {
  assert.equal(auctionInstant(row("2026-08-25")).toISOString(), "2026-08-25T17:00:00.000Z");
  assert.equal(auctionInstant(row("2026-01-15")).toISOString(), "2026-01-15T18:00:00.000Z");
  assert.equal(auctionDateTime(row("2026-08-25"), "KST").full, "2026-08-26 02:00 · 한국 KST");
  assert.equal(auctionDateTime(row("2026-01-15"), "KST").full, "2026-01-16 03:00 · 한국 KST");
});

test("월말·연말 날짜 변경 및 자정 00:00 표기", () => {
  assert.equal(auctionDateTime(row("2026-12-31"), "KST").full, "2027-01-01 03:00 · 한국 KST");
  assert.equal(auctionDateTime(row("2026-08-31", "11:00 AM"), "KST").full, "2026-09-01 00:00 · 한국 KST");
  assert.equal(auctionDateTime(row("2026-08-25", "12:00 AM"), "ET").time, "00:00");
  assert.equal(auctionDateTime(row("2026-08-25", "12:00 PM"), "ET").time, "12:00");
});

test("서머타임 전후 날짜와 존재하지 않거나 중복된 시각 처리", () => {
  for (const [date, expected] of [["2026-03-06", "18:00"], ["2026-03-09", "17:00"], ["2026-10-30", "17:00"], ["2026-11-02", "18:00"]]) {
    assert.ok(auctionInstant(row(date)).toISOString().includes(`T${expected}:00`));
  }
  assert.equal(auctionInstant(row("2026-03-08", "02:30 AM")), null);
  assert.equal(auctionInstant(row("2026-11-01", "01:30 AM")), null);
});

test("시각 형식 검증: 12/24시간·초·ET 접미사 지원", () => {
  for (const time of ["01:00 PM", "1:00 pm", "13:00", "13:00:00", "1:00 PM ET", "1:00 PM EDT"]) {
    assert.equal(auctionDateTime(row("2026-08-25", time), "ET").time, "13:00");
  }
  for (const time of ["", "unknown", "25:00", "00:00 AM", "13:00 PM", "1:60 PM", "1:00:60 PM"]) assert.equal(auctionInstant(row("2026-08-25", time)), null);
});

test("결측·잘못된 날짜·시간대 없는 기준 시각은 추정하지 않음", () => {
  assert.equal(auctionDateTime(row("2026-08-25", ""), "KST").full, "2026-08-25 · 원문 ET · 시각 없음/확인 불가");
  assert.equal(auctionInstant(row("2026-02-30")), null);
  assert.equal(auctionDateTime(undefined, "KST").date, "N/A");
  for (const value of ["", "2026-02-30", "08/25/2026", undefined]) assert.equal(dateOnly(value), "N/A");
  assert.equal(dateOnly("2026-08-25T00:00:00"), "2026-08-25");
  assert.equal(displayInstant("2026-08-25T13:00:00", "KST").date, "N/A");
  assert.equal(displayInstant("badZ", "KST").time, "N/A");
});

test("표시 기준 시각과 일정 정렬·지나간 마감 제외", () => {
  assert.equal(displayInstant("2026-08-21T06:30:00Z", "ET").full, "2026-08-21 02:30 · 미국 동부 ET");
  const tomorrow = row("2026-08-26");
  const today = row("2026-08-25", "02:00 PM");
  const missingTime = row("2026-08-25", "");
  const past = row("2026-08-25", "11:30 AM");
  const input = [tomorrow, missingTime, today, past, row("2026-08-24", ""), row("invalid", "")];
  assert.deepEqual(scheduleRows(input, "2026-08-25T16:00:00Z"), [today, missingTime, tomorrow]);
  assert.equal(input.length, 6); // 원본 배열 변경 없음
  assert.deepEqual(scheduleRows([], "2026-08-25T16:00:00Z"), []);
});
