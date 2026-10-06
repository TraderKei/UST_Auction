import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlUrl = new URL("../UST_AUCTION_ui-baseline-v3.html", import.meta.url);

test("v3 keeps only the auction-results top-level navigation", async () => {
  const html = await readFile(htmlUrl, "utf8");
  const staticNavigation = html.match(/<nav class="nav" aria-label="주요 메뉴">[\s\S]*?<\/nav>/)?.[0] ?? "";

  assert.match(staticNavigation, />입찰 결과<\/button>/);
  assert.doesNotMatch(staticNavigation, /입찰 일정|QRA 공급|API 필드|데이터 구조/);
  assert.match(html, /children:\(0,A\.jsx\)\(`button`,\{className:`active`,"aria-pressed":!0,children:`입찰 결과`\}\)/);
});

test("v3 removes QRA and customer-facing technical reference views", async () => {
  const html = await readFile(htmlUrl, "utf8");

  for (const removed of [
    "qra-integration-styles",
    "qra-integrated-view",
    "qra-integration-script",
    "QRA 공급",
    "API 필드 안내",
    "데이터 구조 안내",
    "원천 자료와 화면 값의 대응",
    "저장 구조 참고안",
  ]) {
    assert.ok(!html.includes(removed), removed);
  }
});

test("v3 retains schedules inside auction results", async () => {
  const html = await readFile(htmlUrl, "utf8");

  assert.match(html, /예정 입찰 일정/);
  assert.match(html, /auction-month-calendar-script/);
  assert.match(html, /입찰 완료/);
  assert.match(html, /입찰 예정/);
  assert.match(html, /standalone-live-data\.js/);
});
