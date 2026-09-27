# 데이터 갭·출처 한계

| 항목 | 상태 | 제공/비제공과 근거 |
|---|---|---|
| When-Issued 금리 | UNAVAILABLE_SOURCE | Fiscal Auctions 및 QRA에 입찰 직전 WI 시세 없음. NULL 유지 |
| Tail | UNAVAILABLE_SOURCE | WI가 없으므로 Stop−WI 계산 불가. Stop으로 대체하지 않음 |
| 2Y/10Y/30Y 실시간 시장금리 | REQUIRES_PAID_SOURCE | 지정 공식 출처에 실시간 시세 feed 없음. 공개 일별 par curve는 시점·정의가 달라 대체하지 않음 |
| Dealer 표 77.5의 통계량 | VERIFIED_DIFFERENT_CONTEXT | 2026년 **4월** 공식 survey PDF 1쪽 2-year 행, **FY27 Year-End / MEAN**=77.5bn. 본문 정의는 trimmed mean. 8월 조사·median으로 사용하면 안 됨 |
| Dealer 현재액·변화율 | SOURCE_NULL | 설문표의 FY27 말 기대액은 현재 실적이 아님. 현재액을 입찰자료와 별도 기준으로 연결하기 전 NULL. 변화율도 NULL |
| Dealer 증액 개시일 | SOURCE_NULL | 해당 survey는 FY말 기대규모와 범위를 제공. 개시일/분기는 숫자에서 역산하지 않음 |
| Dealer 조사 일자 | SOURCE_NULL | 제목에 조사월만 명시. survey_as_of_date=NULL, survey_as_of_month와 MONTH precision 저장. URL의 날짜를 조사일이라고 확정하지 않음 |
| 8월 Quarterly Release XLS의 dealer 표 | NOT_APPLICABLE | 실제 7개 sheet는 평균만기·발행구성·만기도래·차입 등 부채 통계. dealer 표본을 이 XLS 출처로 연결하지 않음 |
| 일일 TGA 연속 경로 | UNAVAILABLE_SOURCE | 이번 자료는 실제 시작 잔고와 분기말/peak 가정의 앵커만 제공. 사이 일자를 보간한 실적 시계열을 만들지 않음 |
| TGA late October peak 일자 | PERIOD_ONLY | 월말 대표 DATE로 정렬하되 원문 late-month 구간을 source_locator에 보존. 특정 날짜의 공식 관측값이 아님 |
| QRA 잠정 일정의 발행액 | SOURCE_NULL | XML이 액수를 제공하지 않는 경우 NULL. 다른 표에서 유사 만기를 찾아 자동 채움하지 않음 |
| 보조 PDF 6개 | REVIEW_REQUIRED / QUARANTINED | 2026-09-23 live 적재에서 Agenda/Charge/일정·buyback PDF의 자동확정 보류. raw/hash 보존; 일정·buyback은 companion XML을 우선 사용 |
| DV01 | DERIVED_UI_PROXY | ui_proxy_v1은 화면의 Net×만기가중치. 실제 채권 DV01/금리 민감도나 재무부 공식 통계라고 해석하지 않음 |
| 최근 구간 밖의 입찰 정정 | RESYNC_REQUIRED | overlap 밖 정정은 기간 backfill 재실행으로 반영. record_date 최대값만으로 완전성 주장하지 않음 |

공식 원천: [Fiscal API](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query), [QRA seed](https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents), [survey archive](https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/quarterly-refunding-archives/primary-dealer-auction-size-survey), [4월 2026 survey PDF](https://home.treasury.gov/system/files/221/auction_survey_20260427.pdf). 원천 파일과 hash는 fixture manifest에 고정되어 있다.

2026-09-23부터 운영 UI는 Fiscal Data 공식 API를 직접 조회하며 표본 fallback을 사용하지 않는다. 실제 적재 건수, 화면 연결 범위, 필요한 외부 조건과 공개 대체 데이터의 차이는 [ACTUAL_DATA_AVAILABILITY.md](ACTUAL_DATA_AVAILABILITY.md)를 따른다.
