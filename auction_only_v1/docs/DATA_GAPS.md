# 데이터 갭·출처 한계 — 입찰 전용 v1

| 항목 | 상태 | 처리 |
|---|---|---|
| When-Issued 금리 | UNAVAILABLE_SOURCE | Fiscal Data 입찰 API에 직전 WI 시세가 없어 NULL 유지 |
| Tail | UNAVAILABLE_SOURCE | WI가 없어 Stop−WI 계산 불가; Stop으로 대체하지 않음 |
| 2Y/10Y/30Y 실시간 시장금리 | NOT_CONNECTED | 공식 입찰 API에 실시간 시세가 없어 N/A 유지 |
| 최근 수집 범위 밖 정정 | RESYNC_REQUIRED | 해당 기간을 `backfill-auctions`로 다시 적재 |

공식 원천: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query
