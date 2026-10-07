# UST Auction/QRA 구현 상태

최종 갱신일: 2026-10-07 KST. 이 문서는 파일 존재가 아니라 현재 산출물, 재실행 결과, 보존된 공식 원천/통합검증 로그를 함께 기준으로 한다.

| Phase | 상태 | 완료 산출물 | 마지막 검증 | 남은 일/차단 원인 |
| ----- | ---- | ----------- | ----------- | ----------------- |
| 00 | COMPLETE | `docs/IMPLEMENTATION_STATE.md`, `work/phase-00/*` | 2026-09-07 offline 34 passed/6 skipped, DDL 61문 parse, UI hash 일치 | 없음 |
| 01 | COMPLETE | `docs/DATA_REQUIREMENTS_AND_MAPPING.md` 입찰 계약, `work/phase-01/*` | 2026-09-07 계약 15/15, phase tests 11 passed, offline 34 passed/6 skipped, UI hash 일치 | 없음 |
| 02 | COMPLETE | QRA 계약, `API_FIELD_METADATA.md`, `DATA_GAPS.md`, 공식 fixture/manifest | 실제 API 11,100행/3페이지 키 감사, QRA archive 9개 문서군 기록 | 없음 |
| 03 | COMPLETE | `pyproject.toml`, lock 2개, `.env.example`, 설정/로깅/CLI | Python 3.12.14, `pip check` 통과, 7개 subcommand help=0/잘못된 명령=2 | 없음 |
| 04 | COMPLETE | HTTP retry/host 제한, content-addressed raw, Fiscal pagination | 현 offline pagination/retry/304 통과; 2026-09-03 live 36행/4페이지 성공 | 없음 |
| 05 | COMPLETE | 입찰 Decimal 정규화/검증/파생 계산 | 현 offline Stop/NULL/0/비율/6회/DST 테스트 통과 | 없음 |
| 06 | COMPLETE | 감사·입찰 DDL/Alembic, upsert/revision/lineage, 입찰 views | 2026-09-03 PostgreSQL 16 포함 39 passed/1 live skip; 이후 DDL 차이는 QRA view뿐 | 없음 |
| 07 | COMPLETE | QRA discovery, host 범위, 조건부 요청, 문서 versioning | 현 offline 통과; 2026-09-03 제한 2026 backfill 44/44문서 성공·3 review | 없음 |
| 08 | COMPLETE | QRA HTML/XML/XLS 레이블 파서와 근거 locator | 현 공식 fixture/hash/XML/holiday/XLS 테스트 통과 | 없음 |
| 09 | COMPLETE | Treasury/TBAC/survey PDF semantic parser와 quarantine | 현 공급/mix/TBAC/survey/broken-PDF 회귀 테스트 통과 | 없음 |
| 10 | COMPLETE | QRA/derived 17개 테이블, 5개 QRA views, repository 적재, QRA 통합 회귀 | 2026-09-07 PG 16.15 phase tests 8 passed; offline 40 passed/1 live skipped; Alembic 재실행 no-op | 없음 |
| 11 | COMPLETE | CLI/pipeline 실행 관리, 범위별 validation, 실패 감사, `tests_pipeline/test_cli.py`, pipeline 회귀 | 2026-09-07 unit 44 passed/1 PG skip; PG 16 phase 42 passed; offline 73 passed/1 live deselected; Alembic first/no-op | 없음 |
| 12 | COMPLETE | 최신 `DB_SPEC.md`, `RUNBOOK.md`, mapping/gaps, `TEST_RESULTS.md`, README 링크, 최종 감사 로그 | 2026-09-07 unit 66 passed; PG 16 integration 7 passed; offline 73 passed/2 live deselected; live 2 passed | 없음 |
| 13 | COMPLETE | 안전한 demo loader, 27-table/8-view Excel, lineage/coverage/validation, `DEMO_DATA_GUIDE.md` | 2026-09-07 unit 2 passed; PG integration 5 passed; offline 80 passed/2 live deselected; Excel 41 sheets 재오픈 PASS | 공식 fixture에 없는 CMB·Note/Bond·TIPS·FRN Stop과 동일 CUSIP 두 번째 사건은 생성하지 않고 gap 기록 |
| 14 | COMPLETE | 실데이터 DB 적재, UI Fiscal Data 전환, 표본 fallback 제거, Allotted at High 연결, `ACTUAL_DATA_AVAILABILITY.md` | 2026-09-23 입찰 763건/재실행 763 unchanged, QRA 17문서 unchanged, DB validate 17/17 PASS, UI live 결과 882·예정 6 | WI/Tail/실시간 시장금리와 source-null 항목은 명시적 gap 유지 |
| 15 | COMPLETE | `UST_AUCTION_ui-baseline-v2.html` 기준 UI 보존형 공식 API 연결, 전체 pagination, 기존 결과 선택·필터·탭 유지, 실패 시 fail-closed | 2026-09-28 원본 SHA-256 복원 검증, JS syntax/CORS, desktop/mobile 렌더링, localhost 실제 클릭·콘솔 검증 | 연결 코드 제거 시 첨부 원본과 byte-for-byte 일치; 직접 실행용 CORS 확인 |
| 16 | COMPLETE | 최종 `UST_AUCTION_ui-baseline-v3.html` 범위에 맞춘 DB Spec·화면 매핑, v3 결과/예정 판정 migration | 2026-10-07 Node 60 passed, pipeline offline 68 passed, schema 2 passed/1 integration skipped, lint/build 통과 | QRA 스키마는 후속 제공용 보류 범위; v3 배포 선행조건 아님 |

