# UST Auction/QRA 데모 DB와 Excel

이 문서는 잠긴 offline fixture를 별도 PostgreSQL 16 데모 DB에 적재하고, `ust` schema의 모든 테이블과 SQL view를 하나의 Excel로 내보내는 절차를 설명한다. 운영 DB 또는 기존 사용자 DB에는 실행하지 않는다.

## 데모 DB 준비

새 빈 DB 이름에는 `demo` 또는 `test`가 반드시 포함돼야 한다. loader는 `UST_DEMO_DATABASE_URL`만 입력으로 사용하며 다음 경우 적재 전에 실패한다.

- DB 이름에 `demo`/`test`가 없음
- `UST_DATABASE_URL`과 `UST_DEMO_DATABASE_URL`이 같음
- PostgreSQL 16 미만
- 미확인 테이블·뷰가 있거나, `DEMO_FIXTURE` 이력이 없는 비어 있지 않은 DB

빈 DB에는 Alembic migrations `20260903_0001`–`20261007_0002`를 `upgrade head`로 적용한다. 이미 확인된 `DEMO_FIXTURE` DB에는 같은 fixture를 재실행해도 current fact, auction revision, QRA document version과 lineage가 증가하지 않는다. loader는 DROP, TRUNCATE를 수행하지 않는다.

예시:

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
$env:UST_DEMO_DATABASE_URL='postgresql+psycopg://ust_app@localhost:5432/ust_pipeline_demo'
.\.venv\Scripts\python.exe scripts\load_demo_database.py --dry-run
.\.venv\Scripts\python.exe scripts\load_demo_database.py
```

종료코드는 성공 0, DB/fixture 검증 실패 2, 연결·실행 실패 1이다. `--dry-run`은 URL, DB 안전 상태, PostgreSQL 버전과 fixture manifest만 확인하고 migration이나 데이터를 쓰지 않는다.

## fixture 출처와 데모 구분

원문은 `tests_pipeline/fixtures/MANIFEST.json`의 13개 공식 fixture다. manifest의 URL, 2026-09-03 UTC 수집일, byte size와 SHA-256을 매번 재검증한다.

- Fiscal Data Auctions API JSON 2개 페이지: 2026년 8월 Bill 4건
- QRA seed/archive HTML, Financing Estimates/Policy HTML
- Tentative Auction/Buyback XML
- Quarterly Release BIFF XLS
- Treasury Presentation, TBAC Recommendation, Primary Dealer Survey PDF

모든 원문은 `RawStore`로 content-addressed 저장되고 `source_request` → `source_snapshot` → revision/document version/fact로 연결된다. 적재 실행은 `ingestion_run.source_name='DEMO_FIXTURE'`로 식별한다.

동일 내용 no-op, A→B→A, quarantine 보존 검증은 감사 이력으로 분리한다. A→B→A QRA 검증은 fact를 생성하지 않는 index document version에서 수행한다. quarantine 검증은 새 fact를 승격하지 않고 직전 공식 borrowing fact가 남는지만 확인한다. 입찰 공고 상태는 공식 fixture 행에서 결과 필드를 제거하는 기술 projection이며, 임의 숫자는 추가하지 않고 `data_quality_issue`에 명시한다.

## Excel 생성

```powershell
$env:UST_DEMO_DATABASE_URL='postgresql+psycopg://ust_app@localhost:5432/ust_pipeline_demo'
.\.venv\Scripts\python.exe scripts\export_demo_workbook.py `
  --output artifacts\UST_Auction_QRA_DB_Demo.xlsx
```

Excel은 DB catalog에서 테이블·뷰 목록을 읽기 때문에 객체 수를 하드코딩하지 않는다. 현재 migration 결과는 테이블 27개, 뷰 8개다. NUMERIC은 15자리 Excel 정밀도 손실을 피하기 위해 정확한 문자열, UUID는 문자열, DATE는 Excel 날짜, TIMESTAMPTZ는 timezone 포함 ISO-8601 문자열, TIME은 Excel 시각으로 기록한다. JSON/ARRAY는 키 정렬 JSON 문자열이다. 원천 문자열이 `=`, `+`, `-`, `@`로 시작하면 formula injection을 막기 위해 apostrophe를 붙인다. 매크로와 외부 링크는 만들지 않는다.

## sheet 구성

| sheet | 내용 |
|---|---|
| `00_README` | 생성 UTC/KST, DB/migration, value class, NULL/0, UI proxy·시장데이터 한계 |
| `01_TABLE_INDEX` | 모든 테이블의 목적, 행 수, sheet명, PK/UQ, 갱신·보관 정책 |
| `02_VIEW_INDEX` | 모든 view의 화면 연결, 행 수, 계산과 결측 처리 |
| `03_COLUMN_COVERAGE` | 모든 테이블·컬럼의 타입/단위/NULL/non-null/실제 0/예시/전부 NULL 사유 |
| `04_LINEAGE_TRACE` | 화면 요소에서 fact ID, revision/version, raw URL·SHA-256·저장경로·locator까지 추적 |
| `05_VALIDATION` | repository 검증, idempotency 변화, 테이블·뷰 조회 결과 |
| `T_*` | 27개 테이블의 실제 조회 결과 |
| `V_*` | 8개 SQL view의 실제 조회 결과 |

긴 객체명은 Excel 31자 제한에 맞춰 안정적인 hash suffix로 줄인다. 원래 DB 객체명과 sheet명은 index에 기록한다. 각 데이터 sheet의 1행은 실제 DB 컬럼 순서이며, header comment에 한글 설명·타입·단위·NULL·원천을 넣는다. 필터와 `A2` freeze pane을 적용한다.

## 운영 데이터와의 차이 및 공식 데이터 갭

이 DB는 2026-09-03에 고정된 offline 회귀 fixture다. 최신 운영 데이터가 아니며 UI HTML의 표본값을 사용하지 않는다.

- fixture의 입찰 결과는 Bill 4건뿐이다. CMB, Note/Bond, TIPS, FRN Stop과 같은 CUSIP의 두 번째 실제 사건은 만들지 않고 품질 이슈/coverage gap으로 표시한다.
- WI, Tail, 2Y/10Y/30Y 실시간 시장금리는 출처가 없어 제공하지 않으며 Stop으로 대체하지 않는다.
- Dealer survey의 `current_auction_size_usd`, `calculated_pct_change`, `expected_increase_timing`과 일 단위 조사일은 공식 field-level 근거가 없어 NULL이다.
- QRA XML이 제공하지 않는 발행액과 일일 TGA 연속 경로는 추정하지 않는다.
- `ui_proxy_v1`은 `net_issuance_usd × tenor_weight`인 화면 proxy이며 Treasury 공식 DV01가 아니다.

## 삭제 없이 다시 실행

기존 데모를 보존하려면 새 빈 DB를 만든 뒤 URL의 DB 이름만 바꾼다. 기존 DB를 DROP/TRUNCATE/DELETE하거나 같은 이름을 재사용해 초기화하지 않는다.

```powershell
$env:UST_DEMO_DATABASE_URL='postgresql+psycopg://ust_app@localhost:5432/ust_pipeline_demo_2'
.\.venv\Scripts\python.exe scripts\load_demo_database.py
.\.venv\Scripts\python.exe scripts\export_demo_workbook.py `
  --output artifacts\UST_Auction_QRA_DB_Demo.xlsx
```
