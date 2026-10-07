-- PostgreSQL 16+. Independent of the earlier unverified UI/D1 draft.
CREATE SCHEMA IF NOT EXISTS ust;

CREATE TABLE ust.ingestion_run (
 run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_name text NOT NULL, job_type text NOT NULL,
 requested_from date, requested_to date, started_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
 status text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCESS','PARTIAL_FAILURE','FAILED','DRY_RUN')),
 pages_attempted integer NOT NULL DEFAULT 0, pages_succeeded integer NOT NULL DEFAULT 0,
 documents_attempted integer NOT NULL DEFAULT 0, documents_succeeded integer NOT NULL DEFAULT 0,
 documents_review_required integer NOT NULL DEFAULT 0,
 rows_received bigint NOT NULL DEFAULT 0, rows_inserted bigint NOT NULL DEFAULT 0,
 rows_updated bigint NOT NULL DEFAULT 0, rows_unchanged bigint NOT NULL DEFAULT 0, rows_rejected bigint NOT NULL DEFAULT 0,
 checkpoint jsonb NOT NULL DEFAULT '{}', error_summary text,
 CHECK (finished_at IS NULL OR finished_at >= started_at), CHECK (rows_received >= 0 AND rows_rejected >= 0)
);
CREATE INDEX ix_run_status ON ust.ingestion_run(status,started_at DESC);
CREATE INDEX ix_run_source ON ust.ingestion_run(source_name,job_type,started_at DESC);
CREATE TABLE ust.source_request (
 source_request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES ust.ingestion_run ON DELETE CASCADE, request_url text NOT NULL,
 safe_parameters jsonb NOT NULL DEFAULT '{}', request_headers jsonb NOT NULL DEFAULT '{}',
 http_status integer CHECK (http_status BETWEEN 100 AND 599), response_headers jsonb NOT NULL DEFAULT '{}',
 fetched_at timestamptz NOT NULL DEFAULT clock_timestamp(), elapsed_ms integer, attempt_number smallint NOT NULL DEFAULT 1,
 error_message text
);
CREATE INDEX ix_request_url ON ust.source_request(request_url,fetched_at DESC);
CREATE TABLE ust.source_snapshot (
 source_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_request_id bigint REFERENCES ust.source_request ON DELETE SET NULL,
 source_name text NOT NULL, source_url text NOT NULL, final_url text NOT NULL, discovered_on_url text, anchor_text text,
 content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'), mime_type text NOT NULL,
 content_length bigint NOT NULL CHECK (content_length >= 0), etag text, last_modified text,
 fetched_at timestamptz NOT NULL, raw_storage_uri text NOT NULL, parser_version text, response_meta jsonb NOT NULL DEFAULT '{}',
 UNIQUE(source_url,content_sha256)
);
CREATE INDEX ix_snapshot_hash ON ust.source_snapshot(content_sha256);
CREATE INDEX ix_snapshot_url ON ust.source_snapshot(source_url,fetched_at DESC);
CREATE TABLE ust.data_quality_issue (
 data_quality_issue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid REFERENCES ust.ingestion_run ON DELETE SET NULL,
 source_snapshot_id uuid REFERENCES ust.source_snapshot ON DELETE SET NULL,
 entity_type text, entity_id uuid, field_name text,
 severity text NOT NULL CHECK (severity IN ('INFO','WARN','ERROR','FATAL')), rule_code text NOT NULL, raw_value text,
 null_reason text CHECK (null_reason IN ('SOURCE_NULL','NOT_APPLICABLE','UNAVAILABLE_SOURCE','NOT_CONNECTED','PARSE_FAILED')),
 message text NOT NULL, resolution_status text NOT NULL DEFAULT 'OPEN' CHECK (resolution_status IN ('OPEN','ACCEPTED','RESOLVED','IGNORED')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), resolved_at timestamptz
);
CREATE INDEX ix_quality_open ON ust.data_quality_issue(resolution_status,severity,created_at DESC);

