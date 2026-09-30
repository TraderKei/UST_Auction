# UST Auction — 다크 대시보드

## 입찰·QRA 데이터 수신 프로그램 (PostgreSQL)

Python 3.12+ / PostgreSQL 16 수집기와 DB는 공식 Fiscal Data·QRA 원천을 적재합니다. React 화면도 Fiscal Data Auctions API의 실제 데이터를 직접 읽으며, API 실패 시 하드코딩 표본으로 대체하지 않습니다. PostgreSQL은 전체 lineage·revision·QRA fact의 영속 저장과 검증에 사용합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env
# .env의 UST_DATABASE_URL을 생성한 로컬 PostgreSQL DB로 설정
.\.venv\Scripts\ust-data.exe init-db
.\.venv\Scripts\ust-data.exe backfill-auctions --from 2026-08-01 --to 2026-08-31
.\.venv\Scripts\ust-data.exe crawl-qra --latest
.\.venv\Scripts\ust-data.exe validate
```

산출물: [소스](src/ust_pipeline), [잠긴 의존성](requirements.lock), [환경 예시](.env.example), [DDL](db/ust_pipeline_schema.sql), [마이그레이션](db/migrations), [한글 DB 명세](docs/DB_SPEC.md), [화면 데이터 계약·매핑](docs/DATA_REQUIREMENTS_AND_MAPPING.md), [실제 API 필드 메타](docs/API_FIELD_METADATA.md), [설치·운영·복구](docs/RUNBOOK.md), [테스트 결과](docs/TEST_RESULTS.md), [데이터 갭](docs/DATA_GAPS.md), [자동 테스트](tests_pipeline).

현재 데이터 파이프라인 상태는 `docs/IMPLEMENTATION_STATE.md`와 `docs/TEST_RESULTS.md`, 실제 적재·미확보 항목은 `docs/ACTUAL_DATA_AVAILABILITY.md`를 기준으로 확인합니다.

## 데모 DB와 Excel 산출

잠긴 offline fixture를 운영 DB와 분리된 PostgreSQL 16 데모 DB에 적재하고, 27개 테이블과 8개 view의 실제 결과를 Excel로 내보낼 수 있습니다. 안전 경계와 sheet 설명은 [데모 데이터 가이드](docs/DEMO_DATA_GUIDE.md)를 확인하세요.

```powershell
$env:UST_DEMO_DATABASE_URL='postgresql+psycopg://ust_app@localhost:5432/ust_pipeline_demo'
.\.venv\Scripts\python.exe scripts\load_demo_database.py
.\.venv\Scripts\python.exe scripts\export_demo_workbook.py `
  --output artifacts\UST_Auction_QRA_DB_Demo.xlsx
```

현재 다크 화면과 기존 미커밋 변경을 함께 검사해 커밋 메시지 `feat: establish UST auction dashboard baseline`, 로컬 태그 `ui-baseline-v1`로 보존했습니다. 원격 저장소에는 push하지 않았습니다. 직접 확인·복원 절차는 `RUNBOOK.md`, 검사 기록은 `TEST_LOG.md`, 요구사항은 `REQUIREMENTS.md`에 있습니다. `ARCHITECTURE.md`와 `DATA_DICTIONARY.md`는 향후 단계용 관리 문서이며 최종 기술이나 DB 설계를 확정한 문서가 아닙니다.

기존 다크 HTML 목업의 배치와 색상을 현재 React 화면에 반영했습니다. 실행 기술을 다른 것으로 교체한 것은 아닙니다. 실행 기준은 이 폴더의 `app/page.tsx`와 `app/AuctionDashboard.tsx`입니다.

## 먼저 알아둘 점

- 이전 `.codex/.chatgpt-projects/.../ust-auction-dashboard.html`은 별도 파일입니다. 그 파일을 새로고침해도 현재 프로젝트의 수정은 보이지 않습니다.
- 저장소의 `UST_AUCTION_ui-baseline-v2.html`은 첨부 기준 화면의 디자인·레이아웃·탭 구성을 그대로 유지하면서 Fiscal Data API 결과를 기존 카드·차트·표에 연결합니다. 앱과 같은 명목채 만기별 필터를 제공하며, 인터넷 연결이 없거나 API가 실패하면 과거 표본으로 대체하지 않고 기존 영역에 수신 실패를 표시합니다.
- 이 프로젝트는 **로컬 주소 `http://localhost:3000/`**에서 확인합니다. 서버가 실행 중이어야 열립니다.
- 화면의 응찰률은 백분율만 표시합니다. 예: API의 원본 배수 2.48 → 화면의 248.0%. 배수와 백분율을 별도 지표로 중복 표시하지 않습니다.
- 화면은 Fiscal Data Auctions API의 최근 730일과 향후 90일 범위를 조회합니다. 요청 실패·불완전 pagination·결과 0건이면 빈 상태와 원인을 표시하고 과거 표본을 보여주지 않습니다.
- Allotted at High는 공식 `allocation_pctage`에 연결했습니다. When-Issued, Tail, 실시간 Market Context는 검증된 원천이 없어 N/A이며 Stop이나 일별 금리로 대체하지 않습니다.
- 화면에 포함된 `API 필드` / `데이터 구조` 문구는 기존 참고 설계입니다. 검증된 파이프라인 계약은 `docs/API_FIELD_METADATA.md`, `docs/DB_SPEC.md`를 따릅니다.
- CUSIP는 화면에서 제거했으며 내부 식별 데이터는 보존했습니다. Price는 상단 KPI에서 제거하고 하단 결과표의 `낙찰가격`은 유지했습니다.
- 기본 시각은 한국 KST입니다. 상단 버튼으로 미국 동부 ET로 바꿀 수 있습니다. 모든 날짜는 YYYY-MM-DD이며, 시각이 없는 날짜는 임의 변환하지 않고 `원문 ET`를 표시합니다. 새로고침하면 기본 KST로 돌아갑니다.

