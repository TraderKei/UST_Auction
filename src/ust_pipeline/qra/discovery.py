from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from lxml import html


QRA_PATH_MARKER = "/policy-issues/financing-the-government/quarterly-refunding/"
ALLOWED_HOST = "home.treasury.gov"


@dataclass(frozen=True)
class QraLink:
    url: str
    anchor_text: str
    document_type: str
    discovered_on_url: str
    release_datetime: datetime | None
    refunding_year: int | None
    refunding_quarter: int | None


@dataclass(frozen=True)
class QraIndex:
    links: list[QraLink]
    next_release_dates: list[date]


def canonicalize_url(base_url: str, href: str) -> str:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def is_allowed_qra_url(url: str, directly_linked_document: bool = False) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.hostname != ALLOWED_HOST:
        return False
    if QRA_PATH_MARKER in parts.path:
        return True
    return directly_linked_document and (
        parts.path.startswith("/system/files/")
        or parts.path.startswith("/news/press-releases/")
    )


def classify_document(anchor_text: str, url: str) -> str:
    value = f"{anchor_text} {url}".lower()
    if "primary-dealer-auction-size-survey" in urlsplit(url).path:
        return "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"
    if QRA_PATH_MARKER in urlsplit(url).path and "archives" in urlsplit(url).path:
        return "QRA_ARCHIVE_HTML"
    if ("auction_survey" in value or "auctionsurvey" in value) and url.lower().endswith(".pdf"):
        return "PRIMARY_DEALER_SURVEY_PDF"
    if "financing estimates" in value:
        return "FINANCING_ESTIMATES_HTML"
    if "economic policy statement" in value:
        return "ECONOMIC_POLICY_STATEMENT_HTML"
    if "policy statement" in value:
        return "POLICY_STATEMENT_HTML"
    if "tbac report" in value or "committee report" in value:
        return "TBAC_REPORT_HTML"
    if "tbac minutes" in value or "committee meeting minutes" in value:
        return "TBAC_MINUTES_HTML"
    if "recommended financing" in value or "tbacrecommended" in value:
        return "TBAC_RECOMMENDED_FINANCING_PDF"
    if "treasury presentation" in value or "treasurypresentationtotbac" in value:
        return "TREASURY_PRESENTATION_PDF"
    if "charge" in value and url.lower().endswith(".pdf"):
        return "TBAC_CHARGE_PDF"
    if "auction" in value and url.lower().endswith(".xml"):
        return "TENTATIVE_AUCTION_XML"
    if "auction" in value and url.lower().endswith(".pdf"):
        return "TENTATIVE_AUCTION_PDF"
    if "buyback" in value and url.lower().endswith(".xml"):
        return "TENTATIVE_BUYBACK_XML"
    if "buyback" in value and url.lower().endswith(".pdf"):
        return "TENTATIVE_BUYBACK_PDF"
    if "dealer" in value and "agenda" in value:
        return "PRIMARY_DEALER_AGENDA_PDF"
    if "quarterly release data" in value or url.lower().endswith(".xls"):
        return "QUARTERLY_RELEASE_XLS"
    if "primary-dealer-auction-size-survey" in value:
        return "PRIMARY_DEALER_SURVEY_ARCHIVE_HTML"
    if "archives" in value:
        return "QRA_ARCHIVE_HTML"
    if url.lower().endswith(".pdf"):
        return "OTHER_QRA_PDF"
    if url.lower().endswith((".htm", ".html")) or not urlsplit(url).path.rsplit("/", 1)[-1].count("."):
        return "OTHER_QRA_HTML"
    return "OTHER_QRA_DOCUMENT"


def _release_datetime(text: str) -> datetime | None:
    normalized = re.sub(r"\s+", " ", text).strip().replace("\xa0", " ")
    match = re.search(
        r"(?:released at|scheduled for)\s+(?:(\d{1,2}:\d{2})\s*([ap]m)\s+)?"
        r"(?:[a-z]+,\s*)?([a-z]+)\s+(\d{1,2}),\s*(\d{4})",
        normalized,
        re.I,
    )
    if not match:
        return None
    clock = f"{match.group(1) or '12:00'} {match.group(2) or 'PM'}"
    value = datetime.strptime(
        f"{match.group(3)} {match.group(4)} {match.group(5)} {clock}",
        "%B %d %Y %I:%M %p",
    )
    return value.replace(tzinfo=ZoneInfo("America/New_York"))


def _quarter(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"(20\d{2})\s*[-–:]?\s*(?:q|quarter)?\s*([1-4])(?:st|nd|rd|th)?\s*quarter", text, re.I)
    if not match:
        match = re.search(r"q([1-4])(20\d{2})", text, re.I)
        return (int(match.group(2)), int(match.group(1))) if match else (None, None)
    return int(match.group(1)), int(match.group(2))


def discover_qra_index(content: bytes | str, page_url: str) -> QraIndex:
    root = html.fromstring(content)
    links: list[QraLink] = []
    next_release_dates: list[date] = []
    current_release: datetime | None = None
    in_scope = False
    current_year: int | None = None
    page_title = " ".join(root.xpath("//*[contains(@class,'uswds-page-title')]//text()")) or " ".join(root.xpath("//h1//text()"))

    main = root.xpath("//main")
    scope = main[0] if main else root
    for element in scope.iter():
        if element.tag in {"h1", "h2", "h3", "h4", "h5", "p", "th", "strong"}:
            text_value = " ".join(element.text_content().split())
            lower = text_value.lower()
            if 'uswds-page-title' in (element.get('class') or '') or element.tag == "h1" or any(title in lower for title in ("most recent quarterly refunding documents", "quarterly refunding archives", "primary dealer auction size survey")):
                in_scope = True
            if re.fullmatch(r"(?:19|20)\d{2}", text_value):
                current_year = int(text_value)
            if in_scope and "debt management resources" in lower:
                in_scope = False
            parsed = _release_datetime(text_value)
            if parsed and "documents released" in text_value.lower():
                current_release = parsed
            if parsed and "next release" in text_value.lower():
                next_release_dates.append(parsed.date())
        if not in_scope or element.tag != "a" or not element.get("href"):
            continue
        anchor = " ".join(element.text_content().split())
        url = canonicalize_url(page_url, element.get("href"))
        document_type = classify_document(anchor, url)
        if document_type in {"OTHER_QRA_HTML", "OTHER_QRA_PDF", "TENTATIVE_AUCTION_PDF"}:
            context = re.sub("Official Remarks on Quarterly Refunding", "Policy Statement", page_title, flags=re.I).replace("Quarterly Financing Estimates", "Financing Estimates")
            document_type = classify_document(context + " " + anchor, url)
        relevant = document_type not in {"OTHER_QRA_HTML", "OTHER_QRA_DOCUMENT"}
        if not relevant or not is_allowed_qra_url(url, directly_linked_document=True):
            continue
        year, quarter = _quarter(f"{anchor} {url}")
        quarter_match = re.search(r"([1-4])(?:st|nd|rd|th) Quarter", anchor, re.I)
        if not year and current_year and quarter_match:
            year, quarter = current_year, int(quarter_match.group(1))
        elif not year and current_year:
            year = current_year
        if not year and current_release:
            year, quarter = current_release.year, (current_release.month - 1) // 3 + 1
        links.append(
            QraLink(
                url=url,
                anchor_text=anchor,
                document_type=document_type,
                discovered_on_url=page_url,
                release_datetime=current_release,
                refunding_year=year,
                refunding_quarter=quarter,
            )
        )
    deduplicated = {link.url: link for link in links}
    return QraIndex(list(deduplicated.values()), sorted(set(next_release_dates)))
