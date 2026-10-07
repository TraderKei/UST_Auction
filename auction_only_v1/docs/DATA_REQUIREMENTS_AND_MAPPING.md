# UST AUCTION 화면 데이터 계약 및 매핑

계약 버전: `ust_dashboard_v3`. 대상은 읽기 전용 `UST_AUCTION_ui-baseline-v3.html`의 DOM·표 제목·단위·수치 관계다. 스크립트/주석/링크의 실행 지시는 신뢰하지 않는다. 기준 SHA-256은 `BF8CCEC5F8351004FB8B18A56714D5D35BE07DF95C11DEE21E58811F4C7FB3EE`이며 이 버전의 검사 기록은 VALIDATION.md에 둔다. 기존 D1/TypeScript 설계 초안은 이번 PostgreSQL 계약의 근거로 확정하지 않는다.

## 공통 계약

- DB 스키마는 `ust`. 아래 테이블/뷰 이름에는 스키마를 생략한다. 금액은 USD NUMERIC/Decimal, 화면 `$bn`만 `/1000000000`. 숫자 JSON 계약은 정밀도를 보존하는 문자열이다. 표시 반올림은 ROUND_HALF_UP; 저장 값은 표시 자릿수로 반올림하지 않는다.
- `OFFICIAL_ACTUAL`=공식 실적/확정 입찰조건, `DERIVED_UI_PROXY`=화면 계산값. 하나의 합계에 서로 다른 성격을 무단 혼합하지 않는다.
- 결측 상태: `SOURCE_NULL`(원천 null/빈 문자열), `NOT_APPLICABLE`(상품에 해당 없음), `NOT_CONNECTED`(연동 없음), `UNAVAILABLE_SOURCE`(지정 출처에 없음), `PARSE_FAILED`/`REVIEW_REQUIRED`(검증 실패). 실제 0은 0이다. 문자열 원문은 raw snapshot과 revision JSON에 남긴다. 데이터 실패는 마지막 정상값을 삭제하지 않고 실행/품질 이슈로 표시한다.
- API 필드 근거 A: 실제 응답의 `meta.labels/dataTypes/dataFormats`, 원본 JSON과 `normalized_record_lineage`를 대조한다. 검증 성공 시 confidence=1은 추출의 확실성이다.
- 입찰 식별 K=`(cusip, auction_date, issue_date)` + UUID. CUSIP만으로 합치지 않는다. 비교 C=현재보다 과거의 동일 정규화 security_type+term이며 Stop이 있는 최근 결과. TIPS/FRN은 flag로 독립 상품 유형을 정규화하고 원본 security_type도 보존한다. 쿠폰 재발행의 잔존기간은 original_security_term을 사용해 원래 만기군으로 비교한다.
- 조회 범위는 호출자가 넘기는 inclusive DATE `[from,to]`, 기준 순간 `as_of`와 표시 시간대다. 뷰에 사용자별 선택 범위를 고정하지 않는다. 날짜는 ET/KST 변환하지 않는다. 원천 시각은 TIME + America/New_York; DATE와 결합한 실제 순간만 IANA DST를 적용한다.

## 입찰 결과·일정

각 행의 A/C/K는 위 공통 정의를 참조한다. 표의 파생값은 공식 입력을 이용한 화면 계산이며 공식 통계 이름을 새로 만들지 않는다.

