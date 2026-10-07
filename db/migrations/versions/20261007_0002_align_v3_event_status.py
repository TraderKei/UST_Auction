"""Align auction dashboard event status with the v3 screen contract.

Revision ID: 20261007_0002
Revises: 20260903_0001
"""

from alembic import op


revision = "20261007_0002"
down_revision = "20260903_0001"
branch_labels = None
depends_on = None


VIEW_SQL = """
CREATE OR REPLACE VIEW ust.v_auction_dashboard AS
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
LEFT JOIN ust.auction_bidder_allocation a USING(auction_event_id) LEFT JOIN ust.v_auction_prior_comparable pc USING(auction_event_id)
"""


def upgrade() -> None:
    op.execute(VIEW_SQL)


def downgrade() -> None:
    op.execute(VIEW_SQL.replace("r.bid_to_cover_ratio IS NULL", "r.stop_value IS NULL"))
