-- PostgreSQL 16+. Independent of the earlier unverified UI/D1 draft.
CREATE SCHEMA IF NOT EXISTS ust;

CREATE TABLE ust.ingestion_run (
 run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_name text NOT NULL, job_type text NOT NULL,
 requested_from date, requested_to date, started_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
 status text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCESS','PARTIAL_FAILURE','FAILED','DRY_RUN')),
 pages_attempted integer NOT NULL DEFAULT 0, pages_succeeded integer NOT NULL DEFAULT 0,
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
 source_name text NOT NULL, source_url text NOT NULL, final_url text NOT NULL, content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'), mime_type text NOT NULL,
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

CREATE VIEW ust.v_ingestion_status AS
SELECT source_name,max(started_at) AS last_attempt_at,max(finished_at) FILTER(WHERE status='SUCCESS') AS last_success_at,
 (array_agg(status ORDER BY started_at DESC))[1] AS last_run_status,
 (array_agg(requested_from ORDER BY started_at DESC))[1] AS requested_from,
 (array_agg(requested_to ORDER BY started_at DESC))[1] AS requested_to,
 (array_agg(rows_received ORDER BY started_at DESC))[1] AS received,
 (array_agg(rows_rejected ORDER BY started_at DESC))[1] AS rejected,
 (array_agg(error_summary ORDER BY started_at DESC))[1] AS last_error
FROM ust.ingestion_run GROUP BY source_name;
