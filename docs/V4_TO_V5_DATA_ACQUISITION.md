# v4 → v5 변경 사항: 데이터 입수

비교 대상은 `UST_AUCTION_ui-baseline-v4.html`과 `UST_AUCTION_ui-baseline-v5.html`이다. 이 문서는 **원천 수신, 검증, 저장, 병합**에 초점을 둔다. 화면에서 데이터를 표현하는 변경은 [화면 렌더링 문서](V4_TO_V5_SCREEN_RENDERING.md)에 정리했다. v5 HTML은 수작업으로 수정하는 파일이 아니라 `scripts/acquire_tentative_schedule_v1.py`가 v4와 별도 스크립트를 조합해 생성한 결과물이다.

## 핵심: 잠정 입찰 일정의 입수

| 단계 | v4 | v5 |
| --- | --- | --- |
| 원천 | 브라우저의 Fiscal Data `auctions_query`로 결과와 공식 공고를 조회 | 기존 조회에 더해 미 재무부 [잠정 일정 XML](https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml)을 생성 시점에 수집 |
| XML 발견 | 없음 | [재무부 증권 안내 페이지](https://home.treasury.gov/policy-issues/financing-the-government/treasury-marketable-and-non-marketable-securities)에서 현재 XML 링크를 찾고, HTTPS·호스트·확장자를 확인 |
| 파싱·검증 | 해당 없음 | `parse_auction_xml`로 반복 행을 읽고 달력 이름·종료일, 입찰일·종류·만기, 공고일과 입찰일의 순서를 확인 |
| 보관 | 잠정 계획 없음 | 원천 URL·SHA-256·수집일·`calendarEnd`·입찰 행을 `ust-tentative-schedule-v1` JSON으로 v5 HTML에 포함 |
| 갱신 | 화면을 열 때 기존 API 조회 | 잠정 XML은 **입수기를 다시 실행해야** 갱신된다. 화면을 열 때 XML을 다시 받지는 않음 |

XML 행은 `auctionDate`, `announcementDate`, `settlementDate`, `type`, `term`, `tips`, `floating_rate`, `reopening`으로 축약된다. XML에 없는 발행액과 경쟁입찰 마감 시각은 만들지 않는다. 원천 수집·변환은 `scripts/acquire_tentative_schedule_v1.py`의 `source_bytes`와 `snapshot_from_xml`에서 수행한다. XML 파싱이나 필수 검증이 실패하면 v5 HTML을 새로 쓰기 전에 중단한다.

현재 저장된 v5 수집본의 수집일은 **2026-10-22 UTC**이고 XML 행은 213건이다. 원본 XML의 가장 늦은 `AuctionDate`는 **2027-02-02**(6주물 Bill)인 반면 루트 `EndDate`는 **2027-01-30**이다. v5 병합 함수는 `auctionDate > calendarEnd`인 행을 제외하므로, 2월 2일 행은 **수집본에는 있으나 화면 일정에는 나타나지 않는다**. 화면은 별도로 조회일(UTC)부터 90일 이내의 행만 표시한다. `EndDate`와 행의 입찰일이 불일치하는 것은 현재 원천 및 구현의 범위 차이이며, `EndDate`를 마지막 실제 입찰일로 해석하면 안 된다.

## 기타 데이터 입수 변경

### TreasuryDirect 공식 공고로 보완

v5 생성 시 [TreasuryDirect 예정 입찰 API](https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json)도 수집해 `announcedRows`와 수집일을 HTML에 포함한다. 화면 실행 중에는 같은 API를 JSONP로 다시 조회하고, 요청이 실패하거나 6초 안에 응답하지 않으면 포함된 공고 스냅샷을 사용한다. 잠정 XML과 달리 공식 공고에는 브라우저 재조회 경로가 있다.

공고문 PDF 파일명이 `A_YYYYMMDD_N.pdf` 형식이고 CUSIP·만기·입찰일·공고일이 있으며 발행액이 양수인 행만 공식 공고로 인정한다. 공고 전 예약 행은 공식 공고로 승격하지 않는다. 이렇게 확인된 행은 Fiscal Data 반영이 늦은 경우에만 보완한다. 둘 다 같은 입찰을 제공하면 Fiscal Data 행을 우선한다. 생성 단계의 검증은 `announced_rows_from_treasury_direct`, 브라우저 단계의 검증·보완은 `scripts/tentative_schedule_v1.js`의 `treasuryDirectRow`와 `__UST_AUGMENT_OFFICIAL__`에 있다.

### 공식 자료와 잠정 자료의 병합

브라우저 병합은 **원문 ET 입찰일 + 상품 종류 + 정규화 만기**를 동일 입찰의 키로 사용한다. 잠정 XML에는 CUSIP이 없다. 단기채의 공식 행은 이번 입찰의 `security_term`을 우선하고, 그 외 종목은 `original_security_term`을 우선한다. 재발행 단기채의 이번 만기와 최초 발행 만기가 다를 수 있기 때문이다. TIPS와 FRN도 별도 종류로 정규화한다.

Fiscal Data 결과 또는 공식 공고가 동일 키로 존재하면 잠정 행을 제외한다. 남은 잠정 행에는 `tentative: true`를 붙이고, 예정 공고일이 지났으면 `tentativeUnconfirmed: true`를 붙인다. 이는 확인 필요 표시이며 취소 판정이 아니다. 잠정 행의 `offeringAmount`는 `null`, `closingTimeCompetitive`는 빈 문자열이다. 결과, 공고, 잠정의 우선순위와 날짜 필터는 `__UST_MERGE_TENTATIVE__`가 적용한다.

### 실패 시 데이터 경로와 저장 범위

Fiscal Data 수신에 성공하면 TreasuryDirect 보완 행과 잠정 행을 더해 화면에 전달한다. 로컬 캐시에는 **Fiscal Data에서 받은 행만** 저장한다. Fiscal Data 수신에 실패하면 기존 캐시 또는 검증된 결과 표본에 TreasuryDirect 공고와 잠정 스냅샷을 합친다. 결과 표본도 사용할 수 없으면 확인된 공고와 잠정 일정만 전달하며 확정 결과를 생성하지 않는다. 이 경로는 v5 HTML의 `standalone-live-data-script`에 있다.

## 재생성 및 확인

```powershell
.\.venv\Scripts\python.exe scripts\acquire_tentative_schedule_v1.py
node --test tests\tentative-schedule-v1.test.mjs
```

`--fixture`는 보존된 2026 Q3 XML을 이용하는 오프라인 회귀검사용이다. 이 옵션은 수집일을 과거 fixture 날짜로 바꾸고 TreasuryDirect 공고 스냅샷을 비우므로 배포용 최신 수집에 사용하지 않는다. 관련 구현은 `scripts/acquire_tentative_schedule_v1.py`, `scripts/tentative_schedule_v1.js`, 검증은 `tests/tentative-schedule-v1.test.mjs`에 있다.
