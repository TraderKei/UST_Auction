-- PostgreSQL 16 reference schema for a production Treasury auction terminal.
-- Monetary values use NUMERIC rather than floating point; API empty strings become NULL.

CREATE TYPE security_type AS ENUM ('Bill', 'Note', 'Bond', 'TIPS', 'FRN', 'CMB');
CREATE TYPE auction_status AS ENUM ('announced', 'open', 'resulted', 'cancelled');
CREATE TYPE stop_metric AS ENUM ('discount_rate', 'investment_rate', 'yield', 'real_yield', 'discount_margin');
CREATE TYPE bidder_type AS ENUM ('primary_dealer', 'direct', 'indirect', 'noncompetitive', 'treasury_retail', 'soma', 'fima');

CREATE TABLE security_master (
  cusip                 CHAR(9) PRIMARY KEY,
  security_type         security_type NOT NULL,
  original_term         VARCHAR(32) NOT NULL,
  original_issue_date   DATE,
  maturity_date         DATE NOT NULL,
  interest_rate         NUMERIC(9,6),
  is_tips               BOOLEAN NOT NULL DEFAULT FALSE,
  is_floating_rate      BOOLEAN NOT NULL DEFAULT FALSE,
  payment_frequency     VARCHAR(24),
  series_name           VARCHAR(80),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auction (
  auction_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cusip                   CHAR(9) NOT NULL REFERENCES security_master(cusip),
  announcement_date       DATE NOT NULL,
  auction_date            DATE NOT NULL,
  issue_date              DATE NOT NULL,
  security_term           VARCHAR(32) NOT NULL,
  offering_amount         NUMERIC(20,2) NOT NULL CHECK (offering_amount > 0),
  competitive_close_et    TIME,
  noncompetitive_close_et TIME,
  auction_format          VARCHAR(32),
  status                  auction_status NOT NULL DEFAULT 'announced',
  is_reopening            BOOLEAN NOT NULL DEFAULT FALSE,
  is_cash_management_bill BOOLEAN NOT NULL DEFAULT FALSE,
  source_updated_at       TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_auction_business_key UNIQUE (cusip, auction_date, issue_date)
);

CREATE TABLE auction_result (
  auction_id             BIGINT PRIMARY KEY REFERENCES auction(auction_id) ON DELETE CASCADE,
  stop_metric            stop_metric NOT NULL,
  stop_value             NUMERIC(9,6) NOT NULL,
  investment_rate        NUMERIC(9,6),
  coupon_rate            NUMERIC(9,6),
  price_per_100           NUMERIC(12,6),
  bid_to_cover_ratio     NUMERIC(8,4),
  allocation_percentage NUMERIC(8,4),
  total_tendered         NUMERIC(20,2),
  total_accepted         NUMERIC(20,2),
  competitive_tendered   NUMERIC(20,2),
  competitive_accepted   NUMERIC(20,2),
  published_at           TIMESTAMPTZ,
  CONSTRAINT ck_bid_to_cover_positive CHECK (bid_to_cover_ratio IS NULL OR bid_to_cover_ratio > 0),
  CONSTRAINT ck_total_award CHECK (total_accepted IS NULL OR total_accepted >= 0)
);

CREATE TABLE bidder_allocation (
  auction_id       BIGINT NOT NULL REFERENCES auction(auction_id) ON DELETE CASCADE,
  bidder_type      bidder_type NOT NULL,
  tendered_amount  NUMERIC(20,2),
  accepted_amount  NUMERIC(20,2),
  acceptance_rate NUMERIC(8,4) GENERATED ALWAYS AS
    (CASE WHEN tendered_amount > 0 THEN accepted_amount / tendered_amount * 100 END) STORED,
  PRIMARY KEY (auction_id, bidder_type)
);

CREATE TABLE source_snapshot (
  snapshot_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  endpoint           TEXT NOT NULL,
  fetched_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  http_status        SMALLINT NOT NULL,
  payload_hash       CHAR(64) NOT NULL,
  raw_payload        JSONB NOT NULL,
  record_count       INTEGER NOT NULL,
  transform_version  VARCHAR(32) NOT NULL,
  CONSTRAINT uq_snapshot_hash UNIQUE (endpoint, payload_hash)
);

CREATE TABLE auction_source_link (
  auction_id   BIGINT NOT NULL REFERENCES auction(auction_id) ON DELETE CASCADE,
  snapshot_id  BIGINT NOT NULL REFERENCES source_snapshot(snapshot_id) ON DELETE RESTRICT,
  PRIMARY KEY (auction_id, snapshot_id)
);

-- Hot-path indexes mirror the terminal's schedule, tape, and security-history queries.
CREATE INDEX idx_security_type_cusip ON security_master (security_type, cusip);
CREATE INDEX idx_auction_date ON auction (auction_date DESC, cusip);
CREATE INDEX idx_auction_upcoming ON auction (status, auction_date) WHERE status <> 'resulted';
CREATE INDEX idx_auction_cusip_history ON auction (cusip, auction_date DESC);
CREATE INDEX idx_auction_term_history ON auction (security_term, auction_date DESC);
CREATE INDEX idx_result_bid_to_cover ON auction_result (bid_to_cover_ratio DESC) WHERE bid_to_cover_ratio IS NOT NULL;
CREATE INDEX idx_snapshot_fetched_at ON source_snapshot (fetched_at DESC);

CREATE VIEW v_auction_terminal AS
SELECT
  a.auction_id, a.auction_date, a.issue_date, a.announcement_date, a.status,
  s.cusip, s.security_type, a.security_term, s.maturity_date, a.offering_amount,
  a.competitive_close_et, a.is_reopening, a.is_cash_management_bill,
  r.stop_metric, r.stop_value, r.investment_rate, r.coupon_rate,
  r.price_per_100, r.bid_to_cover_ratio, r.total_tendered, r.total_accepted
FROM auction a
JOIN security_master s USING (cusip)
LEFT JOIN auction_result r USING (auction_id);

-- Main screen view: every announced line with the latest earlier result for
-- the same security type and auction term. This is the compact comparison
-- rendered in the forward calendar.
CREATE VIEW v_auction_monitor AS
SELECT
  current_auction.*,
  prior.auction_id          AS prior_auction_id,
  prior.auction_date        AS prior_auction_date,
  prior.stop_metric         AS prior_stop_metric,
  prior.stop_value          AS prior_stop_value,
  prior.bid_to_cover_ratio  AS prior_bid_to_cover_ratio,
  prior.indirect_award_pct  AS prior_indirect_award_pct
FROM v_auction_terminal current_auction
LEFT JOIN LATERAL (
  SELECT
    pa.auction_id,
    pa.auction_date,
    pr.stop_metric,
    pr.stop_value,
    pr.bid_to_cover_ratio,
    CASE WHEN pr.total_accepted > 0
      THEN iba.accepted_amount / pr.total_accepted * 100
    END AS indirect_award_pct
  FROM auction pa
  JOIN security_master ps ON ps.cusip = pa.cusip
  JOIN auction_result pr ON pr.auction_id = pa.auction_id
  LEFT JOIN bidder_allocation iba
    ON iba.auction_id = pa.auction_id
   AND iba.bidder_type = 'indirect'
  WHERE ps.security_type = current_auction.security_type
    AND pa.security_term = current_auction.security_term
    AND pa.auction_date < current_auction.auction_date
  ORDER BY pa.auction_date DESC
  LIMIT 1
) prior ON TRUE;

ANALYZE security_master;
ANALYZE auction;
ANALYZE auction_result;
ANALYZE bidder_allocation;