## 산출물 신뢰 구분

- 현재 pipeline 계약/구현: `src/ust_pipeline`, `db/ust_pipeline_schema.sql`, Alembic, `tests_pipeline`, `docs/DATA_REQUIREMENTS_AND_MAPPING.md`, `API_FIELD_METADATA.md`, `DATA_GAPS.md`, `RUNBOOK.md`.
- `docs/DB_SPEC.md`는 PostgreSQL 16.15에 적용된 현재 DB catalog로 재생성했으며 27개 테이블과 8개 뷰를 모두 반영한다.
- 이전 UI/D1 참고 초안: 루트 `ARCHITECTURE.md`, `DATA_DICTIONARY.md`, `RUNBOOK.md`, `TEST_LOG.md`, `docs/API_AND_DB_DESIGN.md`, `db/treasury_auction_schema.sql`, `db/schema.ts`. 이 문서들은 스스로 실제 API/DB 미검증 범위를 밝히며 PostgreSQL pipeline의 권위 있는 명세로 사용하지 않는다.
- 저장소에는 감사 시작 전부터 다수의 미커밋/미추적 UI·pipeline 파일이 있었다. 되돌리거나 삭제하지 않았다. 적용 가능한 `AGENTS.md`는 없다.

## 확정 결정

- Python 3.12+, PostgreSQL 16+, SQLAlchemy/Alembic/httpx/pydantic/psycopg/lxml/xlrd/pdfplumber/pypdf; 잠긴 버전은 `pyproject.toml`과 `requirements*.lock`을 따른다.
- 금융 수치는 Python `Decimal`/PostgreSQL `NUMERIC`, USD 원 단위. 날짜는 `DATE`, 실제 순간은 `TIMESTAMPTZ`, ET 시각은 `TIME`+`America/New_York`; ET↔KST는 DST를 적용한다.
- 입찰 업무키는 `(cusip, auction_date, issue_date)`이며 `NULLS NOT DISTINCT`를 사용한다. 같은 typed content만 재적재하면 revision을 늘리지 않고 A→B→A는 이력으로 남긴다.
- 문자열 `"null"`/빈 문자열/JSON null은 typed NULL, 실제 0은 0이다. 결측 사유는 `SOURCE_NULL`, `NOT_APPLICABLE`, `NOT_CONNECTED`, `UNAVAILABLE_SOURCE`, `PARSE_FAILED`, `REVIEW_REQUIRED`로 구분한다.
- Stop은 Bill/CMB=`high_discnt_rate`, Note/Bond/TIPS=`high_yield`(TIPS real yield), FRN=`high_discnt_margin`. 응찰배수 2.48은 DB에 2.48, UI에서 248.0%다.
- 참여자 비중은 accepted/total_accepted×100, Other는 검증 가능한 입력에서만 UI 잔여 비중이다. 직전 비교는 동일 정규화 상품/만기, 평균은 현재 제외 최대 6개 유효값과 n이다.
- QRA 값은 Treasury actual/estimate, TBAC recommendation, dealer survey, UI proxy를 분리하고 모든 fact에 document version과 locator를 연결한다.
- `ui_proxy_v1` 가중치는 2Y .20, 3Y .30, 5Y .50, 7Y .70, 10Y 1.00, 20Y 1.65, 30Y 2.05이며 Treasury 공식 지표가 아니다.

