from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .auction import AuctionRecord


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    rule: str
    field: str | None
    message: str


def validate_auction(record: AuctionRecord) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if record.issue_date and record.maturity_date and record.maturity_date <= record.issue_date:
        issues.append(ValidationIssue("ERROR", "MATURITY_AFTER_ISSUE", "maturity_date", "maturity_date must be after issue_date"))
    if record.announcemt_date and record.auction_date < record.announcemt_date:
        issues.append(ValidationIssue("WARN", "AUCTION_BEFORE_ANNOUNCEMENT", "auction_date", "auction precedes announcement"))
    for field in ("offering_amt", "total_tendered", "total_accepted", "comp_tendered", "comp_accepted", "noncomp_accepted",
                  "primary_dealer_accepted", "direct_bidder_accepted", "indirect_bidder_accepted", "bid_to_cover_ratio"):
        value = getattr(record, field)
        if value is not None and value < 0:
            issues.append(ValidationIssue("ERROR", "NEGATIVE_NONNEGATIVE_FIELD", field, "value must be nonnegative"))
    if record.allocation_pctage is not None and not Decimal("0") <= record.allocation_pctage <= Decimal("100"):
        issues.append(ValidationIssue("ERROR", "ALLOCATION_PERCENT_RANGE", "allocation_pctage", "percentage must be 0..100"))
    accepted = [record.indirect_bidder_accepted, record.direct_bidder_accepted, record.primary_dealer_accepted]
    if all(value is not None for value in accepted) and record.total_accepted is not None:
        if sum(accepted, Decimal("0")) > record.total_accepted:
            issues.append(ValidationIssue("ERROR", "BIDDER_SUM_EXCEEDS_TOTAL", "total_accepted", "bidder accepted sum exceeds total accepted"))
    if record.issue_date is None:
        issues.append(ValidationIssue("WARN", "NULL_CANDIDATE_KEY_COMPONENT", "issue_date", "NULL issue_date retained with deterministic business key and surrogate id"))
    if record.stop_metric_code == "UNMAPPED":
        issues.append(ValidationIssue("WARN", "UNMAPPED_STOP", "security_type", "security type has no supported stop mapping"))
    return issues
