# Altibase 입찰 JSON 텍스트 저장 설계안

> 상태: 설계안. 현재 저장소의 PostgreSQL 기반 `db/ust_pipeline_schema.sql`과 별개이며, 아래 다섯 테이블의 Altibase DDL 및 배치는 아직 구현되지 않았다. 실제 Altibase 버전·문자셋·드라이버에서 타입과 제약을 확인한 뒤 적용한다.

## 1. 결정 사항과 저장 단위

- API 결과를 매일 수집하되, **입찰일 전체 JSON을 새 버전으로 교체하지 않는다.** 신규 입찰은 추가하고, 기존 입찰의 내용이 달라진 경우에만 **그 입찰 1건**의 새 버전을 만든다.
- 원본 파일은 별도 보관하지 않는다. API의 **페이지별 응답 원문**은 `API_FETCH_CHUNK`에, 화면에서 읽을 **개별 입찰 JSON 객체**는 `AUCTION_DAY_CHUNK`에 텍스트로 저장한다. JSON/LOB 컬럼과 Base64는 사용하지 않는다.
- 모든 `JSON_TEXT` 값의 **UTF-8 인코딩 길이는 3,600바이트 이하**다. 컬럼은 `VARCHAR(3600)`을 권장한다. 한글 등 멀티바이트 문자 중간에서 자르지 않는다. DB 문자셋이 UTF-8이 아니면 실제 DB 인코딩 길이도 별도로 검사한다.
- API가 제공하는 필드는 `cusip`, `auction_date`, `issue_date` 각각이다. 세 값의 **조합을 업무키로 쓰는 것은 수집 프로그램의 규칙**이다. `SNAPSHOT_ID`는 이 업무키가 아니라, 입찰 1건의 특정 저장 버전에 부여하는 고유번호다.
- `AUCTION_DATE`는 API의 미국 기준 입찰일을 그대로 보존한다. KST로 날짜를 바꾸지 않는다. `*_AT_UTC`는 UTC 시각을 Altibase `DATE`에 저장한다.
- 수집 범위는 과거 45일과 예정입찰을 위한 향후 90일을 각각 실행·기록한다. 이 범위 밖의 이력은 최초 과거 적재 또는 별도 재수집으로 채운다. 최근 24개월의 모든 관측일에 직전 24개월 기준선을 그리려면 조회 시작일보다 약 25개월 앞선 이력도 필요하다.

### 테이블 관계

```text
API_FETCH (API 요청 1회, 전체 페이지)
  └─ API_FETCH_CHUNK (페이지 번호 + 조각 순번별 원문)
       └─ 원본 페이지에서 개별 입찰을 식별·비교

AUCTION_DAY (입찰 1건당 1행, 현재 버전 포인터)
  └─ AUCTION_DAY_SNAPSHOT (그 입찰 1건의 변경 이력)
       └─ AUCTION_DAY_CHUNK (해당 버전의 JSON 객체 조각)
```

`AUCTION_DAY`라는 이름은 유지하지만 **날짜당 1행이 아니다.** 같은 날짜에 여러 CUSIP의 입찰이 있으면 여러 행이 생긴다. 이 정의가 입찰일 전체 교체를 피하면서 `AUCTION_DATE BETWEEN :from AND :to` 조회를 가능하게 한다.

## 2. 필드 정의

`PK`는 기본키, `FK`는 참조키, `UK`는 유일 제약이다. `BIGINT` 식별자는 애플리케이션 또는 DB 시퀀스가 발급하며 API 필드에서 만들지 않는다. 표의 `DATE`는 Altibase 날짜·시각 타입이다.

### API_FETCH — 한 번의 API 범위 조회