CREATE TABLE ust.security_master (
 security_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), cusip varchar(20) NOT NULL UNIQUE,
 security_type text NOT NULL, original_security_term text, series text, inflation_index_security boolean, floating_rate boolean,
 original_issue_date date, maturity_date date, first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ust.auction_event (
 auction_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), security_id uuid NOT NULL REFERENCES ust.security_master,
 cusip varchar(20) NOT NULL, record_date date NOT NULL, announcement_date date, auction_date date NOT NULL,
 issue_date date, maturity_date date, security_type text NOT NULL, source_security_type text, security_term text NOT NULL, normalized_security_term text NOT NULL,
 security_term_day_month text, security_term_week_year text, auction_format text, reopening boolean, cash_management_bill boolean,
 closing_time_comp_raw text, closing_time_comp_et time, closing_time_noncomp_raw text, closing_time_noncomp_et time,
 source_timezone text NOT NULL DEFAULT 'America/New_York' CHECK (source_timezone='America/New_York'),
 offering_amount_usd numeric(24,2) CHECK (offering_amount_usd >= 0),
 business_key_hash char(64) NOT NULL UNIQUE CHECK (business_key_hash ~ '^[0-9a-f]{64}$'),
 current_content_hash char(64) NOT NULL CHECK (current_content_hash ~ '^[0-9a-f]{64}$'),
 current_snapshot_id uuid REFERENCES ust.source_snapshot, raw_record jsonb NOT NULL,
 first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(), last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE NULLS NOT DISTINCT(cusip,auction_date,issue_date),
 CHECK (maturity_date IS NULL OR issue_date IS NULL OR maturity_date > issue_date)
);
CREATE INDEX ix_auction_recent ON ust.auction_event(auction_date DESC,security_type,normalized_security_term);
CREATE INDEX ix_auction_comparable ON ust.auction_event(security_type,normalized_security_term,auction_date DESC);
CREATE INDEX ix_auction_cusip ON ust.auction_event(cusip,auction_date DESC);
CREATE TABLE ust.auction_result (
 auction_event_id uuid PRIMARY KEY REFERENCES ust.auction_event ON DELETE CASCADE,
 stop_metric_code text NOT NULL CHECK (stop_metric_code IN ('HIGH_DISCOUNT_RATE','HIGH_YIELD','HIGH_REAL_YIELD','HIGH_DISCOUNT_MARGIN','UNMAPPED')),
 stop_metric_label text NOT NULL, stop_value numeric(18,9), high_discount_rate numeric(18,9), high_investment_rate numeric(18,9),
 high_discount_margin numeric(18,9), high_yield numeric(18,9), spread numeric(18,9), interest_rate numeric(18,9),
 price_per_100 numeric(20,9), high_price numeric(20,9), bid_to_cover_ratio numeric(18,9) CHECK (bid_to_cover_ratio >= 0),
 allocation_percentage numeric(18,9) CHECK (allocation_percentage BETWEEN 0 AND 100),
 total_tendered_usd numeric(24,2) CHECK (total_tendered_usd >= 0), total_accepted_usd numeric(24,2) CHECK (total_accepted_usd >= 0),
 competitive_tendered_usd numeric(24,2), competitive_accepted_usd numeric(24,2), noncompetitive_accepted_usd numeric(24,2),
 pdf_filename_announcement text, pdf_filename_comp_results text, pdf_filename_noncomp_results text,
 xml_filename_announcement text, xml_filename_comp_results text, updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ust.auction_bidder_allocation (
 auction_event_id uuid PRIMARY KEY REFERENCES ust.auction_event ON DELETE CASCADE,
 primary_dealer_tendered_usd numeric(24,2), primary_dealer_accepted_usd numeric(24,2) CHECK (primary_dealer_accepted_usd >= 0),
 direct_bidder_tendered_usd numeric(24,2), direct_bidder_accepted_usd numeric(24,2) CHECK (direct_bidder_accepted_usd >= 0),
 indirect_bidder_tendered_usd numeric(24,2), indirect_bidder_accepted_usd numeric(24,2) CHECK (indirect_bidder_accepted_usd >= 0),
 treasury_retail_accepted_usd numeric(24,2), soma_tendered_usd numeric(24,2), soma_accepted_usd numeric(24,2), soma_holdings_usd numeric(24,2),
 fima_noncomp_tendered_usd numeric(24,2), fima_noncomp_accepted_usd numeric(24,2), updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ust.auction_revision (
 auction_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), auction_event_id uuid NOT NULL REFERENCES ust.auction_event ON DELETE CASCADE,
 revision_number integer NOT NULL CHECK (revision_number > 0), content_hash char(64) NOT NULL,
 source_snapshot_id uuid REFERENCES ust.source_snapshot, raw_record jsonb NOT NULL, typed_record jsonb NOT NULL,
 valid_from timestamptz NOT NULL DEFAULT clock_timestamp(), valid_to timestamptz, is_current boolean NOT NULL DEFAULT true,
 change_fields text[] NOT NULL DEFAULT ARRAY[]::text[], UNIQUE(auction_event_id,revision_number),
 CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX uq_auction_revision_current ON ust.auction_revision(auction_event_id) WHERE is_current;
CREATE TABLE ust.normalized_record_lineage (
 normalized_record_lineage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 entity_type text NOT NULL, entity_id uuid NOT NULL, source_snapshot_id uuid NOT NULL REFERENCES ust.source_snapshot,
 source_locator jsonb NOT NULL DEFAULT '{}', parser_version text NOT NULL, confidence numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(entity_type,entity_id,source_snapshot_id,parser_version)
);

CREATE TABLE ust.qra_refunding (
 qra_refunding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), refunding_year integer NOT NULL CHECK (refunding_year BETWEEN 1970 AND 2200),
 refunding_month smallint NOT NULL CHECK (refunding_month IN (2,5,8,11)), release_datetime timestamptz,
 release_timezone text NOT NULL DEFAULT 'America/New_York', calendar_quarter smallint CHECK (calendar_quarter BETWEEN 1 AND 4),
 fiscal_year integer, fiscal_quarter smallint CHECK (fiscal_quarter BETWEEN 1 AND 4), covered_period_start date, covered_period_end date,
 next_scheduled_release_date date, prior_qra_refunding_id uuid REFERENCES ust.qra_refunding, source_page_url text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(refunding_year,refunding_month), CHECK (covered_period_end >= covered_period_start)
);
CREATE INDEX ix_qra_latest ON ust.qra_refunding(refunding_year DESC,refunding_month DESC);
CREATE TABLE ust.qra_document (
 qra_document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 canonical_url text NOT NULL, document_type text NOT NULL, anchor_text text, discovered_on_url text NOT NULL,
 release_datetime timestamptz, release_timezone text NOT NULL DEFAULT 'America/New_York', current_version_id uuid,
 first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(), last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(qra_refunding_id,canonical_url)
);
CREATE INDEX ix_qra_document_url ON ust.qra_document(canonical_url,last_seen_at DESC);
CREATE TABLE ust.qra_document_version (
 qra_document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_document_id uuid NOT NULL REFERENCES ust.qra_document ON DELETE CASCADE,
 source_snapshot_id uuid NOT NULL REFERENCES ust.source_snapshot, version_number integer NOT NULL CHECK (version_number > 0),
 content_sha256 char(64) NOT NULL, parser_version text NOT NULL,
 parse_status text NOT NULL DEFAULT 'PENDING' CHECK (parse_status IN ('PENDING','PARSED','RAW_ONLY','REVIEW_REQUIRED','QUARANTINED','FAILED')),
 parsed_at timestamptz, parse_summary jsonb NOT NULL DEFAULT '{}', is_current boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(qra_document_id,version_number)
);
ALTER TABLE ust.qra_document ADD CONSTRAINT fk_qra_document_current FOREIGN KEY(current_version_id) REFERENCES ust.qra_document_version;
CREATE UNIQUE INDEX uq_qra_version_current ON ust.qra_document_version(qra_document_id) WHERE is_current;
CREATE INDEX ix_qra_version_hash ON ust.qra_document_version(content_sha256);

CREATE TABLE ust.qra_borrowing_estimate (
 qra_borrowing_estimate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, calendar_year integer NOT NULL,
 calendar_quarter smallint NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4), fiscal_year integer, fiscal_quarter smallint,
 period_start date NOT NULL, period_end date NOT NULL, borrowing_amount_usd numeric(24,2) NOT NULL, end_cash_balance_usd numeric(24,2),
 prior_estimate_usd numeric(24,2), change_from_prior_usd numeric(24,2), change_reason text,
 value_class text NOT NULL CHECK (value_class IN ('OFFICIAL_ACTUAL','OFFICIAL_ESTIMATE','TBAC_RECOMMENDATION','PRIMARY_DEALER_SURVEY','DERIVED_UI_PROXY')),
 source_authority text NOT NULL, source_locator jsonb NOT NULL,
 UNIQUE(qra_refunding_id,calendar_year,calendar_quarter,value_class,qra_document_version_id), CHECK (period_end >= period_start)
);
CREATE TABLE ust.qra_auction_size (
 qra_auction_size_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, auction_month date NOT NULL,
 security_type text NOT NULL, normalized_security_term text NOT NULL, reopening boolean,
 size_status text NOT NULL CHECK (size_status IN ('ACTUAL','ANTICIPATED')), auction_size_usd numeric(24,2) NOT NULL CHECK (auction_size_usd >= 0),
 prior_qra_auction_size_usd numeric(24,2), change_from_prior_usd numeric(24,2), value_class text NOT NULL, source_authority text NOT NULL,
 source_locator jsonb NOT NULL, UNIQUE NULLS NOT DISTINCT(qra_refunding_id,auction_month,security_type,normalized_security_term,reopening,size_status,value_class)
);
CREATE INDEX ix_qra_size_monitor ON ust.qra_auction_size(qra_refunding_id,auction_month,normalized_security_term);
CREATE TABLE ust.qra_supply (
 qra_supply_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, period_start date NOT NULL, period_end date NOT NULL,
 fiscal_year integer, fiscal_quarter smallint, security_type text NOT NULL DEFAULT 'Nominal coupon', normalized_security_term text NOT NULL,
 gross_issuance_usd numeric(24,2) CHECK (gross_issuance_usd >= 0), maturing_amount_usd numeric(24,2) CHECK (maturing_amount_usd >= 0),
 net_issuance_usd numeric(24,2), dv01_method_id uuid, value_class text NOT NULL, source_authority text NOT NULL, source_locator jsonb NOT NULL,
 UNIQUE(qra_refunding_id,period_start,security_type,normalized_security_term,value_class), CHECK (period_end >= period_start)
);
CREATE INDEX ix_qra_supply ON ust.qra_supply(qra_refunding_id,normalized_security_term);
CREATE TABLE ust.qra_financing_mix (
 qra_financing_mix_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, period_start date NOT NULL, period_end date NOT NULL,
 fiscal_year integer, fiscal_quarter smallint, privately_held_net_market_borrowing_usd numeric(24,2), net_coupon_issuance_usd numeric(24,2),
 implied_change_in_bills_usd numeric(24,2), assumed_buybacks_usd numeric(24,2), end_tga_usd numeric(24,2), value_class text NOT NULL,
 source_authority text NOT NULL, source_locator jsonb NOT NULL, calculation_method text,
 input_record_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[], rounding_rule text, UNIQUE(qra_refunding_id,period_start,value_class)
);
CREATE INDEX ix_qra_mix_period ON ust.qra_financing_mix(period_start DESC);
CREATE TABLE ust.qra_tga_path (
 qra_tga_path_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, observation_date date NOT NULL,
 point_type text NOT NULL CHECK (point_type IN ('ACTUAL_START','QUARTER_END_ASSUMPTION','INTERMEDIATE_PEAK','NEXT_QUARTER_END_ASSUMPTION')),
 balance_usd numeric(24,2) NOT NULL CHECK (balance_usd >= 0), range_low_usd numeric(24,2), range_high_usd numeric(24,2),
 value_class text NOT NULL, source_authority text NOT NULL, source_locator jsonb NOT NULL,
 UNIQUE(qra_refunding_id,observation_date,point_type,value_class), CHECK (range_low_usd <= range_high_usd)
);
CREATE INDEX ix_qra_tga ON ust.qra_tga_path(qra_refunding_id,observation_date);
CREATE TABLE ust.qra_guidance (
 qra_guidance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version,
 instrument_group text NOT NULL CHECK (instrument_group IN ('NOMINAL_COUPON','TIPS','FRN','BILL')),
 guidance_status text NOT NULL CHECK (guidance_status IN ('INCREASE','DECREASE','UNCHANGED','MAINTAIN','FLEXIBLE','OTHER')),
 effective_period text, evidence_text text NOT NULL, value_class text NOT NULL, source_authority text NOT NULL, source_locator jsonb NOT NULL,
 UNIQUE(qra_refunding_id,instrument_group,evidence_text)
);
CREATE TABLE ust.qra_tentative_auction (
 qra_tentative_auction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, calendar_name text, calendar_start_date date, calendar_end_date date,
 security_term text, security_type text, reopening boolean, tips boolean, floating_rate boolean, announcement_date date,
 auction_date date NOT NULL, settlement_date date, source_locator jsonb NOT NULL,
 value_class text NOT NULL DEFAULT 'OFFICIAL_ESTIMATE', source_authority text NOT NULL DEFAULT 'US_TREASURY',
 UNIQUE NULLS NOT DISTINCT(qra_refunding_id,auction_date,security_type,security_term,reopening)
);
CREATE INDEX ix_qra_schedule ON ust.qra_tentative_auction(auction_date,security_type,security_term);
CREATE TABLE ust.qra_buyback_operation (
 qra_buyback_operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, calendar_name text, calendar_start_date date, calendar_end_date date,
 purchase_bucket_name text, security_type text, operation_type text, minimum_purchase_amount_usd numeric(24,2), maximum_purchase_amount_usd numeric(24,2),
 maturity_date_range_start date, maturity_date_range_end date, announcement_date date, operation_date date NOT NULL, settlement_date date,
 operation_start_time_et time, operation_end_time_et time, source_timezone text NOT NULL DEFAULT 'America/New_York', source_locator jsonb NOT NULL,
 value_class text NOT NULL DEFAULT 'OFFICIAL_ESTIMATE', source_authority text NOT NULL DEFAULT 'US_TREASURY',
 UNIQUE NULLS NOT DISTINCT(qra_refunding_id,operation_date,purchase_bucket_name,operation_type,operation_start_time_et),
 CHECK (minimum_purchase_amount_usd <= maximum_purchase_amount_usd), CHECK (maturity_date_range_start <= maturity_date_range_end)
);
CREATE INDEX ix_qra_buyback ON ust.qra_buyback_operation(operation_date,purchase_bucket_name);
CREATE TABLE ust.qra_buyback_policy (
 qra_buyback_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, operation_purpose text NOT NULL,
 maximum_amount_usd numeric(24,2) NOT NULL CHECK(maximum_amount_usd>=0), evidence_text text NOT NULL,
 value_class text NOT NULL, source_authority text NOT NULL, source_locator jsonb NOT NULL,
 UNIQUE(qra_refunding_id,operation_purpose,value_class)
);
CREATE TABLE ust.qra_dealer_survey (
 qra_dealer_survey_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_refunding_id uuid NOT NULL REFERENCES ust.qra_refunding ON DELETE CASCADE,
 qra_document_version_id uuid NOT NULL REFERENCES ust.qra_document_version, survey_as_of_date date,
 survey_as_of_month date NOT NULL, date_precision text NOT NULL CHECK(date_precision IN ('DAY','MONTH')), target_fiscal_year integer,
 target_period_start date, target_period_end date, expected_increase_timing text, source_sheet text, source_table text,
 validation_status text NOT NULL DEFAULT 'UNVERIFIED' CHECK (validation_status IN ('VERIFIED','UNVERIFIED','QUARANTINED')),
 value_class text NOT NULL DEFAULT 'PRIMARY_DEALER_SURVEY' CHECK (value_class='PRIMARY_DEALER_SURVEY'),
 source_authority text NOT NULL DEFAULT 'US_TREASURY_PRIMARY_DEALER_SURVEY',
 UNIQUE NULLS NOT DISTINCT(qra_refunding_id,survey_as_of_month,target_period_end)
);
CREATE TABLE ust.qra_dealer_survey_value (
 qra_dealer_survey_value_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), qra_dealer_survey_id uuid NOT NULL REFERENCES ust.qra_dealer_survey ON DELETE CASCADE,
 normalized_security_term text NOT NULL, security_type text NOT NULL, reopening boolean, scenario text NOT NULL,
 statistic text NOT NULL, current_auction_size_usd numeric(24,2) CHECK (current_auction_size_usd >= 0),
 expected_auction_size_usd numeric(24,2) CHECK (expected_auction_size_usd >= 0), calculated_pct_change numeric(18,9),
 source_locator jsonb NOT NULL, formula text, calculation_version text,
 UNIQUE NULLS NOT DISTINCT(qra_dealer_survey_id,security_type,normalized_security_term,reopening,statistic,scenario)
);
CREATE TABLE ust.derived_metric_method (
 derived_metric_method_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), method_code text NOT NULL, version text NOT NULL,
 name text NOT NULL, description text NOT NULL, formula text NOT NULL, unit text NOT NULL,
 value_class text NOT NULL DEFAULT 'DERIVED_UI_PROXY' CHECK (value_class='DERIVED_UI_PROXY'),
 source_authority text NOT NULL DEFAULT 'UI_METHOD_CONFIG', effective_from date NOT NULL, effective_to date, rounding_rule text,
 is_official_treasury_metric boolean NOT NULL DEFAULT false, UNIQUE(method_code,version), CHECK (effective_to >= effective_from)
);
CREATE TABLE ust.derived_metric_method_parameter (
 derived_metric_method_parameter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), derived_metric_method_id uuid NOT NULL REFERENCES ust.derived_metric_method ON DELETE CASCADE,
 parameter_name text NOT NULL, parameter_key text NOT NULL, numeric_value numeric(18,9), text_value text, unit text,
 UNIQUE(derived_metric_method_id,parameter_name,parameter_key), CHECK ((numeric_value IS NOT NULL)::int+(text_value IS NOT NULL)::int=1)
);
INSERT INTO ust.derived_metric_method(method_code,version,name,description,formula,unit,effective_from,rounding_rule)
VALUES ('DV01_10Y_EQUIVALENT_PROXY','ui_proxy_v1','화면용 10Y-equivalent DV01 proxy','확정 화면에서 역산한 가중치. 미국 재무부 공식 지표가 아님.',
 'net_issuance_usd * tenor_weight','USD 10Y-equivalent','2026-08-01','Decimal; display half-up');