## 공식 원천에서 확인한 구조

- Fiscal API는 snake_case 필드와 `meta.labels/dataTypes/dataFormats/total-count/total-pages`, `links`를 반환한다. 2026-09-07 최소 3개 키 필드 전체 감사는 11,106행, 3페이지, NULL 키 0, 중복 업무키 그룹 0이었다.
- 2026년 8월 제한 live 적재는 36행/4페이지 전부 성공했다. 공고 후 결과·정정 때문에 `record_date` 최대값 대신 겹침 구간을 다시 조회한다.
- QRA seed/archive에서 HTML, XML, legacy BIFF XLS, PDF를 동적으로 발견한다. 2026-09-07 live seed는 16개 링크와 유형별 문서 4건 HTTP 200을 확인했고, 기존 제한 backfill은 44/44문서 성공과 semantic review 3건이었다.
- Auction XML은 `AuctionCalendarDate`, Buyback XML은 `BuybackCalendarDate` 반복 구조이며 선택 요소는 NULL, holiday 행은 입찰 fact에서 제외한다.
- 2026년 4월 survey의 77.5는 1쪽 2-year / FY27 Year-End / MEAN이며 본문 정의는 trimmed mean이다. 현재액이나 증액 개시일로 사용하지 않는다.

## 재실행 명령과 데이터 갭

PHASE 13까지 완료됐다. 다음 `PHASE_ID`는 `NONE`이다.

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55434/ust_phase12'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m "not live" tests_pipeline
$env:RUN_LIVE_SMOKE='1'
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider -m live tests_pipeline/test_live.py
```

- WI와 Tail은 `UNAVAILABLE_SOURCE`, 2Y/10Y/30Y 실시간 시장금리는 `REQUIRES_PAID_SOURCE`다. 공개 일별 금리를 실시간 값으로 또는 Stop을 WI로 대체하지 않는다.
- dealer 현재액·변화율·증액 개시일은 공식 근거가 없으면 NULL이다. QRA XML의 미제공 발행액과 일일 TGA 연속경로도 만들지 않는다.
- 현재 로컬 실행환경: `.venv` Python 3.12.14, 보존된 PostgreSQL 16.15 binary/cluster 존재. PHASE 12 검증 포트는 `127.0.0.1:55434`이며 종료 시 서버를 정지한다.
- PHASE 10 UI 시작 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 10 UI 종료 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 11 UI 시작 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 11 UI 종료 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 12 UI 시작 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 12 UI 종료 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 13 UI 시작 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
- PHASE 13 UI 종료 SHA-256: `D5A19347BAF26EA48FFF6E159E7B0992FEA67481FBD146804F9FF2B62E5F1B4E`