| 필드 | 권장 타입 | 필수 | 정의 |
| --- | --- | --- | --- |
| `FETCH_ID` | `BIGINT` | 예 | PK. 페이지 전체를 묶는 수집 고유번호 |
| `SOURCE_CODE` | `VARCHAR(30)` | 예 | `FISCAL_DATA` / `TREASURY_DIRECT` 등 원천 구분 |
| `REQUEST_FROM_DATE` | `DATE` | 예 | API 요청의 시작 입찰일 |
| `REQUEST_TO_DATE` | `DATE` | 예 | API 요청의 종료 입찰일 |
| `REQUEST_URL` | `VARCHAR(2048)` | 예 | 실제 요청 기준 URL. 인증정보를 포함하지 않는다 |
| `STARTED_AT_UTC` | `DATE` | 예 | 수집 시작 시각 |
| `FINISHED_AT_UTC` | `DATE` | 아니요 | 수집 종료 시각. 진행 중이면 NULL |
| `FETCH_STATUS` | `VARCHAR(12)` | 예 | `LOADING` / `READY` / `FAILED` |
| `PAGE_COUNT` | `INTEGER` | 아니요 | 정상 완료된 전체 페이지 수 |
| `RECORD_COUNT` | `INTEGER` | 아니요 | 전체 응답의 `data` 항목 수 |
| `CHUNK_COUNT` | `INTEGER` | 아니요 | 전체 페이지의 저장 조각 수 |
| `RESPONSE_BYTES` | `BIGINT` | 아니요 | 저장한 모든 페이지 JSON의 UTF-8 바이트 합계 |
| `ERROR_MESSAGE` | `VARCHAR(1000)` | 아니요 | 실패 원인. 성공 시 NULL |

한 번의 논리적 범위 조회가 여러 페이지로 나뉘어도 `FETCH_ID`는 하나다. 과거 45일과 향후 90일을 별도로 호출하면 `API_FETCH`도 각각 한 행이다. 페이지 중 하나라도 누락되면 `READY`로 전환하지 않는다.

### API_FETCH_CHUNK — API 페이지 응답 원문

| 필드 | 권장 타입 | 필수 | 정의 |
| --- | --- | --- | --- |
| `FETCH_ID` | `BIGINT` | 예 | `API_FETCH.FETCH_ID`에 대한 FK |
| `PAGE_NO` | `INTEGER` | 예 | API 페이지 번호. 1부터 시작 |
| `CHUNK_NO` | `INTEGER` | 예 | 해당 페이지 안의 조각 순번. 1부터 시작 |
| `JSON_TEXT` | `VARCHAR(3600)` | 예 | **원본 API 페이지 JSON**의 텍스트 조각. UTF-8 기준 최대 3,600바이트 |

PK는 `(FETCH_ID, PAGE_NO, CHUNK_NO)`다. `PAGE_NO`, `CHUNK_NO` 순으로 조각을 합치되 **서로 다른 페이지의 완성된 JSON 문서를 그대로 이어 붙이지 않는다.** 각 페이지를 독립적으로 복원·해석한다.

### AUCTION_DAY — 개별 입찰의 현재 상태와 조회 키

| 필드 | 권장 타입 | 필수 | 정의 |
| --- | --- | --- | --- |
| `AUCTION_ID` | `BIGINT` | 예 | PK. 입찰 1건의 내부 고유번호 |
| `AUCTION_DATE` | `DATE` | 예 | API의 입찰일. `FROM ~ TO` 조회와 인덱스의 기준 |
| `CUSIP` | `VARCHAR(20)` | 예 | API의 증권 식별자 |
| `ISSUE_DATE` | `DATE` | 아니요 | API의 발행일. 미제공 상태를 NULL로 보존 |
| `ISSUE_DATE_KEY` | `VARCHAR(10)` | 예 | 업무키용 값: 발행일 `YYYY-MM-DD`, 미제공이면 `UNKNOWN` |
| `CURRENT_SNAPSHOT_ID` | `BIGINT` | 아니요 | 화면에 제공할 최신 완료 버전의 `SNAPSHOT_ID` |
| `RECORD_STATUS` | `VARCHAR(16)` | 예 | `ACTIVE` / `MISSING_REVIEW` / `INACTIVE` |
| `CREATED_AT_UTC` | `DATE` | 예 | 최초 발견 시각 |
| `LAST_SEEN_AT_UTC` | `DATE` | 예 | 완전한 API 조회에서 마지막으로 확인한 시각 |
| `UPDATED_AT_UTC` | `DATE` | 예 | 현재 버전 또는 상태의 마지막 변경 시각 |

