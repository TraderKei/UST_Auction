# 입찰 전용 수집기 운영 절차

## 준비

Python 3.12 이상과 PostgreSQL 16 이상이 필요합니다. 저장소 루트의 기존 `.venv`와 `requirements.lock`을 사용할 수 있습니다. `auction_only_v1/.env.example`의 설정을 참고해 세션 환경변수 또는 로컬 `.env`에 접속 정보를 둡니다. `.env`는 Git에 올리지 않습니다.

입찰 전용 DDL은 **빈 별도 DB**에 적용합니다. 이미 통합 스키마가 있는 DB에서는 `init-db`를 실행하지 않습니다. `UST_DATABASE_URL`이 별도 DB를 가리키는지 확인한 뒤 아래 명령을 사용합니다.

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
$env:PYTHONPATH='auction_only_v1/src'
$env:UST_DATABASE_URL='postgresql+psycopg://ust_app@localhost:5432/ust_auction_only'
.\.venv\Scripts\python.exe -m ust_auction_only --dry-run init-db
.\.venv\Scripts\python.exe -m ust_auction_only init-db
```

`init-db`는 새 DB의 `ust` 스키마를 생성합니다. 기존 통합 Alembic 이력은 이 버전에 적용하지 않습니다. 같은 DDL을 두 번 적용하지 않습니다.

## 적재·검증

```powershell
.\.venv\Scripts\python.exe -m ust_auction_only backfill-auctions --from 2025-01-01 --to 2026-10-07
.\.venv\Scripts\python.exe -m ust_auction_only sync-auctions
.\.venv\Scripts\python.exe -m ust_auction_only validate-auctions
```

`sync-auctions`는 UTC 오늘을 기준으로 과거 45일과 향후 45일을 조회합니다. 그보다 오래된 정정은 해당 기간을 `backfill-auctions`로 다시 적재합니다. 원본 응답은 `UST_RAW_ROOT`의 내용 해시 경로에 저장되고, 실행·요청·품질 이슈는 DB에 남습니다. `--dry-run`은 네트워크로 응답을 받아 정규화·검증하되 DB와 raw 저장소에는 쓰지 않습니다.

수집 실패나 검증 실패 시 출력의 상태와 `ust.ingestion_run`, `ust.data_quality_issue`를 확인합니다. `v_ingestion_status`는 마지막 시도와 마지막 성공을 분리합니다. 검증된 원천이 없으면 WI, Tail, 실시간 금리는 채우지 않습니다.