INSERT INTO ust.derived_metric_method_parameter(derived_metric_method_id,parameter_name,parameter_key,numeric_value,unit)
SELECT m.derived_metric_method_id,'tenor_weight',v.term,v.weight,'ratio'
FROM ust.derived_metric_method m CROSS JOIN (VALUES ('2Y',0.20::numeric),('3Y',0.30::numeric),('5Y',0.50::numeric),('7Y',0.70::numeric),('10Y',1.00::numeric),('20Y',1.65::numeric),('30Y',2.05::numeric)) v(term,weight)
WHERE m.version='ui_proxy_v1';

ALTER TABLE ust.qra_supply ADD CONSTRAINT fk_supply_method FOREIGN KEY(dv01_method_id) REFERENCES ust.derived_metric_method;
CREATE TABLE ust.derived_metric_result (
 derived_metric_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), derived_metric_method_id uuid NOT NULL REFERENCES ust.derived_metric_method,
 entity_type text NOT NULL, entity_id uuid NOT NULL, source_document_version_id uuid REFERENCES ust.qra_document_version,
 metric_value numeric(30,9), input_record_ids uuid[] NOT NULL, input_values jsonb NOT NULL, formula text NOT NULL,
 rounding_rule text NOT NULL, value_class text NOT NULL DEFAULT 'DERIVED_UI_PROXY' CHECK(value_class='DERIVED_UI_PROXY'),
 calculated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(derived_metric_method_id,entity_type,entity_id,source_document_version_id)
);