UK는 `(AUCTION_DATE, CUSIP, ISSUE_DATE_KEY)`다. `ISSUE_DATE_KEY`는 NULL을 포함한 유일성 판단이 DB 버전에 따라 달라지는 문제를 피한다. `ISSUE_DATE`가 나중에 채워지면 같은 `CUSIP + AUCTION_DATE`의 `UNKNOWN` 행과 **동일 입찰인지 확인한 뒤** 업무키를 이행한다. 후보가 둘 이상이면 자동 병합하지 않고 검토 대상으로 둔다. `CURRENT_SNAPSHOT_ID`는 해당 `AUCTION_ID`에 속한 `READY` 버전만 가리켜야 한다.

### AUCTION_DAY_SNAPSHOT — 개별 입찰 1건의 저장 버전

| 필드 | 권장 타입 | 필수 | 정의 |
| --- | --- | --- | --- |
| `SNAPSHOT_ID` | `BIGINT` | 예 | PK. 버전 고유번호. 업무키의 해시나 결합 문자열이 아님 |
| `AUCTION_ID` | `BIGINT` | 예 | `AUCTION_DAY.AUCTION_ID`에 대한 FK |
| `FETCH_ID` | `BIGINT` | 예 | 이 버전의 원천인 `API_FETCH.FETCH_ID`에 대한 FK |
| `SOURCE_PAGE_NO` | `INTEGER` | 예 | 원본 응답의 페이지 번호 |
| `SOURCE_ROW_NO` | `INTEGER` | 예 | 그 페이지 `data` 배열 안의 항목 순번. 1부터 시작 |
| `SAVED_AT_UTC` | `DATE` | 예 | 버전 저장 시각 |
| `SNAPSHOT_STATUS` | `VARCHAR(12)` | 예 | `LOADING` / `READY` |
| `CHUNK_COUNT` | `INTEGER` | 예 | 이 입찰 JSON 객체의 조각 수 |
| `JSON_BYTES` | `BIGINT` | 예 | 조각을 합친 JSON 객체의 UTF-8 바이트 수 |

새로운 입찰 또는 내용이 변경된 입찰에만 새 `SNAPSHOT_ID`를 발급한다. 내용이 같으면 기존 현재 버전을 그대로 두고 `LAST_SEEN_AT_UTC`만 갱신한다. 이전 버전과 그 조각은 수정하지 않는다. `FETCH_ID + SOURCE_PAGE_NO + SOURCE_ROW_NO`는 원본 페이지로 돌아가기 위한 위치 정보다.

### AUCTION_DAY_CHUNK — 개별 입찰 JSON 객체

| 필드 | 권장 타입 | 필수 | 정의 |
| --- | --- | --- | --- |
| `SNAPSHOT_ID` | `BIGINT` | 예 | `AUCTION_DAY_SNAPSHOT.SNAPSHOT_ID`에 대한 FK |
| `CHUNK_NO` | `INTEGER` | 예 | 그 입찰 객체 안의 조각 순번. 1부터 시작 |
| `JSON_TEXT` | `VARCHAR(3600)` | 예 | **입찰 1건의 JSON 객체** 텍스트 조각. UTF-8 기준 최대 3,600바이트 |

PK는 `(SNAPSHOT_ID, CHUNK_NO)`다. 이 테이블에는 API `PAGE_NO`가 필요하지 않다. 원본 페이지 위치는 `AUCTION_DAY_SNAPSHOT`에 보존하고, 화면 복원 순서는 `CHUNK_NO`만 사용한다.

## 3. 적재·갱신·조회 순서

