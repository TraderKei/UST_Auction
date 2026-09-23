# 데이터 수신 프로그램 실행·운영 절차

## 환경 및 설치

Python 3.12+, PostgreSQL 16+가 필요하다. 기존 Next/Vinext/D1 화면과 별도로 실행한다. UI 빌드, 화면 바인딩, HTTP 조회 API, 배포, 유료 데이터 접속은 포함하지 않는다. 패키지와 전이 의존성은 requirements.lock에 고정했고 테스트 의존성은 requirements-test.lock에 고정했다.

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env
```

이 컴퓨터에서는 `py` 대신 다음 번들 Python을 사용할 수 있다.

```powershell
& 'C:\Users\KOSCOM\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
```

`.env`의 `UST_DATABASE_URL`을 로컬 DB에 맞춰 설정한다. 예제에는 비밀번호가 없다. 필요한 비밀값은 로컬 `.env` 또는 세션 환경변수로만 제공한다. URL 비밀번호의 특수문자는 percent-encode한다. PowerShell 변수명으로 HOME/CODEX_HOME을 덮어쓰지 않는다.

| 설정 | 용도 | 기본값 |
|---|---|---|
| UST_DATABASE_URL | SQLAlchemy psycopg 접속 URL | postgresql+psycopg://ust_app@localhost:5432/ust_data |
| UST_RAW_ROOT | 원본 저장 루트 | data/raw |
| UST_USER_AGENT | 연락처를 포함할 수 있는 공개 UA | ust-auction-qra-pipeline/0.1 |
| UST_HTTP_TIMEOUT_SECONDS | HTTP 타임아웃 | 30 |
| UST_HTTP_MAX_RETRIES | 최초 요청 이후 재시도 횟수 | 4 |
| UST_HTTP_BACKOFF_BASE_SECONDS | 지수 backoff 기준 초 | 0.5 |
| UST_CA_BUNDLE | 조직 CA 파일(선택) | OS 신뢰 저장소 사용 |
| UST_QRA_REQUEST_DELAY_SECONDS | QRA 문서 요청 간격 | 1 |
| UST_AUCTION_PAGE_SIZE | API 한 페이지 행 수 | 1000 |
| UST_AUCTION_OVERLAP_DAYS | 증분 과거 겹침 구간 | 45 |
| UST_INITIAL_FROM_DATE / UST_INITIAL_TO_DATE | 설정에 둔 초기 권장 범위 | 1979-01-01 / 2099-12-31 |
| UST_LOG_LEVEL | 구조화 로그 레벨 | INFO |

429/5xx/timeout/network 오류는 제한된 지수 backoff 후 재시도한다. TLS 검증을 끄지 않는다. 조직망 인증서가 있으면 OS truststore 또는 지정 CA를 사용한다. raw는 날짜/내용 SHA-256 경로로 저장한다. XLS 본문은 `.bin` 확장자지만 BIFF 원본 bytes이고 MIME을 DB에 기록한다. 확장자가 아닌 문서 분류와 MIME으로 파서를 선택한다.

## DB 생성과 마이그레이션

PostgreSQL의 `bin` 경로를 PATH에 추가한 PowerShell에서 로컬 관리 계정으로 실행한다. 아래 DB/역할이 이미 있으면 생성 명령은 생략한다.

```powershell
createuser -U postgres --pwprompt ust_app
createdb -U postgres -O ust_app -E UTF8 ust_data
.\.venv\Scripts\ust-data.exe init-db
.\.venv\Scripts\alembic.exe current
```

`init-db`는 Alembic upgrade head를 실행한다. 재실행은 no-op이다. 빈 DB용 전체 DDL은 `db/ust_pipeline_schema.sql`, 마이그레이션은 `db/migrations/versions/20260903_0001_initial.py`다. SQL 직접 적용 시 `psql -v ON_ERROR_STOP=1 -1 -f db/ust_pipeline_schema.sql`로 트랜잭션 적용하고 Alembic 사용 전 `alembic stamp head`를 수행한다. 같은 DB에 DDL을 중복 적용하지 않는다.

검토용 SQL만 출력할 수도 있다.

```powershell
.\.venv\Scripts\alembic.exe upgrade head --sql > work/migration-preview.sql
```

## 초기 적재·증분

```powershell
.\.venv\Scripts\ust-data.exe backfill-auctions --from 2025-01-01 --to 2026-09-03
.\.venv\Scripts\ust-data.exe crawl-qra --backfill-from 2025
.\.venv\Scripts\ust-data.exe sync-auctions
.\.venv\Scripts\ust-data.exe crawl-qra --latest
.\.venv\Scripts\ust-data.exe sync-all
.\.venv\Scripts\ust-data.exe validate
```

초기 범위는 명령에서 명시적으로 선택한다. 환경변수의 권장 범위를 쓰려면 CLI 호출의 `--from/--to`에 해당 날짜를 전달한다. 증분은 오늘 UTC 기준 과거 overlap과 향후 45일의 공고를 재조회한다. record_date 최대값을 watermark로 사용하지 않는다. 오래된 정정은 해당 기간 backfill을 다시 실행해야 한다.

전체 초기 적재는 운영 창을 나누어 `backfill-auctions`를 과거부터 순차 실행하고, QRA는 확인하려는 공식 archive 시작 연도를 `--backfill-from`에 명시한다. 대량 실행 전 같은 명령에 `--dry-run`을 붙여 원천 접근·정규화·검증을 먼저 확인한다. 수집 명령은 공통 PostgreSQL advisory lock을 사용하므로 다른 수집이 실행 중이면 종료코드 1로 끝나며 기존 작업 종료 후 다시 실행한다.

모든 명령은 `--dry-run`(네트워크·정규화·검증만, DB/raw 쓰기 없음), `--verbose`를 지원한다. 예:

```powershell
.\.venv\Scripts\ust-data.exe backfill-auctions --from 2026-08-01 --to 2026-08-31 --dry-run
.\.venv\Scripts\ust-data.exe crawl-qra --latest --dry-run --verbose
```

| 종료코드 | 의미 | 조치 |
|---|---|---|
| 0 | SUCCESS 또는 DRY_RUN | 검토 필요 문서 수·품질 이슈도 확인 |
| 1 | 전체 실패/설정/접속/실행 충돌 | 접속정보·로그 확인 후 재실행 |
| 2 | validate 검증 실패 또는 잘못된 CLI 인자 | 품질검토 및 원천 대조 |
| 3 | PARTIAL_FAILURE | 정상 적재는 유지; 동일 구간 재실행 |

QRA의 HTTP 성공과 parser 검증 성공은 별개다. `documents_review_required`, document_version.parse_status 및 data_quality_issue를 함께 확인한다. 보조 PDF의 자동확정 실패는 공식 숫자로 승격하지 않는다. XML 일정의 HolidayName/HolidayDate 행은 공휴일이며 입찰 이벤트가 아니다.

## 실패 복구와 재처리

1. `ingestion_run`의 상태/오류와 checkpoint.last_completed_page, source_request를 확인한다. 실패 실행을 삭제하지 않는다. 프로세스 강제종료로 RUNNING이 남으면 실행 종료 확인 후 운영자가 상태를 FAILED로 변경하고 사유를 남긴다.
2. API 페이지 실패는 이전 성공 페이지를 보존한다. 페이지 사이 원천 내용이 바뀔 수 있으므로 재실행은 같은 날짜 구간 **첫 페이지부터** 수행한다. 업무키/hash upsert로 중복 없이 복구한다. 체크포인트는 안전한 완료 경계/진단 용도다.
3. QRA는 ETag/Last-Modified를 이용한다. 파서 버전이 달라지거나 성공한 문서 버전이 없는 URL에는 조건부 생략을 적용하지 않는다. 304 시 원문/현재 fact는 유지하고 요청 이력만 추가한다.
4. 파서 수정 후 `PARSER_VERSION`을 올려 같은 URL을 재수집한다. 새로운 추출 버전은 기존 원문 snapshot을 참조할 수 있다. 잘못된 새 PDF/표는 격리하고 직전 정상 fact는 유지한다.
5. 원본 파일을 수정하지 않는다. 원천이 A→B→A로 돌아오면 각 정정 순서를 남긴다. 손상 raw는 백업에서 복원하고 SHA-256을 대조한다.

`crawl-qra --latest`는 최신 QRA 문서군과 최신 공표 dealer survey를 발견한다. 둘의 조사·발표 시점은 다를 수 있다. `--backfill-from`은 공식 QRA 아카이브의 문서군별 페이지와 명시 연도/분기를 따른다. 오래된 표 형식은 새 파서 지원 전 REVIEW_REQUIRED/QUARANTINED일 수 있으며 자동 추정 적재하지 않는다.

## 조회 및 검증

```sql
SELECT * FROM ust.v_ingestion_status;
SELECT * FROM ust.v_auction_dashboard
WHERE auction_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
ORDER BY auction_date DESC;
SELECT * FROM ust.v_qra_supply_monitor ORDER BY refunding_year DESC,refunding_month DESC,normalized_security_term;
SELECT * FROM ust.v_qra_comparison;
SELECT * FROM ust.v_qra_tga_path ORDER BY observation_date;
SELECT * FROM ust.v_qra_dealer_outlook WHERE scenario='SIZE_EXPECTATION' AND statistic='TRIMMED_MEAN';
SELECT rule_code,severity,count(*) FROM ust.data_quality_issue WHERE resolution_status='OPEN' GROUP BY 1,2;
```

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
# 반드시 폐기 가능한 빈 테스트 DB를 사용한다. integration 테스트가 ust 스키마를 초기화한다.
$env:TEST_DATABASE_URL = 'postgresql+psycopg://ust_test@localhost:5432/ust_pipeline_test'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m integration
# 선택적 공식 원천 smoke: 특정 최신 숫자에 의존하지 않는다.
$env:RUN_LIVE_SMOKE = '1'
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider -m live tests_pipeline/test_live.py
```

