# 실제 데이터 적재·가용성 감사

감사 시각: 2026-09-23 KST

공식 원천: 미국 재무부 Fiscal Data Auctions API 및 Treasury Quarterly Refunding 페이지/문서군

이 문서는 실제 원천에서 확인한 값, 운영 화면에 연결한 값, 원천 또는 환경 제약으로 제공할 수 없는 값을 구분한다. 숫자는 아래 감사 시각의 재현 가능한 실행 결과이며 이후 공식 발표와 정정으로 달라질 수 있다.

## 실제 적재 결과

| 영역 | 상태 | 범위·건수 | 검증 결과 |
|---|---|---|---|
| 입찰 사건 | AVAILABLE_AND_LOADED | 2025-01-02~2026-09-24, 763건 | 결과 757건, 공고 상태 6건, 업무키 중복 0 |
| 화면용 공식 API | AVAILABLE_AND_LOADED | 조회 범위 2024-09-23~2026-12-22, 결과 882건, 예정 6건 | 최신 결과 2026-09-22, 다음 수신 일정 2026-09-23 |
| QRA 문서 | AVAILABLE_AND_LOADED | 현재 문서 17개 | PARSED 11, REVIEW_REQUIRED/QUARANTINED 6 |
| QRA 차입 전망 | AVAILABLE_AND_LOADED | 3건 | 문서 version과 locator 연결 |
| 정례 입찰규모 | AVAILABLE_AND_LOADED | 102건 | Treasury 전망/실제와 권고 분리 |
| 만기별 공급 | AVAILABLE_AND_LOADED | 14건 | Gross/Maturing/Net 및 DV01 proxy lineage 검증 |
| Financing mix | AVAILABLE_AND_LOADED | 2건 | 산술 검증 통과 |
| TGA 앵커 | AVAILABLE_AND_LOADED | 4건 | 실제 시작·분기말 가정·peak만 저장 |
| 잠정 입찰 일정 | AVAILABLE_AND_LOADED | 2026-08-10~2027-02-02, 213건 | XML 우선, 공휴일 7건 제외 |
| 잠정 buyback | AVAILABLE_AND_LOADED | 2026-08-18~2026-11-05, 18건 | XML 구조화 및 날짜 검증 통과 |
| Dealer survey 값 | AVAILABLE_AND_LOADED | 450건 | 2026-04 조사월, 통계량·대상기간·locator 보존 |

첫 입찰 적재는 763건 INSERT였고 동일 범위를 재실행했을 때 763건 모두 UNCHANGED였다. QRA도 두 번째 실행에서 현재 문서 17개가 UNCHANGED였으며 변경되지 않은 원천은 HTTP 304를 사용했다. `ust-data validate`의 17개 무결성 검사는 모두 0건으로 통과했다.

## 화면 연결 결과

- 운영 화면은 `lib/treasury.ts`에서 Fiscal Data Auctions API의 실제 snake_case 필드를 조회한다.
- 과거 하드코딩 입찰 결과·예정 일정과 자동 fallback을 제거했다.
- API 실패 시 빈 상태와 실패 원인을 표시하며 표본을 실제 자료처럼 보여주지 않는다.
- 상품 유형은 `inflation_index_security`와 `floating_rate`를 이용해 TIPS/FRN을 구분한다.
- Bill/CMB, Note/Bond/TIPS, FRN별 Stop 필드를 구분한다.
- `allocation_pctage`를 Allotted at High KPI와 결과표에 연결했다.
- 화면에는 공식 원천, 조회 범위, 수신 시각을 표시한다.

현재 화면은 공식 API를 직접 조회하고, PostgreSQL은 전체 lineage·revision·QRA fact의 영속 저장 및 검증에 사용한다. 화면 API가 실패해도 DB 데이터를 자동으로 섞거나 오래된 값을 최신값으로 표시하지 않는다.

## 확보하지 못한 데이터

