"""Regenerate the Korean column catalog from an applied PostgreSQL schema."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from ust_pipeline.config import Settings
from ust_pipeline.fiscal import AUCTION_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PURPOSES = {
"ingestion_run":"수집 실행, 범위, 진행·실패·적재 집계", "source_request":"HTTP 시도 및 안전한 파라미터/응답 메타데이터",
"source_snapshot":"변경 불가능한 원본 파일의 해시·위치·응답 메타", "data_quality_issue":"누락·타입·합계·검증 거절과 처리 상태",
"security_master":"CUSIP 단위 증권 기본정보", "auction_event":"공고·일정과 입찰 사건의 현재 상태",
"auction_result":"입찰 결과 수치와 상품별 Stop", "auction_bidder_allocation":"참여자별 응찰·낙찰 원 단위 금액",
"auction_revision":"정규화 내용 변경 이력과 당시 원문", "normalized_record_lineage":"정규화 레코드와 모든 관측 원본의 연결",
"qra_refunding":"2/5/8/11월 Refunding 식별 및 달력/회계/대상 기간", "qra_document":"동적으로 발견한 공식 문서의 논리 식별",
"qra_document_version":"동일 URL의 내용/파서 버전 및 추출 근거 전체", "qra_borrowing_estimate":"분기별 순시장성차입 전망·실적과 현금 가정",
"qra_auction_size":"월별·상품별 actual/anticipated 입찰규모와 별도 TBAC 권고", "qra_supply":"만기별 Gross/Maturing/Net 명목 쿠폰 공급",
"qra_financing_mix":"순차입·쿠폰·Bill·buyback·현금의 분기 조달 구성", "qra_tga_path":"관측/가정/범위별 TGA 앵커",
"qra_guidance":"공식 명시 문장에 연결한 상품별 공급 가이던스", "qra_tentative_auction":"XML 우선 잠정 입찰 일정",
"qra_buyback_operation":"XML 우선 잠정 buyback 운용 일정", "qra_buyback_policy":"Policy Statement의 용도별 buyback 상한",
"qra_dealer_survey":"설문 시점, 대상 기간, 검증 상태와 통계 출처", "qra_dealer_survey_value":"만기·상품·재발행·통계량·시나리오별 설문 셀",
"derived_metric_method":"공식 지표와 구분한 계산 방법의 불변 버전", "derived_metric_method_parameter":"계산 방법 버전별 만기 가중치",
"derived_metric_result":"계산 값, 입력 ID/원값, 식·버전·반올림의 재현 기록",
}
LABELS = {
"cusip":"미국 증권 식별번호", "security_type":"정규화 상품 종류", "source_security_type":"API 원문 상품 종류", "security_term":"원문 만기", "normalized_security_term":"비교용 표준 만기",
"record_date":"API 레코드 기준일", "announcement_date":"공고일", "announcemt_date":"API 공고일", "auction_date":"입찰일", "issue_date":"발행·결제일", "settlement_date":"결제일", "maturity_date":"만기일", "original_issue_date":"최초 발행일", "original_security_term":"최초 발행 만기", "series":"발행 시리즈", "inflation_index_security":"물가연동 여부", "floating_rate":"변동금리 여부", "reopening":"재발행 여부", "cash_management_bill":"CMB 여부",
"offering_amount_usd":"공고 발행액", "interest_rate":"쿠폰금리", "bid_to_cover_ratio":"원본 응찰배수(2.48 보존)", "allocation_percentage":"고율에서 비례 배정률", "price_per_100":"액면100당 낙찰가격", "high_price":"최고가격", "high_discount_rate":"최고 할인율", "high_investment_rate":"최고 투자수익률", "high_discount_margin":"최고 할인마진", "high_yield":"최고 수익률", "spread":"FRN 스프레드", "stop_value":"상품별 낙찰 Stop", "stop_metric_code":"Stop 지표 코드", "stop_metric_label":"Stop 표시 명칭",
"total_tendered_usd":"전체 응찰액", "total_accepted_usd":"전체 낙찰액", "competitive_tendered_usd":"경쟁 응찰액", "competitive_accepted_usd":"경쟁 낙찰액", "noncompetitive_accepted_usd":"비경쟁 낙찰액",
"raw_record":"원문 필드값 JSON", "typed_record":"당시 Decimal/날짜 정규화 JSON", "source_locator":"페이지/시트/표/행/열/selector/인용문/추출신뢰도", "parse_summary":"전체 추출값·근거·검증이슈 JSON", "response_meta":"API labels/dataTypes/dataFormats/count/pages 등", "safe_parameters":"허용된 공개 쿼리 파라미터만 직렬화", "request_headers":"비밀정보 제외 요청 헤더", "response_headers":"HTTP 응답 헤더", "content_sha256":"응답 본문 SHA-256", "content_hash":"정규화 내용 SHA-256", "current_content_hash":"현재 정규화 내용 SHA-256", "business_key_hash":"cusip/입찰일/발행일 업무키 SHA-256", "raw_storage_uri":"변경 불가 원본의 절대 경로", "mime_type":"원천 Content-Type", "content_length":"실제 응답 본문 바이트 수", "etag":"HTTP ETag", "last_modified":"HTTP Last-Modified 원문", "source_url":"요청한 공식 URL", "final_url":"리디렉션 후 공식 URL", "request_url":"HTTP 요청 URL", "canonical_url":"정규화 절대 URL", "discovered_on_url":"링크 발견 공식 페이지", "anchor_text":"원천 링크 표시문구", "parser_version":"추출/정규화 코드 버전", "version_number":"문서 버전 번호", "revision_number":"입찰 정정 번호", "change_fields":"이전 정정과 달라진 필드 목록", "is_current":"현재 버전 여부", "parse_status":"추출/검토/격리 상태", "validation_status":"출처 검증 상태", "confidence":"추출 신뢰도", "extraction_confidence":"추출 신뢰도", "entity_type":"연결 레코드 테이블/종류", "field_name":"문제 원천 필드", "raw_value":"문제 원문 값", "severity":"검증 심각도", "rule_code":"검증 규칙 코드", "null_reason":"NULL의 원인", "message":"검증 메시지", "resolution_status":"이슈 처리 상태",
"refunding_year":"Refunding 연도", "refunding_month":"Refunding 발표월", "calendar_year":"달력 연도", "calendar_quarter":"달력 분기", "fiscal_year":"미 회계연도", "fiscal_quarter":"미 회계분기", "covered_period_start":"대상 기간 시작일", "covered_period_end":"대상 기간 종료일", "period_start":"값 적용 기간 시작일", "period_end":"값 적용 기간 종료일", "release_datetime":"실제 발표 순간", "next_scheduled_release_date":"다음 본 발표 예정일", "source_page_url":"Refunding 발견 페이지", "source_timezone":"원천 시간대 IANA명", "release_timezone":"원천 발표 시간대", "value_class":"실적/전망/권고/설문/파생 분류", "source_authority":"수치 권한·기관 구분",
"borrowing_amount_usd":"privately-held 순시장성차입", "end_cash_balance_usd":"분기말 현금 잔액·가정", "prior_estimate_usd":"직전 전망(명시 delta로 검산 가능)", "change_from_prior_usd":"직전 대비 금액 변화", "change_reason":"원천 변화 사유 문단", "auction_month":"입찰 월의 첫날", "size_status":"실제/예정 입찰규모 구분", "auction_size_usd":"정례 입찰액", "prior_qra_auction_size_usd":"직전 QRA 동일 조건 입찰액", "gross_issuance_usd":"총발행액", "maturing_amount_usd":"만기도래액", "net_issuance_usd":"순발행액", "privately_held_net_market_borrowing_usd":"민간보유 순시장성차입", "net_coupon_issuance_usd":"순쿠폰 발행", "implied_change_in_bills_usd":"암묵적 Bill 순증감", "assumed_buybacks_usd":"가정 buyback 금액", "end_tga_usd":"기말 TGA(출처 연결 시)", "observation_date":"TGA 기준일 또는 명시 기간 대표일", "point_type":"시작실제/분기말가정/중간peak/다음말가정", "balance_usd":"TGA 잔고·가정", "range_low_usd":"가정 범위 하단", "range_high_usd":"가정 범위 상단", "instrument_group":"가이던스 상품군", "guidance_status":"명시 문장 기반 공급방향", "effective_period":"원천에 명시된 가이던스 적용기간 문장", "evidence_text":"근거 원문 문장", "calendar_name":"XML 일정 명칭", "calendar_start_date":"XML 일정 시작일", "calendar_end_date":"XML 일정 종료일", "tips":"TIPS 여부", "purchase_bucket_name":"매입 대상 bucket", "operation_type":"buyback 운용 종류", "operation_purpose":"매입 상한의 용도", "minimum_purchase_amount_usd":"최소 매입금액", "maximum_purchase_amount_usd":"최대 매입금액", "maximum_amount_usd":"가이던스 최대금액", "maturity_date_range_start":"대상 만기일 범위 시작", "maturity_date_range_end":"대상 만기일 범위 종료", "operation_date":"매입 운용일",
"survey_as_of_date":"명시된 조사 기준일(일 미기재 NULL)", "survey_as_of_month":"명시된 조사월 첫날", "date_precision":"원천 날짜 정밀도 DAY/MONTH", "target_fiscal_year":"설문 대상 FY", "target_period_start":"설문 대상기간 시작", "target_period_end":"설문 대상기간 말", "expected_increase_timing":"명시된 증액 개시시점", "source_sheet":"원천 시트명", "source_table":"원천 표명", "statistic":"TRIMMED_MEAN/STD 등 원문 통계량", "scenario":"기대규모/놀랍지 않은 범위의 LOW/HIGH", "current_auction_size_usd":"근거가 확인된 현재입찰액", "expected_auction_size_usd":"해당 통계량의 예상 규모", "calculated_pct_change":"현재 대비 예상 변화율",
"method_code":"계산 방법 식별코드", "version":"계산 방법 버전", "name":"방법 표시명", "description":"방법 설명", "formula":"재현 가능한 계산식", "unit":"계산결과·파라미터 단위", "effective_from":"방법 적용 시작일", "effective_to":"방법 적용 종료일", "rounding_rule":"반올림 규칙", "is_official_treasury_metric":"재무부 공식 지표 여부", "parameter_name":"파라미터 종류", "parameter_key":"가중치의 만기 키", "numeric_value":"Decimal 파라미터", "text_value":"문자열 파라미터", "metric_value":"계산 결과", "input_record_ids":"계산 입력 레코드 UUID 목록", "input_values":"당시 입력 수치와 가중치", "calculation_method":"원천 계산 설명", "calculation_version":"파생 계산 버전", "job_type":"수집 명령 종류", "source_name":"원천 종류", "status":"실행 상태", "requested_from":"요청 범위 시작", "requested_to":"요청 범위 끝", "checkpoint":"완료 페이지와 전체 페이지 수", "error_summary":"오류 요약", "http_status":"HTTP 상태코드", "elapsed_ms":"HTTP 소요시간", "attempt_number":"재시도 순번", "error_message":"HTTP/처리 오류",
}

def label(column):
    if column in LABELS: return LABELS[column]
    if column.endswith('_id'): return column.removesuffix('_id') + ' 식별키(UUID/연결키)'
    time_labels={'started_at':'실행 시작','finished_at':'실행 종료','fetched_at':'수집','created_at':'생성','updated_at':'갱신','first_seen_at':'최초 관측','last_seen_at':'최근 관측','parsed_at':'파싱','resolved_at':'이슈 해결','calculated_at':'계산','valid_from':'버전 유효 시작','valid_to':'버전 유효 종료'}
    if column in time_labels:return time_labels[column]+' 순간(UTC 저장)'
    if column.startswith(('closing_time_','operation_')) and (column.endswith('_et') or column.endswith('_raw')):return column+' / 원천 ET 시각'+(' 원문' if column.endswith('_raw') else ' TIME')
    if column.startswith(('pages_','documents_','rows_')):return column.replace('pages','페이지').replace('documents','문서').replace('rows','행').replace('attempted','시도').replace('succeeded','성공').replace('received','수신').replace('inserted','추가').replace('updated','수정').replace('unchanged','동일').replace('rejected','거절')+' 건수'
    if column.endswith('_usd'):
        return column[:-4].replace('primary_dealer','PD').replace('direct_bidder','직접입찰자').replace('indirect_bidder','간접입찰자').replace('treasury_retail','재무부 소매').replace('soma','SOMA').replace('fima_noncomp','FIMA 비경쟁').replace('tendered','응찰액').replace('accepted','낙찰액').replace('holdings','보유액')
    return {'auction_format':'입찰 방식','security_term_day_month':'일·월 기준 원문만기','security_term_week_year':'주·년 기준 원문만기'}.get(column,column+' (원천 명칭 보존)')

def source_map():
    mapping={}
    tree=ast.parse((ROOT/'src/ust_pipeline/repository.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='result_map' for t in node.targets):
            for col,field in ast.literal_eval(node.value).items():mapping[col]=field
    mapping.update({'offering_amount_usd':'offering_amt','announcement_date':'announcemt_date','cash_management_bill':'cash_management_bill_cmb','treasury_retail_accepted_usd':'treas_retail_accepted'})
    return mapping

def main():
    engine=create_engine(Settings().database_url)
    meta=json.loads((ROOT/'tests_pipeline/fixtures/auctions_page_1.json').read_text(encoding='utf-8'))['meta']
    fields=set(AUCTION_FIELDS.split(',')); fmap=source_map()
    output=['# PostgreSQL DB 명세','', 'PostgreSQL 16 / schema `ust` / migrations `20260903_0001`–`20261007_0002`. 실제 적용 DB의 catalog에서 타입·NULL·기본값·제약·인덱스를 추출했다. 설명과 원천 매핑은 코드 계약과 함께 관리한다. 현재 화면 계약은 `UST_AUCTION_ui-baseline-v3.html`이다.','',
    '## v3 구현 범위','',
    '- v3의 고객 화면은 `입찰 결과` 단일 상단 메뉴로 구성한다. 예정 입찰 일정과 월간 캘린더는 같은 화면 안에서 `v_auction_dashboard`의 `ANNOUNCED` 행을 사용한다. 별도 일정 데이터 모델을 만들지 않는다.',
    '- 화면에 노출하지 않는 API 필드·데이터 구조 안내는 내부 문서인 `API_FIELD_METADATA.md`, 이 명세, `DATA_REQUIREMENTS_AND_MAPPING.md`에서만 관리한다. 고객 화면 제거는 원천 필드·감사·lineage 저장 삭제를 뜻하지 않는다.',
    '- QRA 공급 기능은 v3 배포 범위에서 제외한다. 기존 `qra_*` 테이블과 `v_qra_*` 읽기 모델은 향후 제공을 위한 보류 스키마이며, v3 조회·배포의 필수 객체나 데이터 적재 선행조건이 아니다.',
    '- 실시간 2Y·10Y·30Y 시장금리는 v3에서 미연결 상태다. 검증된 별도 원천이 생기기 전에는 시장금리 테이블을 추가하거나 입찰 Stop으로 대체하지 않는다.','',
    '### v3 화면 조회 계약','',
    '| 화면 요소 | DB 객체·필드 | 조회·계산 규칙 |',
    '|---|---|---|',
    '| 최근 입찰·KPI·결과표 | `v_auction_dashboard`의 `RESULT_AVAILABLE` 행 | 사용자 결과 기간과 상품 필터를 적용한다. CUSIP는 내부 식별에만 사용하고 화면에는 표시하지 않는다. |',
    '| 예정 입찰 일정·월간 캘린더 | `v_auction_dashboard`의 `ANNOUNCED` 행 | 기준일 이상 90일 이내의 공식 공고만 표시한다. 결과와 예정이 같은 사건이면 `auction_event_id` 기준으로 결과를 우선한다. |',
    '| 낙찰금리·참여자 비중 | `stop_value`, `*_share_pct`, `other_ui_residual_pct` | 선택 결과와 동일한 `security_type + normalized_security_term`만 비교한다. |',
    '| 응찰률 KPI | `bid_to_cover_ratio` | 원본 배수에 100을 곱해 %로 표시한다. 선택 결과 이전 최대 6개 유효값 평균과 %p가 아닌 퍼센트 값 차이를 계산한다. |',
    '| 응찰률 장기 차트 | `bid_to_cover_ratio`, `auction_date` | 동일 상품·만기 전 이력을 날짜순으로 계산한다. 각 관측일 직전 24개월 초과 경계의 유효값으로 평균·모집단 표준편차(±1σ)를 계산하고 최근 6회 평균은 6건이 모두 있을 때만 표시한다. 조회 시작일보다 25개월 앞선 warm-up 데이터를 확보한다. |',
    '| 상태·출처 | `v_ingestion_status`, `source_snapshot` | 마지막 시도와 성공을 구분하며, 수신 실패 시 표본값으로 대체하지 않는다. |','',
    '## ERD','', '```mermaid','erDiagram',' ingestion_run ||--o{ source_request : attempts',' source_request ||--o{ source_snapshot : captures',' source_snapshot ||--o{ normalized_record_lineage : proves',' security_master ||--o{ auction_event : identifies',' auction_event ||--|| auction_result : result',' auction_event ||--|| auction_bidder_allocation : allocations',' auction_event ||--o{ auction_revision : revises',' qra_refunding ||--o{ qra_document : publishes',' qra_document ||--o{ qra_document_version : versions',' source_snapshot ||--o{ qra_document_version : preserves',' qra_document_version ||--o{ qra_supply : supports',' qra_document_version ||--o{ qra_borrowing_estimate : supports',' qra_document_version ||--o{ qra_auction_size : supports',' qra_document_version ||--o{ qra_tga_path : supports',' qra_document_version ||--o{ qra_financing_mix : supports',' qra_document_version ||--o{ qra_guidance : supports',' qra_document_version ||--o{ qra_tentative_auction : supports',' qra_document_version ||--o{ qra_buyback_operation : supports',' qra_document_version ||--o{ qra_buyback_policy : supports',' qra_document_version ||--o{ qra_dealer_survey : supports',' qra_dealer_survey ||--o{ qra_dealer_survey_value : cells',' derived_metric_method ||--o{ derived_metric_method_parameter : weights',' derived_metric_method ||--o{ derived_metric_result : computes',' source_snapshot ||--o{ data_quality_issue : validates','```','',
    '## 공통 갱신·보관 정책','',
    '- A(감사): 실행마다 추가. 원본/정정/문서버전/계산기록은 무기한 보관하며 자동 삭제하지 않는다. DB 백업과 raw 디렉터리를 함께 보관한다. FK의 CASCADE는 명시적인 관리 삭제 시에만 적용되며 수집 명령은 실행/원본 이력을 삭제하지 않는다.',
    '- C(현재): 업무키 upsert. 같은 정규화 내용이면 최근 관측만 갱신; 내용이 바뀌면 auction_revision 추가. QRA 정상 새 문서 버전은 같은 문서의 이전 current fact를 교체하고 이전 값·근거는 parse_summary와 raw에 유지한다. 격리된 새 문서는 이전 정상 fact를 보존한다.',
    '- M(방법): 새 방법은 새 version으로 추가. 공급행의 dv01_method_id와 derived_metric_result는 당시 방법/입력/식/반올림을 고정한다. 기존 방법 파라미터를 수정하지 않는 운영 정책이다.',
    '- 모든 USD 금액은 NUMERIC(24,2), 금리·비율은 NUMERIC(18,9). float/real/double precision 금지. 금융 계산은 Decimal. HTTP timeout/backoff와 PDF 좌표 같은 비금융 라이브러리 내부값은 별개다.',
    '- DATE는 원천 달력일. TIMESTAMPTZ는 실제 순간. ET만 있는 시각은 TIME+America/New_York이며 날짜와 결합할 때만 DST 적용한다.',
    '- NULL 이유는 원천 raw/상품적용규칙/data_quality_issue.null_reason과 DATA_GAPS 계약으로 판별한다. 실제0은 보존한다. QRA source_locator는 필드별 column_label 또는 원문 field명 매핑을 포함하는 record 수준 근거다.',
    '- 업무키는 (cusip,auction_date,issue_date). issue_date NULL은 UQ NULLS NOT DISTINCT로 같은 미완성 키의 중복만 막는다. NULL 발행일 자료는 검증 경고를 남기며 후속 발행일이 확정될 때 다른 사건으로 오합병하지 않는다. 날짜 정정은 원천키 변경이므로 별도 사건+원본을 유지하고 품질검토 대상으로 본다.',
    '- source_snapshot은 URL+hash로 재사용, qra_document_version은 내용 또는 parser/status 변경 시 증가. A→B→A 정정도 순서대로 남긴다. 동시 수집은 명령별 PostgreSQL advisory lock으로 직렬화한다.',
    '- 아래 예시는 형식 예시이며 seed 운영데이터가 아니다. PK/FK/UQ/CHECK의 정확한 정의는 각 표 아래 PostgreSQL catalog 출력이 권위 있는 명세다.','']
    with engine.connect() as conn:
        tables=conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='ust' AND table_type='BASE TABLE' ORDER BY table_name")).scalars().all()
        for table in tables:
            mode='M' if table.startswith('derived_metric_method') else 'A' if table in {'ingestion_run','source_request','source_snapshot','auction_revision','qra_document_version','normalized_record_lineage','derived_metric_result','data_quality_issue'} else 'C'
            output += [f'## {table}', '', PURPOSES.get(table,table)+f'。 갱신·보관 규칙: **{mode}** (공통 정책 참조).', '', '| 컬럼 | 한글 설명 | PostgreSQL 타입 | 단위 | NULL | 기본값 | 원천/생성 | 예시 |','|---|---|---|---|---|---|---|---|']
            cols=conn.execute(text("""SELECT a.attname,format_type(a.atttypid,a.atttypmod) AS typ,NOT a.attnotnull AS nullable,pg_get_expr(d.adbin,d.adrelid) AS def,a.attidentity
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                WHERE n.nspname='ust' AND c.relname=:t AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"""),{'t':table}).all()
            for col,typ,nullable,default,identity in cols:
                source=fmap.get(col,col.removesuffix('_usd'))
                if table.startswith('auction') or table=='security_master': source='API.'+source if source in meta['labels'] else '정규화/감사 생성'
                elif table.startswith('qra_') and col not in {'source_locator','parse_summary'}: source='QRA 문서/추출·식별 규칙 (매핑표 참조)'
                else: source='수집기/HTTP/계산 방법 설정'
                unit='USD' if col.endswith('_usd') else '%' if col in {'stop_value','high_discount_rate','high_investment_rate','high_discount_margin','high_yield','interest_rate','spread','allocation_percentage','calculated_pct_change'} else '배' if col=='bid_to_cover_ratio' else 'USD/액면100' if 'price' in col else 'byte' if col=='content_length' else '건' if col.startswith(('rows_','pages_','documents_')) else '—'
                example='NULL' if nullable else 'UUID' if typ=='uuid' else '{}' if typ=='jsonb' else '2026-08-05' if typ=='date' else '2026-08-05T12:30:00Z' if typ.startswith('timestamp') else '0' if typ.startswith(('numeric','integer','bigint','smallint')) else 'true' if typ=='boolean' else '원천 문자열'
                deftext='IDENTITY' if identity else str(default or '없음')
                output.append(f'| `{col}` | {label(col)} | `{typ}` | {unit} | {"허용" if nullable else "불가"} | `{deftext}` | {source} | {example} |')
            constraints=conn.execute(text("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=to_regclass(:t) ORDER BY conname"),{'t':'ust.'+table}).all()
            indexes=conn.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname='ust' AND tablename=:t ORDER BY indexname"),{'t':table}).scalars().all()
            output += ['', '키·제약:', '', '```sql']+[f'-- {n}\n{d};' for n,d in constraints]+['```','', '인덱스:', '', '```sql']+list(indexes)+['```','']
        output+=['## 읽기 모델','', '화면별 컬럼 대응/계산/결측은 DATA_REQUIREMENTS_AND_MAPPING.md를 따른다. SELECT 권한만 부여해 사용한다. 조회 범위는 DATE 조건으로 필터하며 WI/Tail/실시간 시장금리 컬럼은 만들지 않는다.','']
        for view,definition in conn.execute(text("SELECT viewname,definition FROM pg_views WHERE schemaname='ust' ORDER BY viewname")):
            columns=conn.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='ust' AND table_name=:v ORDER BY ordinal_position"),{'v':view}).all()
            output += [f'### {view}', '', '컬럼: '+', '.join('`'+c+'` ('+t+')' for c,t in columns), '', '```sql', definition, '```','']
    (ROOT/'docs/DB_SPEC.md').write_text('\n'.join(output),encoding='utf-8')
    api=['# 실제 Fiscal Data API 필드 메타데이터','', '기준: tests_pipeline/fixtures/auctions_page_1.json. URL/수집시각/hash는 MANIFEST.json. 첫 응답의 전체 labels/dataTypes/dataFormats를 그대로 대조한다. price_per100/high_price는 원천 STRING이지만 Decimal로 정규화한다.','', '| 원천 snake_case | label | dataType | dataFormat | 최소 수집 | DB 원천 보존 |','|---|---|---|---|---|---|']
    for field, lab in meta['labels'].items():
        target=next((k for k,v in fmap.items() if v==field),field)
        api.append(f'| `{field}` | {lab} | {meta["dataTypes"].get(field)} | {meta["dataFormats"].get(field)} | {"예" if field in fields else "아니오"} | {target if field in fields else "최소집합 밖; 메타만 보존"} |')
    (ROOT/'docs/API_FIELD_METADATA.md').write_text('\n'.join(api)+'\n',encoding='utf-8')

if __name__=='__main__': main()