fixture의 URL/수집일/SHA-256은 tests_pipeline/fixtures/MANIFEST.json, XML 필드 스키마는 tests_pipeline/fixtures/XML_SCHEMA.json에 있다. PDF 공급표·설문표는 원천 페이지/행/열을 검증한 경우에만 사용한다. UI 표본을 운영 DB seed로 넣지 않는다. 최종 검증 환경·명령·건수는 `docs/TEST_RESULTS.md`에서 확인한다.

## 백업·복구

```powershell
pg_dump -h localhost -U ust_app -d ust_data -Fc -f work/ust_data.dump
Copy-Item -LiteralPath data/raw -Destination work/raw_backup -Recurse
createdb -U postgres -O ust_app ust_data_restore
pg_restore -h localhost -U ust_app -d ust_data_restore --no-owner work/ust_data.dump
```

raw는 immutable이므로 증분 파일 백업 후 DB dump와 함께 보관한다. 복구 DB에 대해 validate를 수행하고 source_snapshot의 경로/hash를 대조한다. raw 루트를 변경하면 DB의 raw_storage_uri를 새 경로로 재매핑하는 관리 작업이 필요하다. 기존 UI 백업/태그/파일은 건드리지 않는다. 운영 보관기간/삭제는 별도 결정이며 수집 프로그램은 자동 purge를 하지 않는다.
