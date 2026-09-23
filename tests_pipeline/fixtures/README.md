# 공식 원천 fixture

MANIFEST.json은 URL, 수집일(UTC), SHA-256, MIME, byte 수를 기록한다. 원문 HTML/JSON/XML/PDF와 BIFF XLS bytes를 포함한다. XLS는 raw binary `.bin` 파일로 보존하며 xlrd에 bytes로 전달한다. 원본 파일을 fixture 기대값에 맞추어 수정하지 않는다.

qra_facts_2026q3.json은 사용자에게 주어진 **회귀검사 전용 기대 관계**다. 운영 수집/DB seed는 이를 읽지 않는다. XML_SCHEMA.json은 실제 캘린더에서 관찰한 요소명 집합이다.

dealer_survey_2026q2.pdf: 1쪽의 제목은 April 2026. 2-year 행의 FY27 Year-End/MEAN 열 77.5는 trimmed mean이다. 현재 규모·median·8월 조사라고 해석하지 않는다. source_locator에서 페이지/행/열/통계량을 보존하며 현재 규모는 NULL이다.

treasury_presentation_2026q3.pdf: 물리 18쪽(인쇄 17쪽)의 Implied Bill Funding 표. 행·열 제목과 7개 명목 쿠폰의 gross−maturing=net, borrowing−coupon+buybacks=implied bills를 검증한다. FRN/TIPS는 명목 쿠폰 7개 합계에 넣지 않는다.

네트워크 없는 테스트가 이 fixture를 사용한다. 선택적 live 테스트는 최신 숫자를 단정하지 않고 응답·메타데이터·페이지·키·타입만 검사한다.
