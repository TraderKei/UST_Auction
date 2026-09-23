# PHASE 12 최종 검증 결과

검증일: 2026-09-07 KST. 대상은 Python 3.12.14, PostgreSQL 16.15, migration `20260903_0001`이다. 네트워크 검증은 미국 재무부 공식 호스트에 대한 제한된 읽기 요청으로 수행했다. 전체 원본 본문과 큰 출력은 `work/phase-12/`에 보존했다.

## 실행 결과

| 검증 | 결과 | 근거 로그 |
|---|---|---|
| 단계 단위 테스트 | PASS — 66 passed, 0 failed, 8 integration/live deselected | `work/phase-12/unit-tests.txt` |
| PostgreSQL integration | PASS — 7 passed, 0 failed, 68 non-integration deselected | `work/phase-12/postgres-integration.txt` |
| 전체 offline suite | PASS — 73 passed, 0 failed, 2 live deselected | `work/phase-12/offline-full.txt` |
| 제한 live smoke 최종 | PASS — 2 passed, 0 failed, 0 skipped | `work/phase-12/live-smoke-final.txt` |
| fixture manifest | PASS — 13개 파일 URL/수집일/MIME/byte/SHA-256 일치 | `work/phase-12/fixture-manifest-audit.json` |
| 잠긴 Python 의존성 | PASS — `pip check`: No broken requirements | `work/phase-12/pip-check.txt` |
| Alembic offline SQL | PASS — 33,504 bytes, 27 tables, 8 views | `work/phase-12/migration-offline.sql` |
| 빈 DB migration 및 재실행 | PASS — 최초 upgrade 성공, 두 번째 no-op 성공 | `work/phase-12/migration-first.txt`, `migration-second.txt` |
| PostgreSQL catalog/뷰 | PASS — 27 tables, 390 columns, 156 constraints, 70 indexes, 8 views; 모든 뷰 SELECT 성공 | `work/phase-12/catalog-audit-final.txt` |
| 최종 DB validation | PASS — 입찰·QRA 17개 규칙 모두 이슈 0, 종료코드 0 | `work/phase-12/cli-validate.txt` |
| 화면 계약·DB·gap 대조 | PASS — 27/27 tables, 8/8 views, 화면 계약 32/32, gap 8/8 | `work/phase-12/document-contract-audit.json` |
| UI 무변경 | PASS — 외부 기준 HTML 시작/종료 SHA-256 동일, 저장소 UI 경로 `git diff --` 0 bytes | `work/phase-12/ui-hash-start.txt`, `ui-hash-end.txt`, `ui-git-diff.patch` |

첫 live smoke 시도는 공식 HTTP 응답을 받은 뒤 테스트 출력의 `date` JSON 직렬화와 소문자 HTML doctype 처리 때문에 2 failed였다(`work/phase-12/live-smoke.txt`). 테스트를 원천 형식에 맞게 수정한 뒤 같은 제한 범위를 한 번 재검증해 2 passed로 끝났다. 실패를 원천 장애나 parser 성공으로 기록하지 않았다.

## 공식 원천 live 확인

- Fiscal API: 2026-08-01~2026-08-31 구간에서 `meta.total-count=36`, `meta.total-pages=18`; 첫 두 페이지의 total count/pages가 일치했다. 필수 업무키가 존재했고 첫 행을 `date`/`Decimal` 모델로 정규화했다.
- QRA seed: HTTP 200, 동적 링크 16개를 발견했다. anchor/URL로 분류한 Financing Estimates HTML(78,790 bytes), Auction XML(74,558), Quarterly Release legacy XLS(203,264), TBAC Recommended Financing PDF(247,561)를 각각 HTTP 200과 파일 시그니처로 확인했다. 특정 최신 수치는 단정하지 않았다.
- 전체 후보키 감사: 최소 필드 `cusip,auction_date,issue_date`, page size 5,000으로 API 전체를 한 번 순회했다. 11,106행/3페이지, 11,106 distinct keys, 키별 NULL 0, 중복 그룹 0이었다. 페이지별 raw hash/경로는 `work/phase-12/candidate-key-audit.json`에 있다.

## Idempotency·정정·격리

실제 PostgreSQL 테스트에서 동일 입찰 공고 2회는 revision을 늘리지 않았고, 공고→결과→공고(A→B→A)는 내용 변경마다 revision을 추가했다. 같은 CUSIP의 별도 재발행 사건은 별도 업무키로 유지됐다. QRA 동일 fixture 2회는 document version/current fact를 늘리지 않았고, 검증된 B와 다시 A로 바뀐 경우에만 version이 증가했다. 중간 quarantined 문서는 직전 정상 fact를 삭제하지 않았다. 관련 테스트는 다음과 같으며 모두 통과했다.

- `test_announcement_result_reversion_and_same_cusip_reopening`
- `test_qra_twice_with_lineage_classes_corrections_and_quarantine`
- `test_database_fk_unique_and_check_enforcement`
- `test_postgresql_advisory_lock_serializes_collectors`

## 원 요청 완료 기준

| 기준 | 상태 | 확인 내용 |
|---|---|---|
| UI 원본 불변 | PASS | 기준 SHA-256 `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E` 유지. 시작부터 untracked였던 저장소 HTML은 되돌리거나 수정하지 않음 |
| Fiscal 실제 필드·메타·pagination | PASS | live smoke와 전체 후보키 3페이지 감사 |
| QRA 동적 발견·유형별 원본 처리 | PASS | 공식 seed에서 HTML/XML/XLS/PDF 발견·다운로드; fixture parser 회귀 통과 |
| backfill·overlap·idempotent 정정이력 | PASS | CLI/pipeline 및 실제 PostgreSQL A→B→A 회귀 통과 |
| 원문/typed, NULL/0, 날짜/시각, value class 분리 | PASS | 정규화·DST·lineage·QRA authority 테스트 통과 |
| PostgreSQL 16 DDL·migration·뷰 | PASS | 빈 DB 실제 적용, 재실행 no-op, 모든 제약/뷰 integration 통과 |
| 모든 화면 요소의 DB/gap 연결 | PASS | 화면 계약 32개와 읽기 모델 8개 대조 누락 0 |
| 출처 없는 값 미생성 | PASS | float 0, WI/Tail/시장금리 컬럼 0; dealer current/delta 근거 없으면 NULL |
| 동일 입력 중복 방지 | PASS | 입찰 revision/QRA version/current fact 실제 DB 회귀 통과 |
| 운영·DB 한글 문서 | PASS | `DB_SPEC.md`, `RUNBOOK.md`, mapping, gap, README 링크 갱신 |

## 재실행 명령

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
.\.venv\Scripts\python.exe -m pip check
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55434/ust_phase12'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m "not live" tests_pipeline
$env:RUN_LIVE_SMOKE='1'
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider -m live tests_pipeline/test_live.py
.\.venv\Scripts\alembic.exe upgrade head --sql
```

## 남은 데이터 갭

When-Issued와 Tail은 `UNAVAILABLE_SOURCE`, 2Y/10Y/30Y 실시간 시장금리는 `NOT_CONNECTED`다. Dealer 현재 입찰액·변화율·증액 개시일은 공식 field-level 근거가 없으면 NULL이다. QRA XML 미제공 발행액과 일일 TGA 연속 경로도 추정 생성하지 않는다. 상세 상태와 근거는 `DATA_GAPS.md`를 따른다.