## 현재 컴퓨터에서 실행하기

PowerShell(명령어 입력 창)에서 아래를 실행합니다. 이미 설치된 도구를 사용하며 새 설치는 필요 없습니다.

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
$env:PATH = 'C:\Users\KOSCOM\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
$env:NODE_USE_SYSTEM_CA = '1' # 조직 TLS 중간 인증서가 있는 현재 컴퓨터
pnpm dev
```

`Local: http://localhost:3000/` 안내가 나오면 해당 주소를 브라우저에서 엽니다. 초기 실행에 시간이 걸릴 수 있습니다. 포트가 사용 중이면 명령 창에 나온 실제 주소를 이용합니다. 종료는 해당 명령 창에서 `Ctrl+C`입니다.

위 경로는 **현재 컴퓨터 기준**이며 `$env:PATH` 변경은 해당 명령 창에만 적용됩니다. 다른 컴퓨터의 개발 환경 준비는 이후 승인된 단계에서 정리합니다.

## 기준 버전 확인과 안전한 복원

현재 작업 폴더를 변경하지 않고 기준 버전을 확인합니다.

```powershell
git status --short --branch
git show --stat --oneline ui-baseline-v1
git tag --points-at ui-baseline-v1
```

기준 화면을 별도 폴더에서 확인하는 가장 안전한 방법은 분리된 worktree를 만드는 것입니다. 기존 작업 파일은 덮어쓰지 않습니다.

```powershell
git worktree add --detach '..\US_Treasury_Auction_ui-baseline-v1' ui-baseline-v1
```

생성된 폴더에서 이 README의 실행 명령을 사용합니다. 현재 폴더를 과거 상태로 강제 변경하는 `reset --hard`는 사용하지 않습니다. 이미 같은 확인 폴더가 있거나 현재 변경을 실제로 되돌려야 한다면 먼저 변경을 별도 커밋·복사로 보존한 뒤 진행합니다.

## 화면 확인 순서

1. `http://localhost:3000/`을 새로고침합니다. `UST AUCTION`, `입찰 결과`, 짙은 남색 배경을 확인합니다.
2. KPI 순서는 응찰률 → High Yield (Stop) → 간접낙찰률 → 직접낙찰률 → PD낙찰률 → Allotted at High입니다. 두 번째 카드 이름은 상품에 맞게 바뀝니다(물가연동채: 실질금리).
3. `2년`~`30년` 만기 필터에서 실제 최근 명목 중·장기채 결과를 선택하고 응찰률·Stop·낙찰 비중·Allotted at High가 같은 공식 레코드에서 표시되는지 확인합니다. 2년 FRN과 10년·20년·30년 TIPS는 각각 별도 종류 필터에만 표시됩니다. 비교 자료가 없으면 `비교 자료 없음`입니다.
4. 하단에 최근 결과표와 수신된 예정 일정표가 함께 있는지 확인합니다. ET 경쟁마감 시각은 DST를 반영해 KST로 전환하고, 결제일처럼 시각이 없는 날짜는 `원문 ET`로 유지합니다.
5. 창 폭을 줄여 6개 KPI가 3열 또는 2열로, 차트가 세로로 배치되는지 확인합니다. 긴 표는 내부 스크롤로 조회합니다. 자료 기준 시각과 시간대 버튼은 작은 화면에서도 표시됩니다.

## 검사 명령

위와 같이 폴더 및 PATH를 설정한 다음 실행합니다.

```powershell
pnpm test:ui
pnpm test
pnpm lint
```

- `test:ui`: 인터넷 요청 없이 표시·계산·서머타임·날짜 경계 등 25개 검사
- `test`: 실행용 빌드와 총 38개 화면·standalone HTML 회귀검사. 테스트 입력은 네트워크와 분리된 합성 레코드이며 운영 fallback 데이터로 사용되지 않습니다.
- `lint`: 코드 작성 규칙 검사
- 전체 TypeScript 형식 검사에는 기존 Cloudflare/DB 형식 선언 오류 3개가 남아 있습니다. 자세한 내용은 `TEST_LOG.md`에 기록했습니다.

기존 화면 작업 기록은 `PROJECT_STATUS.md`와 `TEST_LOG.md`, 데이터 파이프라인의 검증 결과는 `docs/TEST_RESULTS.md`를 확인하세요. QRA 화면 바인딩과 외부 배포는 이번 범위에 포함되지 않습니다.