CREATE VIEW ust.v_auction_prior_comparable AS
SELECT e.auction_event_id,p.auction_event_id AS prior_auction_event_id,p.auction_date AS prior_auction_date,
 pr.stop_metric_code AS prior_stop_metric_code,pr.stop_value AS prior_stop_value,
 pr.bid_to_cover_ratio AS prior_bid_to_cover_ratio,
 pa.indirect_bidder_accepted_usd/NULLIF(pr.total_accepted_usd,0)*100 AS prior_indirect_share_pct,
 pa.direct_bidder_accepted_usd/NULLIF(pr.total_accepted_usd,0)*100 AS prior_direct_share_pct,
 pa.primary_dealer_accepted_usd/NULLIF(pr.total_accepted_usd,0)*100 AS prior_primary_dealer_share_pct,
 avg6.stop_average AS prior_six_valid_stop_average,avg6.sample_count AS prior_six_valid_stop_sample_count
FROM ust.auction_event e
LEFT JOIN LATERAL (
 SELECT pe.* FROM ust.auction_event pe JOIN ust.auction_result px USING(auction_event_id)
 WHERE pe.security_type=e.security_type AND pe.normalized_security_term=e.normalized_security_term
 AND pe.auction_date<e.auction_date AND px.stop_value IS NOT NULL
 ORDER BY pe.auction_date DESC,pe.auction_event_id DESC LIMIT 1
) p ON true
LEFT JOIN ust.auction_result pr ON pr.auction_event_id=p.auction_event_id
LEFT JOIN ust.auction_bidder_allocation pa ON pa.auction_event_id=p.auction_event_id
LEFT JOIN LATERAL (
 SELECT avg(x.stop_value) AS stop_average,count(*)::integer AS sample_count FROM (
  SELECT xr.stop_value FROM ust.auction_event xe JOIN ust.auction_result xr USING(auction_event_id)
  WHERE xe.security_type=e.security_type AND xe.normalized_security_term=e.normalized_security_term
  AND xe.auction_date<e.auction_date AND xr.stop_value IS NOT NULL ORDER BY xe.auction_date DESC,xe.auction_event_id DESC LIMIT 6
 ) x
) avg6 ON true;

