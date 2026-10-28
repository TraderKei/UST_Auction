"""Use competitive awards for bidder allocation shares.

Revision ID: 20261028_0003
Revises: 20261007_0002
"""

from alembic import op


revision = "20261028_0003"
down_revision = "20261007_0002"
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE OR REPLACE VIEW ust.v_auction_prior_comparable AS
SELECT e.auction_event_id,p.auction_event_id AS prior_auction_event_id,p.auction_date AS prior_auction_date,
 pr.stop_metric_code AS prior_stop_metric_code,pr.stop_value AS prior_stop_value,
 pr.bid_to_cover_ratio AS prior_bid_to_cover_ratio,
 pa.indirect_bidder_accepted_usd/NULLIF(pr.competitive_accepted_usd,0)*100 AS prior_indirect_share_pct,
 pa.direct_bidder_accepted_usd/NULLIF(pr.competitive_accepted_usd,0)*100 AS prior_direct_share_pct,
 pa.primary_dealer_accepted_usd/NULLIF(pr.competitive_accepted_usd,0)*100 AS prior_primary_dealer_share_pct,
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

CREATE OR REPLACE VIEW ust.v_auction_dashboard AS
SELECT e.auction_event_id,e.cusip,e.security_type,e.security_term,e.normalized_security_term,e.reopening,e.announcement_date,
 e.auction_date,e.closing_time_comp_et,e.source_timezone,e.issue_date,e.maturity_date,e.offering_amount_usd,
 r.interest_rate AS coupon_rate,r.stop_metric_code,r.stop_metric_label,r.stop_value,r.bid_to_cover_ratio,
 r.bid_to_cover_ratio*100 AS bid_to_cover_display_pct,r.allocation_percentage AS allotted_at_high_pct,r.price_per_100,
 a.indirect_bidder_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100 AS indirect_share_pct,
 a.direct_bidder_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100 AS direct_share_pct,
 a.primary_dealer_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100 AS primary_dealer_share_pct,
 CASE WHEN 100-(a.indirect_bidder_accepted_usd+a.direct_bidder_accepted_usd+a.primary_dealer_accepted_usd)/NULLIF(r.competitive_accepted_usd,0)*100 BETWEEN 0 AND 100
 THEN 100-(a.indirect_bidder_accepted_usd+a.direct_bidder_accepted_usd+a.primary_dealer_accepted_usd)/NULLIF(r.competitive_accepted_usd,0)*100 END AS other_ui_residual_pct,
 pc.prior_auction_event_id,pc.prior_stop_value,pc.prior_bid_to_cover_ratio,pc.prior_six_valid_stop_average,pc.prior_six_valid_stop_sample_count,
 a.indirect_bidder_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100-pc.prior_indirect_share_pct AS indirect_change_pp,
 a.direct_bidder_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100-pc.prior_direct_share_pct AS direct_change_pp,
 a.primary_dealer_accepted_usd/NULLIF(r.competitive_accepted_usd,0)*100-pc.prior_primary_dealer_share_pct AS primary_dealer_change_pp,
 CASE WHEN r.bid_to_cover_ratio IS NULL THEN 'ANNOUNCED' ELSE 'RESULT_AVAILABLE' END AS event_status,
 e.current_snapshot_id,e.last_seen_at
FROM ust.auction_event e LEFT JOIN ust.auction_result r USING(auction_event_id)
LEFT JOIN ust.auction_bidder_allocation a USING(auction_event_id) LEFT JOIN ust.v_auction_prior_comparable pc USING(auction_event_id);
"""


def upgrade() -> None:
    for statement in VIEW_SQL.strip().split(";\n\n"):
        op.execute(statement)


def downgrade() -> None:
    for statement in VIEW_SQL.strip().replace("competitive_accepted_usd", "total_accepted_usd").split(";\n\n"):
        op.execute(statement)