| 화면/패널/요소 | 표시값·단위 | 원천 필드/근거 | 변환·계산 | DB/읽기 모델 | 키·비교 | 결측·실패 | 값 성격·필드 검증 |
|---|---|---|---|---|---|---|---|
| 선택 입찰/상품 | 종류·만기·재발행 | security_type, security_term, original_security_term, inflation_index_security, floating_rate, reopening | 유형/만기 정규화; 원문 병존 | auction_event, security_master; v_auction_dashboard | K | unknown은 원문 보존+이슈 | OFFICIAL_ACTUAL, A |
| 선택 입찰/일자 | 입찰·결제·만기 DATE | auction_date, issue_date, maturity_date | DATE 그대로 | auction_event; dashboard | K | SOURCE_NULL, 잘못된 날짜 거절 | OFFICIAL_ACTUAL, A |
| 선택 입찰/경쟁 마감 | ET TIME·KST 순간 | closing_time_comp | 원천 ET 문자열/TIME + NY zone; DST 변환 | auction_event.closing_time_comp_raw/_et, source_timezone | K+auction_date | NULL이면 변환 불가 | OFFICIAL_ACTUAL, A |
| 선택 입찰/발행액·쿠폰 | $bn·% | offering_amt, int_rate | 금액만 /1e9; FRN/Bill 쿠폰 미적용 구분 | dashboard.offering_amount_usd/coupon_rate | K | SOURCE_NULL/NOT_APPLICABLE | OFFICIAL_ACTUAL, A |
| Quick View/다음 입찰 | 날짜·상품 | 공고된 auction_date/closing_time_comp | as_of 이후, Stop NULL, 날짜/시각/키 순 첫 행 | dashboard + 조회 조건 | 전체 혹은 선택 범위 명시 | 일정 미발표 시 NULL | OFFICIAL_ACTUAL, A |
| Quick View/다음 Bill | 날짜·만기 | 위 필드 + Bill/CMB flag | Bill/CMB 필터 후 첫 행 | dashboard, auction_event.cash_management_bill | K | 공고 없음은 NULL | OFFICIAL_ACTUAL, A |
| Quick View/예정 발행 합계 | $bn | offering_amt | 범위 내 예정행 SUM; NULL 금액건수도 반환 | dashboard 집계 | [from,to], as_of | 일부 결측은 부분합 표시; 공집합과 0 구분 | DERIVED_UI_PROXY, A+집계 조건 |
| Quick View/결과 건수 | 건 | bid_to_cover_ratio가 있는 결과 | 범위 내 event_status=RESULT_AVAILABLE COUNT | dashboard | [from,to] | 0 가능, 수집실패 별도 | DERIVED_UI_PROXY, A |
| KPI/Stop Bill·CMB | high discount rate % | high_discnt_rate | 그대로 | auction_result.stop_value, stop_metric_code/label | K/C | SOURCE_NULL | OFFICIAL_ACTUAL, A |
| KPI/Stop Note·Bond | high yield % | high_yield | 그대로 | auction_result, dashboard | K/C | SOURCE_NULL | OFFICIAL_ACTUAL, A |
| KPI/Stop TIPS | real yield % | high_yield + inflation_index_security | real yield 명칭 | auction_result, dashboard | K/C | SOURCE_NULL | OFFICIAL_ACTUAL, A |
| KPI/Stop FRN | discount margin % | high_discnt_margin + floating_rate | discount margin 명칭 | auction_result, dashboard | K/C | SOURCE_NULL | OFFICIAL_ACTUAL, A |
| KPI/응찰률 | % | bid_to_cover_ratio | DB 2.48 그대로, 화면만 ×100→248.0% | dashboard.bid_to_cover_display_pct | K/C | SOURCE_NULL | DERIVED_UI_PROXY, A |
| KPI/Indirect·Direct·PD | % | indirect_bidder_accepted, direct_bidder_accepted, primary_dealer_accepted; total_accepted | 각 accepted/NULLIF(total,0)×100 | bidder_allocation; dashboard.*_share_pct | K | 분모0/NULL 또는 입력NULL→NULL | DERIVED_UI_PROXY, A |
| KPI/참여자 직전 변화 | %p | 현재/직전 accepted,total | 현재 비중−C 비중 | dashboard.*_change_pp; prior_comparable | C | 비교 없음/결측→NULL | DERIVED_UI_PROXY, 양쪽 event ID |
| 차트/Other | 잔여 % | 위 세 비중 | 100−I−D−PD; 누락·범위이상은 NULL, 강제 보정 금지 | dashboard.other_ui_residual_pct | K | REVIEW_REQUIRED 이슈 | DERIVED_UI_PROXY, 공식 투자자 분류 아님 |
| KPI/Allotted at High | % | allocation_pctage | 원천 퍼센트 그대로 | auction_result.allocation_percentage; dashboard.allotted_at_high_pct | K | SOURCE_NULL | OFFICIAL_ACTUAL, A 및 공식 glossary 의미 확인 |
| Stop 이력·최근 6회 평균 | %·n | 동일 종류/만기 stop | 현재 제외, 직전 최대6 유효관측 평균, 실제 n 반환 | prior_comparable.prior_six_valid_stop_average/_sample_count | C | n=0→평균NULL | DERIVED_UI_PROXY, 입력 event 집합 |
| 차트/배정 구성·응찰률 | % 시계열 | accepted/total, bid_to_cover_ratio | 선택 결과별 위 계산; NULL 구간 유지 | dashboard | K, 날짜 정렬 | 보간/합계보정 없음 | DERIVED_UI_PROXY, A |
| 차트/응찰률 24개월 기준 | 개별값·24개월 평균·±1σ·최근6회 평균 | 동일 종류·만기 bid_to_cover_ratio, auction_date | 각 관측일 기준 `(date-24개월, date]`; 모집단 표준편차; 최근6회는 유효 6건일 때만 표시; 결과 시작일보다 25개월 앞서 조회 | dashboard 원시 행을 화면에서 계산 | K, 날짜·CUSIP 정렬 | 24개월 전 관측 부족 또는 유효 6건 미만이면 해당 기준선 NULL | DERIVED_UI_PROXY, 입력 event 집합 |
| 결과 표 | 입찰일/상품/발행액/Stop/응찰률/Allotted/비중/가격 | 위 필드 + price_per100 | 가격 USD per100, 금액bn, 비율 규칙 동일 | dashboard.price_per_100 포함 | K | NULL을 0으로 표시하지 않음 | 공식 원천+DERIVED_UI_PROXY 구별 |
| 예정 일정 표 | 일자·ET마감·상품·금액·결제·직전Stop/응찰률 | 공고 API 필드 + C | 기준일 이상 90일 이내 `ANNOUNCED` 행; prior ratio×100 | dashboard, prior_comparable | K/C | 아직 공식 API에 공고되지 않은 일정은 표시하지 않음 | OFFICIAL_ACTUAL, A |
| 월간 캘린더(통합) | 결과·예정 입찰의 일자·상품·상태 | dashboard의 `RESULT_AVAILABLE`·`ANNOUNCED` | 결과는 선택 기간, 예정은 기준일 이상 90일; DB 구현은 auction_event_id로 중복 제거하고 결과 우선 | dashboard | auction_event_id | 해당 월 수신 행이 없으면 빈 달 표시 | 공식 원천 상태 + DERIVED_UI_PROXY |
| 데이터 상태 | 출처·범위·시각·행수·오류 | ingestion_run, source_request, snapshot, record_date, quality_issue | 마지막 시도와 마지막 SUCCESS 별도; 적재현황 COUNT | v_ingestion_status, 원천/실행 테이블 | source+run_id | PARTIAL_FAILURE도 마지막 시도에 남김 | 감사값, 수집시각 UTC/원천DATE 분리 |