CREATE VIEW ust.v_auction_dashboard AS
SELECT e.auction_event_id,e.cusip,e.security_type,e.security_term,e.normalized_security_term,e.reopening,e.announcement_date,
 e.auction_date,e.closing_time_comp_et,e.source_timezone,e.issue_date,e.maturity_date,e.offering_amount_usd,
 r.interest_rate AS coupon_rate,r.stop_metric_code,r.stop_metric_label,r.stop_value,r.bid_to_cover_ratio,
 r.bid_to_cover_ratio*100 AS bid_to_cover_display_pct,r.allocation_percentage AS allotted_at_high_pct,r.price_per_100,
 a.indirect_bidder_accepted_usd/NULLIF(r.total_accepted_usd,0)*100 AS indirect_share_pct,
 a.direct_bidder_accepted_usd/NULLIF(r.total_accepted_usd,0)*100 AS direct_share_pct,
 a.primary_dealer_accepted_usd/NULLIF(r.total_accepted_usd,0)*100 AS primary_dealer_share_pct,
 CASE WHEN 100-(a.indirect_bidder_accepted_usd+a.direct_bidder_accepted_usd+a.primary_dealer_accepted_usd)/NULLIF(r.total_accepted_usd,0)*100 BETWEEN 0 AND 100
 THEN 100-(a.indirect_bidder_accepted_usd+a.direct_bidder_accepted_usd+a.primary_dealer_accepted_usd)/NULLIF(r.total_accepted_usd,0)*100 END AS other_ui_residual_pct,
 pc.prior_auction_event_id,pc.prior_stop_value,pc.prior_bid_to_cover_ratio,pc.prior_six_valid_stop_average,pc.prior_six_valid_stop_sample_count,
 a.indirect_bidder_accepted_usd/NULLIF(r.total_accepted_usd,0)*100-pc.prior_indirect_share_pct AS indirect_change_pp,
 a.direct_bidder_accepted_usd/NULLIF(r.total_accepted_usd,0)*100-pc.prior_direct_share_pct AS direct_change_pp,
 a.primary_dealer_accepted_usd/NULLIF(r.total_accepted_usd,0)*100-pc.prior_primary_dealer_share_pct AS primary_dealer_change_pp,
 CASE WHEN r.bid_to_cover_ratio IS NULL THEN 'ANNOUNCED' ELSE 'RESULT_AVAILABLE' END AS event_status,
 e.current_snapshot_id,e.last_seen_at
