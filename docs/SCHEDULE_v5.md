# 입찰 일정 v5: 잠정 계획과 공식 공고

버전: `schedule_v5` · 화면: `UST_AUCTION_ui-baseline-v5.html` · 입수기: `scripts/acquire_tentative_schedule_v1.py` · 브라우저 병합 로직: `scripts/tentative_schedule_v1.js`.

기존 v4 HTML과 v3 화면·DB 계약은 보존한다. 이 문서는 v5의 일정 표시 계약과 재생성 절차를 기록한다.

## 원천과 갱신

| 상태 | 원천 | 표시 범위 | 제공 값 |
| --- | --- | --- | --- |
| 잠정 | [미 재무부 잠정 일정 XML](https://home.treasury.gov/policy-issues/financing-the-government/treasury-marketable-and-non-marketable-securities) | 조회일(UTC)부터 90일 이내이면서 XML의 `EndDate` 이내 | 입찰·발표·결제 예정일, 종류·만기·재발행 여부. 금액·마감 시각은 미제공이므로 `N/A`. |
| 공고 | Fiscal Data `auctions_query`의 결과 미발표 행 | 조회일(UTC)부터 90일 이내 | 공고된 금액·마감 시각과 일정. |
| 공고 보완 | [TreasuryDirect 공고 API](https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json)의 공고문 PDF와 발행액이 있는 행 | 조회일(UTC)부터 90일 이내 | Fiscal Data 반영이 늦은 공식 공고의 날짜·금액·마감 시각. 브라우저는 TreasuryDirect의 JSONP를 확인하고 실패하면 HTML에 포함된 수집 시점 공고를 사용한다. |
| 결과 | Fiscal Data `auctions_query`의 결과 발표 행 | 사용자가 선택한 결과 기간 | 확정 결과. |

2026-10-22 UTC에 공식 페이지가 가리킨 `Tentative-Auction-Schedule.xml`을 직접 수신했다. 213개 입찰 행, XML SHA-256 `c1f4049f6e94f994591f84f184a21ef3d41a61dd7ba6ce3a01dddd4edf9d2908`이며 보존된 2026 Q3 공식 fixture와 내용이 일치한다. XML의 마지막 날짜는 2027-01-30이다. v5 HTML은 이 XML과 같은 날 수집한 TreasuryDirect 공식 공고를 자체 포함하므로 `file://`로 열 때 수신 실패에도 확인된 일정은 남는다. 열 때마다 Fiscal Data 공고·결과와 TreasuryDirect 최신 공고를 다시 확인한다.

2026-10-22에는 4주물의 [10월 20일 공식 공고문](https://www.treasurydirect.gov/instit/annceresult/press/preanre/2026/A_20261020_1.pdf)이 확인되지만, Fiscal Data `auctions_query`에는 해당 행이 아직 없었다. 공식 공고문 기준 입찰일은 10월 22일, 발행액은 1,100억 달러다. 잠정 XML만으로 `잠정`으로 보였던 원인은 원천 간 반영 시차다. 공고문 PDF 파일명과 양의 발행액이 모두 있는 TreasuryDirect 행만 공식 공고로 인정하며, 공고 전 예약 행은 잠정으로 유지한다.

## 병합과 화면 표시

- 같은 입찰은 **원문 ET 입찰일 + 정규화 상품 종류 + 만기**로 맞춘다. 단기채는 이번 입찰의 `security_term`, 그 외 종목은 `original_security_term`을 우선 사용한다. 재개찰 단기채의 원래 만기는 이번 입찰 만기와 다를 수 있다. 잠정 XML에는 CUSIP이 없으므로 CUSIP 단독 결합을 하지 않는다.
- Fiscal Data 또는 TreasuryDirect에서 같은 입찰의 공식 공고를 받으면 잠정 행을 숨긴다. 두 원천에 같은 입찰이 있으면 Fiscal Data 행을 우선하고, 결과는 공고보다 우선한다. 잠정 행에 공고의 금액이나 시각을 추정해서 넣지 않는다.
- 잠정 행에는 `잠정` 배지를 표시한다. XML의 예정 공고일이 지났는데 같은 공식 행을 받지 못했다면 `공고 확인 필요`로 표시한다. 이것은 취소 판정이 아니라 재확인 신호다.
- ‘일정 한눈에 보기’ 달력은 당월에서 시작하고 단기채도 기본 표시한다. 범례와 월별 건수에서 `결과`, `공고`, `잠정`을 구분한다. 잠정 일정 칸과 범례는 차분한 회색 계열을 쓰며 밝은 테마에서도 같은 색을 사용한다. 좌측 상단 선택 입찰의 예정 배지는 채도를 낮춘 갈색과 흰색 글자를 사용하며 범례의 예정 색과 맞춘다. 달력 아래에는 링크 없이 잠정 일정 수집일과 변경 가능성을 안내한다. 단기채는 기존 체크박스로 숨길 수 있다.
- 영어 모드에서는 v5의 공고·잠정 상태, 달력 안내, 수집 상태 메시지와 언어 전환 버튼도 영어로 표시한다.
- 달력의 일정을 누르면 입찰 식별자와 입찰일이 모두 일치하는 일정표 행을 선택한다. 같은 만기의 다른 날짜를 대신 선택하지 않으며, 잠정 행의 좌측 선택 입찰 상태도 `잠정`으로 표시한다.
- v4 달력은 `단기채 제외`가 기본으로 켜져 있어 4·6·8·13주물 등이 보이지 않았다. v5는 이를 기본 표시하며, 공식 결과가 있는 단기채는 실제 입찰 만기로 표시한다. 단기채 결과 자체는 v4의 Fiscal Data 수집 대상이었다.
- Fiscal Data 요청이 실패해도 확정 결과를 만들어 내지 않는다. 상태 배너에 실패를 표시하면서 확인된 TreasuryDirect 공고와 수집일이 명시된 잠정 스냅샷을 일정으로 보여준다. XML이나 TreasuryDirect 공고 수집에 실패하면 입수기는 v5 HTML을 덮어쓰지 않는다.

## 갱신 명령

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
.\.venv\Scripts\python.exe scripts\acquire_tentative_schedule_v1.py
node --test tests\tentative-schedule-v1.test.mjs
```

입수기는 재무부 공식 페이지에서 현재 XML 링크를 찾고 TreasuryDirect 공식 공고를 함께 수집한다. HTTPS 인증서를 Windows 신뢰 저장소로 검증하고 XML 파싱·공고문 파일명·필수값·날짜 순서를 확인한 뒤 v5 HTML을 생성한다. 네트워크 없는 회귀검사는 `--fixture`로 2026 Q3 보존 원문을 사용한다. `--fixture`로 만든 HTML은 `capturedAt`이 2026-09-03으로 돌아가고 공식 공고 스냅샷이 비므로 배포용 갱신에는 쓰지 않는다.

재무부가 새 분기 잠정 일정을 발표하면 위 명령을 다시 실행한다. 보존된 v5 파일은 재실행 전까지 수집일이 고정된 스냅샷이며, 새 공고 데이터만 브라우저에서 새로 조회된다. `docs/DATA_REQUIREMENTS_AND_MAPPING.md`의 `ust_dashboard_v3` 계약과 PostgreSQL QRA 테이블은 이 버전의 파일 기반 UI와 별도다.