| 화면/기능 | 데이터 항목 | 상태 | 조사한 출처 | 미확보 원인 | 필요한 조건 | 공개 대체 데이터 | 처리 결과·재확인 |
|---|---|---|---|---|---|---|---|
| Stop 비교 | When-Issued 금리 | UNAVAILABLE_SOURCE | Fiscal Auctions, QRA | 공식 원천에 입찰 직전 거래금리 없음 | 시각이 명확한 허가된 시장 데이터 feed | 일별 국채 수익률은 시점·정의가 달라 대체 불가 | NULL; 시장 데이터 계약 시 재검토 |
| Stop 비교 | Tail | UNAVAILABLE_SOURCE | 위와 같음 | WI가 없어 Stop-WI 계산 불가 | WI feed | 없음 | NULL; Stop으로 대체 금지 |
| 시장 동향 | 실시간 2Y/10Y/30Y 금리 | REQUIRES_PAID_SOURCE | Fiscal/QRA 및 Treasury 공개 일별 금리 | 지정 공식 원천에 실시간 feed 없음 | 라이선스가 있는 실시간 시세원 | Treasury 일별 par curve는 실시간이 아님 | N/A; 출처·지연시간 승인 후 연결 |
| Dealer 전망 | 설문상의 현재 입찰액·변화율 | SOURCE_NULL | 2026-04 dealer survey PDF | 문서는 FY27 말 기대액을 제공하지만 현재액은 제공하지 않음 | 별도 현재 기준과 명시적 결합 규칙 | Fiscal 실제 offering amount는 설문 응답의 현재액과 의미가 다름 | NULL; 의미를 섞지 않음 |
| Dealer 전망 | 증액 개시일/분기 | SOURCE_NULL | dealer survey PDF | FY말 기대규모만 제공 | 일자를 명시한 후속 공식 자료 | 숫자 역산은 불가 | NULL; 새 설문마다 확인 |
| Dealer 전망 | 정확한 조사일 | SOURCE_NULL | survey archive/PDF | 조사월만 명시 | 일자를 명시한 공식 메타데이터 | URL 날짜는 확정 근거가 아님 | month precision으로 저장 |
| 잠정 입찰 | XML 미제공 발행액 | SOURCE_NULL | Tentative Auction XML | 일정 XML에 금액 요소가 없는 행 존재 | 향후 공고 또는 Policy Statement의 명시적 대응 | 유사 만기 금액은 대체 불가 | NULL; 공고 API 수신 후 별도 사건으로 적재 |
| TGA | 일일 전망 경로 | UNAVAILABLE_SOURCE | Financing Estimates/Policy Statement | 시작·분기말·peak 앵커만 제공 | 공식 일별 전망 경로 | Daily Treasury Statement는 실제 과거 잔고로 전망 경로가 아님 | 앵커만 표시; 보간 금지 |
| 보조 문서 | 6개 PDF 자동확정 | REVIEW_REQUIRED | Agenda/Charge/일정·buyback PDF | 신뢰할 표 구조가 없거나 의미 추출에 사람 검토 필요 | 수동 검토 또는 전용 parser | 일정·buyback은 companion XML 사용 가능 | PDF fact 미승격; 원본/hash 보존 |

## 재현 명령

```powershell
$env:UST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55435/ust_data'
$env:UST_RAW_ROOT='.\work\live-db\raw'
.\.venv\Scripts\ust-data.exe backfill-auctions --from 2025-01-01 --to 2026-11-07
.\.venv\Scripts\ust-data.exe crawl-qra --latest
.\.venv\Scripts\ust-data.exe validate

# 조직 TLS 중간 인증서가 있는 이 컴퓨터의 Node 실행
$env:NODE_USE_SYSTEM_CA='1'
pnpm dev
```

실데이터 DB와 raw 원본은 `.gitignore` 대상인 `work/live-db`에 있으며 비밀값·대용량 원본을 Git에 넣지 않는다.