FROM ust.auction_event e LEFT JOIN ust.auction_result r USING(auction_event_id)
LEFT JOIN ust.auction_bidder_allocation a USING(auction_event_id) LEFT JOIN ust.v_auction_prior_comparable pc USING(auction_event_id);

CREATE VIEW ust.v_qra_supply_monitor AS
SELECT r.qra_refunding_id,r.refunding_year,r.refunding_month,s.period_start,s.period_end,s.fiscal_year,s.fiscal_quarter,
 s.security_type,s.normalized_security_term,s.gross_issuance_usd,s.maturing_amount_usd,s.net_issuance_usd,
 p.numeric_value AS tenor_weight,s.net_issuance_usd*p.numeric_value AS dv01_10y_equivalent_proxy_usd,m.version AS calculation_version,
 s.value_class,s.source_authority,s.source_locator,s.qra_supply_id,s.dv01_method_id,
 'DERIVED_UI_PROXY'::text AS proxy_value_class,'net_issuance_usd * tenor_weight'::text AS proxy_formula,
 ARRAY[s.qra_supply_id] AS proxy_input_record_ids,m.rounding_rule
FROM ust.qra_supply s JOIN ust.qra_refunding r USING(qra_refunding_id)
LEFT JOIN ust.derived_metric_method m ON m.derived_metric_method_id=s.dv01_method_id
LEFT JOIN ust.derived_metric_method_parameter p ON p.derived_metric_method_id=m.derived_metric_method_id
 AND p.parameter_name='tenor_weight' AND p.parameter_key=s.normalized_security_term;
