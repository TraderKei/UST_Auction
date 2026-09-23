from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo


PERCENT = Decimal("100")


def bid_to_cover_percent(ratio: Decimal | None) -> Decimal | None:
    return None if ratio is None else (ratio * PERCENT).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def accepted_share(accepted: Decimal | None, total_accepted: Decimal | None) -> Decimal | None:
    if accepted is None or total_accepted is None or total_accepted == 0:
        return None
    return (accepted / total_accepted * PERCENT).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def other_ui_residual(
    indirect: Decimal | None, direct: Decimal | None, primary_dealer: Decimal | None
) -> Decimal | None:
    if indirect is None or direct is None or primary_dealer is None:
        return None
    residual = PERCENT - indirect - direct - primary_dealer
    return residual if Decimal("0") <= residual <= PERCENT else None


def percentage_point_change(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    return None if current is None or prior is None else current - prior


def valid_trailing_average(
    observations: list[Decimal | None], maximum: int = 6
) -> tuple[Decimal | None, int]:
    valid = [value for value in observations if value is not None][:maximum]
    if not valid:
        return None, 0
    return sum(valid, Decimal("0")) / Decimal(len(valid)), len(valid)


def et_to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("America/New_York"))
    return value.astimezone(ZoneInfo("Asia/Seoul"))


def dv01_proxy(net_issuance: Decimal | None, tenor_weight: Decimal | None) -> Decimal | None:
    if net_issuance is None or tenor_weight is None:
        return None
    return net_issuance * tenor_weight


def pct_change(future: Decimal | None, current: Decimal | None) -> Decimal | None:
    if future is None or current in (None, Decimal("0")):
        return None
    return (future / current - Decimal("1")) * PERCENT