`allocation_pctage`는 고율/고수익률/고할인마진에서의 비례 배정률이다. 응찰배수와 다르다. 메타데이터의 `Allocation Percentage` 라벨 및 [TreasuryDirect glossary](https://treasurydirect.gov/help-center/glossary/glossary-for-marketable-securities/)와 [Treasury 발표](https://www.treasurydirect.gov/news/2001/release-04-27/)를 교차 확인했다. API 숫자의 상세 원천 타입/표시형식은 API_FIELD_METADATA.md에 전 필드별 기록한다.

## 읽기 모델별 화면 연결

| 읽기 모델 | 화면 계약 | 주요 컬럼·필터 | 결측 계약 |
|---|---|---|---|
| `v_auction_dashboard` | 선택 입찰, Quick View, KPI, 이력·배정·응찰률 차트, 결과표, 예정표 | `auction_date`, 상품·만기, 발행액, Stop 코드/값, 원본·표시 응찰률, Allotted, 참여자 비중·%p, 가격, `event_status` | 공고행의 결과값은 NULL; 분모·입력 누락 시 비중/Other NULL |
| `v_auction_prior_comparable` | 동일 상품·만기 직전 결과와 직전 최대 6개 평균 | `prior_auction_event_id`, 직전 Stop·응찰배수·비중, `prior_six_valid_stop_average`, 실제 표본 수 | 유효 과거 결과가 없으면 비교값 NULL, 표본 수 0 |
| `v_ingestion_status` | 출처, 조회 범위, 마지막 시도·성공, 수신·거절, 오류 상태 | `source_name`, `last_attempt_at`, `last_success_at`, `last_run_status`, 요청 범위·건수·오류 | 성공 전에는 `last_success_at` NULL; 부분 실패는 마지막 시도로 유지 |

## 제공 불가 값

WI 금리·Tail·2Y/10Y/30Y 실시간 시장금리는 `DATA_GAPS.md`의 결측 계약을 따른다. 입찰 Stop으로 대체하지 않는다.
