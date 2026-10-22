"""Build the self-contained v5 HTML from Treasury's tentative auction XML.

Use --fixture only for reproducible offline builds. The default discovers and
downloads the current XML from Treasury before replacing the v5 artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from lxml import html as lxml_html

from ust_pipeline.http_client import TreasuryHttpClient
from ust_pipeline.qra.parsers import parse_auction_xml


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "UST_AUCTION_ui-baseline-v4.html"
OUTPUT = ROOT / "UST_AUCTION_ui-baseline-v5.html"
MERGER = ROOT / "scripts" / "tentative_schedule_v1.js"
FIXTURES = ROOT / "tests_pipeline" / "fixtures"
SOURCE_PAGE = "https://home.treasury.gov/policy-issues/financing-the-government/treasury-marketable-and-non-marketable-securities"


def replace_once(text: str, before: str, after: str) -> str:
    count = text.count(before)
    if count != 1:
        raise ValueError(f"Expected one v4 anchor, found {count}: {before[:90]!r}")
    return text.replace(before, after, 1)


def source_bytes(fixture: bool) -> tuple[bytes, str, str]:
    if fixture:
        entry = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["files"]["auction_schedule_2026q3.xml"]
        content = (FIXTURES / "auction_schedule_2026q3.xml").read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Fixture hash differs from the official-source manifest")
        return content, entry["url"], entry["captured_on_utc"]

    with TreasuryHttpClient(user_agent="UST-Auction/1.0", allowed_hosts={"home.treasury.gov"}) as client:
        page = client.get(SOURCE_PAGE)
        links = lxml_html.fromstring(page.content).xpath("//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'xml format tentative auction schedule')]/@href")
        if len(links) != 1:
            raise ValueError(f"Expected one official tentative-auction XML link; found {len(links)}")
        url = urljoin(SOURCE_PAGE, links[0])
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "home.treasury.gov" or not parsed.path.lower().endswith(".xml"):
            raise ValueError(f"Unexpected tentative-auction source: {url}")
        response = client.get(url)
    return response.content, url, datetime.now(timezone.utc).date().isoformat()


def snapshot_from_xml(content: bytes, url: str, captured_at: str) -> dict:
    parsed = parse_auction_xml(content)
    if parsed.status != "PARSED" or not parsed.records:
        raise ValueError("Treasury tentative-auction XML was not parsed completely")
    first = parsed.records[0]
    if not first["calendar_end_date"] or not first["calendar_name"]:
        raise ValueError("Treasury calendar is missing its name or end date")
    rows = []
    for row in parsed.records:
        if not row["auction_date"] or not row["security_type"] or not row["security_term"]:
            raise ValueError("Treasury calendar contains an unidentified auction")
        if row["announcement_date"] and row["announcement_date"] > row["auction_date"]:
            raise ValueError("Treasury calendar announcement follows its auction")
        rows.append({
            "auctionDate": row["auction_date"].isoformat(),
            "announcementDate": row["announcement_date"].isoformat() if row["announcement_date"] else None,
            "settlementDate": row["settlement_date"].isoformat() if row["settlement_date"] else None,
            "type": row["security_type"],
            "term": row["security_term"],
            "tips": row["tips"],
            "floating_rate": row["floating_rate"],
            "reopening": row["reopening"],
        })
    return {
        "version": 1,
        "sourceUrl": url,
        "sourceSha256": hashlib.sha256(content).hexdigest(),
        "capturedAt": captured_at,
        "calendarName": first["calendar_name"],
        "calendarEnd": first["calendar_end_date"].isoformat(),
        "rows": rows,
    }


def build_html(snapshot: dict) -> str:
    html = BASELINE.read_text(encoding="utf-8")
    data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    merger = MERGER.read_text(encoding="utf-8")
    insertion = (f'<script type="application/json" id="ust-tentative-schedule-v1">{data}</script>\n'
                 f'<script id="ust-tentative-merger-v1">{merger}</script>\n'
                 '<style id="ust-v5-tentative-styles">\n'
                 '.tentative-badge{display:inline-block;margin-left:5px;padding:1px 4px;border:1px solid #ac84c8;border-radius:3px;color:#e5c6ff;font-size:9px;white-space:nowrap}\n'
                 '.auction-month-calendar{--ust-tentative-color:#76529b}\n'
                 ':root .auction-month-calendar .auction-calendar-event.is-tentative{border-color:#ad83c8;background:var(--ust-tentative-color);color:#fff}\n'
                 '.auction-calendar-legend i.tentative{background:var(--ust-tentative-color)}\n'
                 '.auction-calendar-source{font-size:9px;line-height:1.5;color:var(--muted)}\n'
                 '.auction-calendar-source a{color:#a8cfff;text-decoration:underline}\n'
                 '</style>\n')
    html = replace_once(html, '<script id="standalone-live-data-script">', insertion + '<script id="standalone-live-data-script">')

    html = replace_once(html, 'term: row.original_security_term || row.security_term || "",',
                        'term: type === "Bill" ? row.security_term || row.original_security_term || "" : row.original_security_term || row.security_term || "",')

    official = '''const upcoming = normalized
      .filter((row) => row.auctionDate >= todayText && row.auctionDate <= upcomingTo && row.bidToCover === null)
      .sort((a, b) => a.auctionDate.localeCompare(b.auctionDate) || a.cusip.localeCompare(b.cusip));'''
    merged = '''const officialUpcoming = normalized
      .filter((row) => row.auctionDate >= todayText && row.auctionDate <= upcomingTo && row.bidToCover === null);
    const upcoming = window.__UST_MERGE_TENTATIVE__(rows, officialUpcoming, todayText, upcomingTo);'''
    html = replace_once(html, official, merged)
    html = replace_once(html, 'return { results: results.length, upcoming: upcoming.length };',
                        'return { results: results.length, upcoming: officialUpcoming.length, tentative: upcoming.length - officialUpcoming.length };')
    old_count = '결과 ${counts.results}건, 예정 ${counts.upcoming}건.'
    if html.count(old_count) != 2:
        raise ValueError("Expected two live/cache status messages in v4")
    html = html.replace(old_count, '결과 ${counts.results}건, 공고 ${counts.upcoming}건, 잠정 ${counts.tentative}건.')
    html = replace_once(html, 'upcoming: [],\n        results: [],\n        source: "unavailable",',
                        'upcoming: window.__UST_MERGE_TENTATIVE__([], [], todayText, upcomingTo),\n        results: [],\n        source: "unavailable",')

    html = replace_once(html, 'const state = { data: null, zone: null, year: null, month: null, selectedKey: "", excludeBills: true };',
                        'const state = { data: null, zone: null, year: null, month: null, selectedKey: "", excludeBills: false };')
    html = replace_once(html, '.map((auction) => ({ auction, status: "upcoming" }));',
                        '.map((auction) => ({ auction, status: auction.tentative ? "tentative" : "upcoming" }));')
    html = replace_once(html, '''const latest = events.at(-1)?.display.date.slice(0, 7);
        const current = formatParts(new Date(), zone);
        [state.year, state.month] = latest
          ? latest.split("-").map(Number)
          : [Number(current.year), Number(current.month)];''',
                        '''const current = formatParts(new Date(), zone);
        [state.year, state.month] = [Number(current.year), Number(current.month)];''')
    html = replace_once(html, 'const upcomingCount = datedEvents.length - resultCount;',
                        'const upcomingCount = datedEvents.filter((event) => event.status === "upcoming").length;\n      const tentativeCount = datedEvents.filter((event) => event.status === "tentative").length;')
    html = replace_once(html, '· 예정 ${upcomingCount}건`;', '· 공고 ${upcomingCount}건 · 잠정 ${tentativeCount}건`;')
    html = replace_once(html, 'event.status === "upcoming" ? " is-upcoming" : ""',
                        'event.status === "upcoming" ? " is-upcoming" : event.status === "tentative" ? " is-tentative" : ""')
    html = replace_once(html, 'event.status === "result" ? "입찰 결과" : "예정 입찰"',
                        'event.status === "result" ? "입찰 결과" : event.status === "tentative" ? event.auction.tentativeUnconfirmed ? "잠정 · 공고 확인 필요" : "잠정 일정 · 공식 공고 전" : "공고된 예정 입찰"')
    html = replace_once(html, '''          row = [...rows].find((candidate) => {
            const cells = candidate.querySelectorAll("td");
            return cells.length > 1 && cells[1].textContent.includes(visibleLabel) && candidate.querySelector("button.row-select")?.getAttribute("aria-label")?.includes(event.auction.cusip || event.auction.auctionDate);
          });
          if (!row) row = [...rows].find((candidate) => candidate.querySelectorAll("td")[1]?.textContent.includes(visibleLabel));''',
                        '''          const key = `${event.auction.cusip}-${event.auction.auctionDate}`;
          row = [...rows].find((candidate) =>
            candidate.querySelector("button.row-select")?.getAttribute("data-auction-key") === key);''')
    html = replace_once(html, '        const visibleLabel = window.__UST_TRANSLATE__ && document.documentElement.lang === "en" ? window.__UST_TRANSLATE__(label) : label;\n', '')
    html = replace_once(html, 'event.status === "result" ? "결과" : "예정"}을 선택했습니다.',
                        'event.status === "result" ? "결과" : event.status === "tentative" ? "잠정" : "예정"}을 선택했습니다.')
    html = replace_once(html, 'scheduled.innerHTML = \'<i class="upcoming"></i>입찰 예정\';\n      legend.append(completed, scheduled);',
                        'scheduled.innerHTML = \'<i class="upcoming"></i>공고된 예정\';\n      const tentativeLegend = document.createElement("span");\n      tentativeLegend.innerHTML = \'<i class="tentative"></i>잠정 일정\';\n      legend.append(completed, scheduled, tentativeLegend);')
    html = replace_once(html, 'calendar.append(head, meta, weekdayRow, grid, legend, message);',
                        '''const provenance = document.createElement("p");
      provenance.className = "auction-calendar-source";
      const info = window.__UST_TENTATIVE_INFO__;
      if (info) {
        const link = document.createElement("a");
        link.href = info.sourceUrl;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = "재무부 잠정 일정 원문";
        provenance.append(link, document.createTextNode(` · 수집 ${info.capturedAt} UTC · 잠정 일정은 공고 전 변경될 수 있습니다.`));
      }
      calendar.append(head, meta, weekdayRow, grid, legend, provenance, message);''')

    schedule_start = html.index('q.map(i=>{let b=G(i,n)')
    schedule_end = html.index('!q.length', schedule_start)
    schedule = replace_once(html[schedule_start:schedule_end],
                            'e("button",{className:"row-select","aria-label":',
                            'e("button",{className:"row-select","data-auction-key":F(i),"aria-label":')
    schedule = replace_once(schedule,
                            'a("td",{children:[D(i)," ",i.reopening&&e("span",{className:"reopen-badge"',
                            'a("td",{children:[D(i)," ",i.tentative&&e("span",{className:"tentative-badge",children:i.tentativeUnconfirmed?"\\uACF5\\uACE0 \\uD655\\uC778 \\uD544\\uC694":"\\uC7A0\\uC815"}),i.reopening&&e("span",{className:"reopen-badge"')
    html = html[:schedule_start] + schedule + html[schedule_end:]
    html = replace_once(html, 'className:"released",children:$==="results"?"\\uACB0\\uACFC":"\\uC608\\uC815"',
                        'className:"released",children:$==="results"?"\\uACB0\\uACFC":C?.tentative?"\\uC7A0\\uC815":"\\uC608\\uC815"')
    note_start = html.index('a("p",{className:"schedule-note",children:[', html.index('function ve({upcoming:'))
    note_end = html.index(']}),e("div",{className:"table-wrap"', note_start)
    note = 'a("p",{className:"schedule-note",children:["\\uAE30\\uC900 \\uC2DC\\uAC01: ",Ee.full," \\xB7 ","\\uACF5\\uACE0 \\uC77C\\uC815\\uACFC \\uC7AC\\uBB34\\uBD80 \\uC7A0\\uC815 \\uC77C\\uC815\\uC744 \\uD568\\uAED8 \\uD45C\\uC2DC\\uD569\\uB2C8\\uB2E4. \\uC7A0\\uC815 \\uC77C\\uC815\\uC740 \\uACF5\\uC2DD \\uACF5\\uACE0 \\uC804\\uAE4C\\uC9C0 \\uBCC0\\uACBD\\uB420 \\uC218 \\uC788\\uC2B5\\uB2C8\\uB2E4."'
    html = html[:note_start] + note + html[note_end:]
    html = replace_once(html, "fonts, including any derivative works, can be bundled, embedded, \n",
                        "fonts, including any derivative works, can be bundled, embedded,\n")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="build from the verified 2026 Q3 XML fixture without a network request")
    args = parser.parse_args()
    content, url, captured_at = source_bytes(args.fixture)
    snapshot = snapshot_from_xml(content, url, captured_at)
    html = build_html(snapshot)
    OUTPUT.write_text(html, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "source": url, "capturedAt": captured_at,
                      "rows": len(snapshot["rows"]), "sha256": snapshot["sourceSha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