CREATE VIEW ust.v_qra_comparison AS
WITH ordered AS (SELECT r.*,lag(qra_refunding_id) OVER(ORDER BY refunding_year,refunding_month) AS prior_refunding_id FROM ust.qra_refunding r)
SELECT o.qra_refunding_id,o.refunding_year,o.refunding_month,o.release_datetime,o.prior_refunding_id,
 b.calendar_year,b.calendar_quarter,b.borrowing_amount_usd,COALESCE(b.prior_estimate_usd,pb.borrowing_amount_usd) AS prior_estimate_usd,
 COALESCE(b.change_from_prior_usd,b.borrowing_amount_usd-COALESCE(b.prior_estimate_usd,pb.borrowing_amount_usd)) AS borrowing_change_usd,
 b.end_cash_balance_usd,b.value_class,b.source_authority,b.qra_borrowing_estimate_id AS current_estimate_record_id,
 pb.qra_borrowing_estimate_id AS prior_estimate_record_id,b.qra_document_version_id,
 b.borrowing_amount_usd-pb.borrowing_amount_usd AS cross_document_change_usd
FROM ordered o LEFT JOIN ust.qra_borrowing_estimate b USING(qra_refunding_id)
LEFT JOIN ust.qra_borrowing_estimate pb ON pb.qra_refunding_id=o.prior_refunding_id
 AND pb.calendar_year=b.calendar_year AND pb.calendar_quarter=b.calendar_quarter AND pb.value_class='OFFICIAL_ESTIMATE';