1. 수집기는 `API_FETCH`를 `LOADING`으로 만들고 모든 API 페이지를 받는다. 각 페이지 응답 텍스트를 문자 경계를 지키며 최대 3,600바이트로 나누어 `API_FETCH_CHUNK`에 저장한다. 별도 원본 파일은 남기지 않는다.
2. 모든 페이지의 메타데이터와 실제 수신 건수가 맞는지 검사하고, 각 페이지 JSON을 파싱한다. 페이지 누락·파싱 실패가 있으면 `API_FETCH`를 `FAILED`로 남기고 **해당 조회의 개별 입찰 버전은 게시하지 않는다.**
3. 각 `data` 항목에서 `cusip`, `auction_date`, `issue_date`만 조회 키로 읽는다. 개별 입찰 JSON 객체를 이전 현재 버전과 **JSON 내용 기준으로** 비교한다. 공백·필드 순서만 다르면 같은 내용으로 취급하되, 원본 API 페이지 텍스트는 그대로 둔다.
4. 신규 입찰이면 `AUCTION_DAY` 행을 만든다. 내용이 달라진 입찰이면 해당 `AUCTION_ID`에만 새 `AUCTION_DAY_SNAPSHOT` 및 `AUCTION_DAY_CHUNK`를 추가한다. 조각 수·바이트 수·JSON 파싱·업무키를 확인한 뒤 트랜잭션 안에서 `READY`로 만들고 `CURRENT_SNAPSHOT_ID`를 교체한다. 다른 입찰의 현재 포인터는 건드리지 않는다.
5. 조회 시 `AUCTION_DAY.AUCTION_DATE BETWEEN :from AND :to`에서 `ACTIVE`인 입찰과 각 `CURRENT_SNAPSHOT_ID`를 가져온다. 입찰별로 `CHUNK_NO` 순서로 JSON 객체를 복원하고 서버에서 `{"data":[객체1,객체2,...]}` 형태의 응답을 만들어 화면에 보낸다. 여러 API 페이지 JSON을 문자열로 직접 이어 붙이지 않는다.

API 페이지 원문과 일자별 화면 응답은 **동일한 문서가 아니다.** 앞의 것은 `API_FETCH_CHUNK`에서 그대로 복원되고, 뒤의 것은 저장된 개별 입찰 객체를 모아 서버가 생성한다. 개별 객체를 파싱 후 재직렬화하면 공백·필드 순서 등은 달라질 수 있으므로, 원본 페이지와 글자 단위 동일성은 `API_FETCH_CHUNK`가 보장한다.

## 4. 운영 시 반드시 지킬 경계

- **부분 성공 방지:** 전체 페이지를 모두 받기 전에는 어떤 입찰도 현재 버전으로 게시하지 않는다. 쓰기 도중 실패하면 기존 `CURRENT_SNAPSHOT_ID`를 유지한다.
- **중복·정정:** 한 수집 안에서 동일 업무키가 중복되면 임의로 하나를 고르지 않고 검토한다. 정정이 오면 해당 입찰 1건의 버전만 추가한다. 비교 과정에 JSON 파서는 필요하지만 DB에서 전체 JSON을 컬럼별로 풀어 저장할 필요는 없다.
- **누락·취소:** 재조회 응답에서 기존 입찰이 빠졌다는 이유만으로 삭제하지 않는다. 수집 누락이나 원천 변경 가능성을 확인할 때까지 `MISSING_REVIEW`로 표시하고, 확인 후에만 `INACTIVE`로 전환한다.
- **출처 차이:** TreasuryDirect의 조기 결과와 Fiscal Data의 결과는 필드명·구조가 다르다. `SOURCE_CODE`와 원본은 보존하고, 화면 전달 단계에서 출처별 필드 매핑을 적용한다. 서로 다른 출처의 JSON 객체를 그대로 한 `data` 배열에 넣어 현행 화면에 전달하지 않는다.
- **저장 한도:** `VARCHAR(3600)`은 3,600 **문자** 보장이 아니다. 수집기에서 인코딩 후 바이트 길이를 검사하고, 저장 후에도 실제 길이를 확인한다. Altibase 공식 설명은 `VARCHAR`의 크기를 바이트 기준으로 다룬다: [Character Data Types](https://manual.altibase.com/7.3/en/ref/general/1.-Data-Types/Character-Data-Types/).
- **초기 이력:** 과거 45일 재수집은 장기 이력의 최초 적재를 대체하지 못한다. 24개월 차트와 롤링 기준선에 필요한 기간을 먼저 과거 적재한다.
