# UST Auction — 입찰 전용 v1

`UST_AUCTION_ui-baseline-v3.html` 구현을 위한 입찰 전용 데이터 명세와 실행 코드입니다. 기존 통합 파일은 이 디렉터리 밖에 원본 그대로 보존합니다. 화면 파일 자체는 이미 입찰 결과만 표시하므로 복제하지 않고 원본 v3를 기준으로 사용합니다.

## 이번 버전의 기준 파일

| 용도 | 파일 |
|---|---|
| DB 객체·컬럼·제약·조회 뷰 | [DB 명세](docs/DB_SPEC.md) |
| 실제 생성 SQL | [입찰 전용 DDL](db/auction_schema.sql) |
| 화면 필드 매핑 | [데이터 계약](docs/DATA_REQUIREMENTS_AND_MAPPING.md) |
| 공식 API 필드 자료형·라벨 | [API 필드 메타데이터](docs/API_FIELD_METADATA.md) |
| 미제공 데이터 | [데이터 갭](docs/DATA_GAPS.md) |
| 수집기 실행 | [운영 절차](docs/RUNBOOK.md) |
| 구현 요청용 사양 | [구현 프롬프트](docs/IMPLEMENTATION_PROMPT.md) |
| 검증과 이력 구분 | [검증 기록](docs/VALIDATION.md) |
| 새 버전 상태 | [구현 상태](docs/IMPLEMENTATION_STATE.md) |

실행 패키지는 `src/ust_auction_only`입니다. 새 PostgreSQL DB에 DDL을 적용하고 Fiscal Data Auctions API만 수집합니다. 기존 통합 DB에 있는 테이블을 삭제하거나 이전하지 않습니다. UI는 공식 API를 직접 읽으며 이 PostgreSQL 수집기의 결과를 자동으로 혼합하지 않습니다.

이 디렉터리는 기존 통합 코드의 독립적인 새 버전입니다. 기존 `README.md`, `docs/DB_SPEC.md`, `db/ust_pipeline_schema.sql`, `src/ust_pipeline` 및 역사적 증빙·목업은 변경하지 않았습니다. 이전 보고서는 과거 구현 기록이며 이번 입찰 전용 계약의 입력으로 사용하지 않습니다.