CREATE VIEW ust.v_qra_tga_path AS
SELECT r.refunding_year,r.refunding_month,r.release_datetime,t.* FROM ust.qra_tga_path t JOIN ust.qra_refunding r USING(qra_refunding_id);
CREATE VIEW ust.v_qra_dealer_outlook AS
SELECT r.refunding_year,r.refunding_month,s.qra_dealer_survey_id,s.survey_as_of_date,s.target_period_start,s.target_period_end,
 s.expected_increase_timing,s.validation_status,s.survey_as_of_month,s.date_precision,s.target_fiscal_year,
 v.security_type,v.reopening,v.scenario,v.normalized_security_term,v.statistic,v.current_auction_size_usd,v.expected_auction_size_usd,
 (v.expected_auction_size_usd/NULLIF(v.current_auction_size_usd,0)-1)*100 AS pct_change,v.source_locator
FROM ust.qra_dealer_survey s JOIN ust.qra_refunding r USING(qra_refunding_id)
JOIN ust.qra_dealer_survey_value v USING(qra_dealer_survey_id) WHERE s.validation_status='VERIFIED';

CREATE VIEW ust.v_qra_auction_size_comparison AS
SELECT s.*,p.qra_auction_size_id AS prior_record_id,p.auction_size_usd AS comparable_prior_size_usd,
 s.auction_size_usd-p.auction_size_usd AS comparable_change_usd
FROM ust.qra_auction_size s JOIN ust.qra_refunding r USING(qra_refunding_id)
LEFT JOIN LATERAL (
 SELECT ps.* FROM ust.qra_auction_size ps JOIN ust.qra_refunding pr USING(qra_refunding_id)
 WHERE (pr.refunding_year,pr.refunding_month)<(r.refunding_year,r.refunding_month)
 AND ps.auction_month=s.auction_month AND ps.security_type=s.security_type
 AND ps.normalized_security_term=s.normalized_security_term AND ps.reopening IS NOT DISTINCT FROM s.reopening
 AND ((ps.value_class IN ('OFFICIAL_ACTUAL','OFFICIAL_ESTIMATE') AND s.value_class IN ('OFFICIAL_ACTUAL','OFFICIAL_ESTIMATE')) OR ps.value_class=s.value_class)
 ORDER BY pr.refunding_year DESC,pr.refunding_month DESC LIMIT 1
) p ON true;
CREATE VIEW ust.v_ingestion_status AS
SELECT source_name,max(started_at) AS last_attempt_at,max(finished_at) FILTER(WHERE status='SUCCESS') AS last_success_at,
 (array_agg(status ORDER BY started_at DESC))[1] AS last_run_status,
 (array_agg(requested_from ORDER BY started_at DESC))[1] AS requested_from,
 (array_agg(requested_to ORDER BY started_at DESC))[1] AS requested_to,
 (array_agg(rows_received ORDER BY started_at DESC))[1] AS received,
 (array_agg(rows_rejected ORDER BY started_at DESC))[1] AS rejected,
 (array_agg(error_summary ORDER BY started_at DESC))[1] AS last_error
FROM ust.ingestion_run GROUP BY source_name;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['qra_auction_size','qra_supply','qra_financing_mix','qra_tga_path','qra_guidance','qra_tentative_auction','qra_buyback_operation','qra_buyback_policy'] LOOP
  EXECUTE format('ALTER TABLE ust.%I ADD CHECK (value_class IN (''OFFICIAL_ACTUAL'',''OFFICIAL_ESTIMATE'',''TBAC_RECOMMENDATION'',''PRIMARY_DEALER_SURVEY'',''DERIVED_UI_PROXY''))',t);
 END LOOP;
END $$;
