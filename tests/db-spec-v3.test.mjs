import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("DB spec identifies v3 as the current customer-screen contract", async () => {
  const [spec, mapping] = await Promise.all([
    read("docs/DB_SPEC.md"),
    read("docs/DATA_REQUIREMENTS_AND_MAPPING.md"),
  ]);

  assert.match(spec, /현재 화면 계약은 `UST_AUCTION_ui-baseline-v3\.html`/);
  assert.match(mapping, /계약 버전: `ust_dashboard_v3`/);
  assert.match(mapping, /BF8CCEC5F8351004FB8B18A56714D5D35BE07DF95C11DEE21E58811F4C7FB3EE/);
  assert.doesNotMatch(mapping.split("\n", 3).join("\n"), /baseline-v2/);
});

test("DB spec covers the v3 calendar and bid-to-cover history rules", async () => {
  const [spec, mapping] = await Promise.all([
    read("docs/DB_SPEC.md"),
    read("docs/DATA_REQUIREMENTS_AND_MAPPING.md"),
  ]);

  for (const expected of ["월간 캘린더", "24개월", "모집단 표준편차", "25개월", "ANNOUNCED", "RESULT_AVAILABLE"]) {
    assert.ok(spec.includes(expected), `DB spec: ${expected}`);
    assert.ok(mapping.includes(expected), `mapping: ${expected}`);
  }
});

test("DB spec defers QRA without deleting future schema or exposing technical tabs", async () => {
  const [spec, readme] = await Promise.all([
    read("docs/DB_SPEC.md"),
    read("README.md"),
  ]);

  assert.match(spec, /QRA 공급 기능은 v3 배포 범위에서 제외/);
  assert.match(spec, /기존 `qra_\*` 테이블과 `v_qra_\*` 읽기 모델은 향후 제공을 위한 보류 스키마/);
  assert.match(readme, /`API 필드`와 `데이터 구조`는 고객 화면에 노출하지 않으며/);
});

test("database event status follows the v3 bid-to-cover result rule", async () => {
  const [schema, migration, spec] = await Promise.all([
    read("db/ust_pipeline_schema.sql"),
    read("db/migrations/versions/20261007_0002_align_v3_event_status.py"),
    read("docs/DB_SPEC.md"),
  ]);

  for (const source of [schema, migration, spec]) {
    assert.match(source, /bid_to_cover_ratio IS NULL/);
  }
  assert.doesNotMatch(schema, /CASE WHEN r\.stop_value IS NULL THEN 'ANNOUNCED'/);
  assert.match(spec, /`20260903_0001`–`20261007_0002`/);
});
