# 입찰 전용 v1 구현 상태

- 기준 UI: 저장소 루트의 `UST_AUCTION_ui-baseline-v3.html`.
- 명세: 이 디렉터리의 `DB_SPEC.md`, `DATA_REQUIREMENTS_AND_MAPPING.md`, `API_FIELD_METADATA.md`, `DATA_GAPS.md`.
- 독립 실행 경로: `../src/ust_auction_only`와 `../db/auction_schema.sql`.
- 정적 검증: SQL 문법 파싱, 10개 테이블·3개 뷰의 명세 대응, Python 모듈 로드, CLI 명령 계약.
- 운영 검증: 새 별도 PostgreSQL DB의 생성·적재·조회는 아직 수행하지 않았다. 대상 DB가 준비되면 `RUNBOOK.md`의 순서로 실행하고 결과를 기록한다.

원본 통합 구현의 과거 적재·테스트 결과는 이 버전의 운영 검증으로 간주하지 않는다.
