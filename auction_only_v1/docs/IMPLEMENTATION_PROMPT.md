# 입찰 전용 구현 사양

대상 UI는 저장소 루트의 `UST_AUCTION_ui-baseline-v3.html`이다. 이 화면의 입찰 결과, 예정 일정, 월간 캘린더를 Fiscal Data Auctions API의 공식 필드로 구현한다. 구현 계약은 이 디렉터리의 `DB_SPEC.md`, `DATA_REQUIREMENTS_AND_MAPPING.md`, `DATA_GAPS.md`와 `../db/auction_schema.sql`이다.

## 원천과 보관

- 공식 API: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query`.
- 모든 페이지를 수집하고 `meta`의 행수·페이지 수를 검증한다. 요청 실패·불완전 페이지·결과 0건을 표본 데이터로 덮지 않는다.
- 원본 응답·해시·요청 이력·정규화 레코드의 lineage를 보존한다.
- 업무키는 `(cusip, auction_date, issue_date)`이다. 같은 내용은 중복 이력을 만들지 않고, 정정은 revision으로 남긴다.
- 금액과 비율은 Decimal/NUMERIC으로 저장한다. 날짜는 DATE로 보존하고 ET의 실제 순간만 `America/New_York` DST를 적용한다.

## 화면 계약

- `v_auction_dashboard`의 `RESULT_AVAILABLE` 결과와 `ANNOUNCED` 공고를 구분한다. 결과 판정은 `bid_to_cover_ratio` 존재 여부를 따른다.
- 결과 필터는 사용자 기간과 상품·만기다. 예정 일정은 기준일 이상 90일 이내의 공식 공고만 표시한다. 월간 캘린더는 같은 사건의 중복을 제거하고 결과를 우선한다.
- 응찰배수 2.48은 DB에 2.48로 저장하고 UI에서는 248.0%로 표시한다. 24개월 평균·모집단 표준편차와 최근 6회 평균은 `DATA_REQUIREMENTS_AND_MAPPING.md`의 창 경계를 따른다.
- Stop은 Bill/CMB 할인율, Note/Bond/TIPS 수익률, FRN 할인마진을 사용한다. 참여자 비중은 accepted/total accepted로 계산한다.
- CUSIP는 내부 식별용이며 고객 화면에 표시하지 않는다. WI, Tail, 실시간 시장금리는 확인된 별도 원천이 생기기 전 N/A로 둔다.

## 실행과 검증

`../src/ust_auction_only`의 `init-db`, `backfill-auctions`, `sync-auctions`, `validate-auctions` 명령을 사용한다. 새 DB에만 `../db/auction_schema.sql`을 적용한다. `docs/VALIDATION.md`의 정적 검사와 유효한 PostgreSQL 연결에서 적재·무결성 검사를 수행한다.
