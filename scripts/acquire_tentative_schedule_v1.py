"""Build the self-contained v5 HTML from Treasury's tentative auction XML.

Use --fixture only for reproducible offline builds. The default discovers and
downloads the current XML from Treasury before replacing the v5 artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
RESULTS_EXPORTER = ROOT / "scripts" / "results_excel_v1.js"
FIXTURES = ROOT / "tests_pipeline" / "fixtures"
SOURCE_PAGE = "https://home.treasury.gov/policy-issues/financing-the-government/treasury-marketable-and-non-marketable-securities"
ANNOUNCEMENTS_API = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"
ANNOUNCEMENT_FIELDS = (
    "cusip", "securityType", "type", "securityTerm", "originalSecurityTerm",
    "announcementDate", "competitiveAuctionCloseDate", "competitiveAuctionCloseTime",
    "issueDate", "maturityDate", "offeringAmount", "reopening", "cashManagementBill",
    "treasuryOfferingAnnouncementPressReleaseFileName", "floatingRate", "inflationProtected",
)


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


def announced_rows_from_treasury_direct(rows: list[dict]) -> list[dict]:
    announced = []
    for row in rows:
        pdf = str(row.get("treasuryOfferingAnnouncementPressReleaseFileName") or "")
        if not pdf:
            continue  # TreasuryDirect also returns unannounced placeholders.
        if not re.fullmatch(r"A_\d{8}_\d+\.pdf", pdf):
            raise ValueError(f"Unexpected TreasuryDirect announcement file: {pdf}")
        auction_date = str(row.get("competitiveAuctionCloseDate") or "")[:10]
        announcement_date = str(row.get("announcementDate") or "")[:10]
        if not all((row.get("cusip"), row.get("securityTerm"), auction_date, announcement_date)):
            raise ValueError("TreasuryDirect announced auction lacks an identity or date")
        if datetime.fromisoformat(announcement_date).date() > datetime.fromisoformat(auction_date).date():
            raise ValueError("TreasuryDirect announcement follows its auction")
        if float(row.get("offeringAmount") or 0) <= 0:
            raise ValueError("TreasuryDirect announced auction lacks an offering amount")
        announced.append({field: row.get(field) or "" for field in ANNOUNCEMENT_FIELDS})
    return announced


def fetch_announced_rows() -> list[dict]:
    with TreasuryHttpClient(user_agent="UST-Auction/1.0", allowed_hosts={"www.treasurydirect.gov"}) as client:
        payload = client.get(ANNOUNCEMENTS_API).json()
    if not isinstance(payload, list):
        raise ValueError("TreasuryDirect upcoming auctions did not return a list")
    return announced_rows_from_treasury_direct(payload)


def build_html(snapshot: dict) -> str:
    html = BASELINE.read_text(encoding="utf-8")
    html = replace_once(html, '<title>UST AUCTION · UI Baseline v4</title>',
                        '<title>UST AUCTION · UI Baseline v5</title>')
    data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    merger = MERGER.read_text(encoding="utf-8")
    results_exporter = RESULTS_EXPORTER.read_text(encoding="utf-8")
    html = replace_once(html, '<script id="ust-vue-dashboard-runtime">',
                        f'<script id="ust-results-excel-v1">{results_exporter}</script>\n<script id="ust-vue-dashboard-runtime">')
    insertion = (f'<script type="application/json" id="ust-tentative-schedule-v1">{data}</script>\n'
                 f'<script id="ust-tentative-merger-v1">{merger}</script>\n'
                 '<style id="ust-v5-tentative-styles">\n'
                 ':root{--ust-tentative-color:#3b4650;--ust-tentative-text:#e9eef2;--ust-tentative-border:#788895;--ust-upcoming-swatch:#755b42}\n'
                 'html[data-ust-theme="light"]{--ust-tentative-color:#e3e8ed;--ust-tentative-text:#35424e;--ust-tentative-border:#8b98a4;--ust-upcoming-swatch:#8a6b4a}\n'
                 '.tentative-badge{display:inline-block;margin-left:4px;padding:1px 5px;border:1px solid var(--ust-tentative-border);border-radius:3px;color:var(--ust-tentative-text);font-size:11px;white-space:nowrap}\n'
                 ':root .auction-month-calendar .auction-calendar-event.is-tentative{border-color:var(--ust-tentative-border);background:var(--ust-tentative-color);color:var(--ust-tentative-text)}\n'
                 '.auction-calendar-legend i.tentative{background:var(--ust-tentative-color)}\n'
                 'html[data-ust-theme="light"] .auction-calendar-legend i.tentative{border:1px solid var(--ust-tentative-border)}\n'
                 ':root .latest-panel .released.is-result{background:#245c91;color:#fff;border:1px solid #245c91}\n'
                 ':root .auction-month-calendar .auction-calendar-legend i.upcoming{background:var(--ust-upcoming-swatch)}\n'
                 ':root .latest-panel .released.is-upcoming{background:var(--ust-upcoming-swatch);color:#fff;border:1px solid var(--ust-upcoming-swatch)}\n'
                 ':root .latest-panel .released.is-tentative{background:var(--ust-tentative-color);color:var(--ust-tentative-text);border:1px solid var(--ust-tentative-border)}\n'
                 '.auction-calendar-source{font-size:9px;line-height:1.5;color:var(--muted)}\n'
                 ':root .auction-month-calendar .auction-calendar-source,:root .auction-month-calendar .auction-calendar-message{margin:0}\n'
                 ':root .auction-month-calendar .auction-calendar-message{margin-top:-6px}\n'
                 ':root .date-range-form .results-export{width:30px;height:30px;flex:0 0 30px;display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid var(--ce-border2);border-radius:4px;background:var(--panel);cursor:pointer}\n'
                 ':root .date-range-form .results-export:hover{border-color:#217346;background:var(--ce-hover)}\n'
                 ':root .date-range-form .results-export:focus-visible{outline:2px solid #217346;outline-offset:2px}\n'
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
    html = replace_once(html, '''      const rows = await fetchRows(from, to);
      const counts = renderRows(rows, "live", retrievedAt.toISOString(), range, defaults, initialFilter, todayText, upcomingTo);
      saveCache(from, to, rows, retrievedAt);''',
                        '''      const fiscalRows = await fetchRows(from, to);
      const treasuryDirectRows = await treasuryDirectPromise;
      const rows = window.__UST_AUGMENT_OFFICIAL__(fiscalRows, treasuryDirectRows, todayText, upcomingTo);
      const counts = renderRows(rows, "live", retrievedAt.toISOString(), range, defaults, initialFilter, todayText, upcomingTo);
      saveCache(from, to, fiscalRows, retrievedAt);''')
    html = replace_once(html, '    try {\n      const fiscalRows = await fetchRows(from, to);',
                        '    const treasuryDirectPromise = window.__UST_LOAD_OFFICIAL_ANNOUNCEMENTS__();\n\n    try {\n      const fiscalRows = await fetchRows(from, to);')
    html = replace_once(html, '''    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);''',
                        '''    } catch (error) {
      const treasuryDirectRows = await treasuryDirectPromise;
      const reason = error instanceof Error ? error.message : String(error);''')
    html = replace_once(html, 'renderRows(cached.rows, "snapshot", cached.retrievedAt, range, defaults, initialFilter, todayText, upcomingTo)',
                        'renderRows(window.__UST_AUGMENT_OFFICIAL__(cached.rows, treasuryDirectRows, todayText, upcomingTo), "snapshot", cached.retrievedAt, range, defaults, initialFilter, todayText, upcomingTo)')
    html = replace_once(html, 'renderRows(VERIFIED_RESULT_ROWS, "snapshot", retrievedAt.toISOString(), range, defaults, initialFilter, todayText, upcomingTo)',
                        'renderRows(window.__UST_AUGMENT_OFFICIAL__(VERIFIED_RESULT_ROWS, treasuryDirectRows, todayText, upcomingTo), "snapshot", retrievedAt.toISOString(), range, defaults, initialFilter, todayText, upcomingTo)')
    html = replace_once(html, 'return { results: results.length, upcoming: upcoming.length };',
                        'return { results: results.length, upcoming: officialUpcoming.length, tentative: upcoming.length - officialUpcoming.length };')
    old_count = '결과 ${counts.results}건, 예정 ${counts.upcoming}건.'
    if html.count(old_count) != 2:
        raise ValueError("Expected two live/cache status messages in v4")
    html = html.replace(old_count, '결과 ${counts.results}건, 공고 ${counts.upcoming}건, 잠정 ${counts.tentative}건.')
    html = html.replace('미국 재무부 Fiscal Data 공식 API 자료입니다.', '미국 재무부 Fiscal Data 및 TreasuryDirect 공식 API 자료입니다.')
    html = replace_once(html, 'Data from the U.S. Treasury Fiscal Data official API.',
                        'Data from the U.S. Treasury Fiscal Data and TreasuryDirect official APIs.')
    html = replace_once(html, 'upcoming: [],\n        results: [],\n        source: "unavailable",',
                        'upcoming: window.__UST_MERGE_TENTATIVE__(announced, announced.map(normalize), todayText, upcomingTo),\n        results: [],\n        source: "unavailable",')
    html = replace_once(html, '      window.__UST_RENDER_AUCTIONS__({\n        upcoming: window.__UST_MERGE_TENTATIVE__(announced,',
                        '      const announced = window.__UST_AUGMENT_OFFICIAL__([], treasuryDirectRows, todayText, upcomingTo);\n      window.__UST_RENDER_AUCTIONS__({\n        upcoming: window.__UST_MERGE_TENTATIVE__(announced,')

    html = replace_once(html, 'const state = { data: null, zone: null, year: null, month: null, selectedKey: "", excludeBills: true };',
                        'const state = { data: null, zone: null, year: null, month: null, selectedKey: "", excludeBills: false };')
    html = replace_once(html, 'if (auction.type === "Bill") return `${amount}주 단기채`;',
                        'if (auction.type === "Bill") return `${amount}${String(auction.term || auction.securityTerm).includes("Day") ? "일" : "주"} 단기채`;')
    html = replace_once(html, 'if (auction.type === "Bill") return `${amount}W`;',
                        'if (auction.type === "Bill") return `${amount}${String(auction.term || auction.securityTerm).includes("Day") ? "D" : "W"}`;')
    html = replace_once(html, 'pe=t=>t.replace(/-Year(s)?/gi,"\\uB144").replace(/-Week(s)?/gi,"\\uC8FC").replace(/-Month(s)?/gi,"\\uAC1C\\uC6D4")',
                        'pe=t=>t.replace(/-Year(s)?/gi,"\\uB144").replace(/-Week(s)?/gi,"\\uC8FC").replace(/-Month(s)?/gi,"\\uAC1C\\uC6D4").replace(/-Day(s)?/gi,"\\uC77C")')
    html = replace_once(html,
                        ',a("text",{className:"axis-term",x:s,y:"210",textAnchor:"middle",children:[pe(t.term)," \\xB7 ",r.converted?n:"\\uC6D0\\uBB38 ET"]})',
                        '')
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
      provenance.textContent = "잠정 일정은 공식 공고 전까지 변경될 수 있습니다.";
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
                        'className:`released ${$==="results"?"is-result":C?.tentative?"is-tentative":"is-upcoming"}`,children:$==="results"?"\\uACB0\\uACFC":C?.tentative?"\\uC7A0\\uC815":"\\uC608\\uC815"')
    html = replace_once(html,
                        'className:"date-range-form",onSubmit:rt,noValidate:!0,children:[a("label"',
                        'className:"date-range-form",onSubmit:rt,noValidate:!0,children:[e("button",{type:"button",className:"results-export","aria-label":"최근 입찰 결과 엑셀 다운로드",title:"최근 입찰 결과 엑셀 다운로드",onClick:()=>window.__UST_RESULTS_EXCEL_V1__.download(),dangerouslySetInnerHTML:{__html:window.__UST_RESULTS_EXCEL_V1__.icon}}),a("label"')
    html = replace_once(html,
                        ',e("span",{children:s==="snapshot"?"\\uD45C\\uBCF8 \\uAE30\\uC900 \\uC608\\uC815 \\xB7 \\uCD5C\\uC2E0 \\uC77C\\uC815 \\uBBF8\\uD655\\uC778":"\\uC790\\uB8CC \\uAE30\\uC900 \\uC2DC\\uAC01 \\uC774\\uD6C4 \\uC608\\uC815"})',
                        '')
    note_start = html.index('a("p",{className:"schedule-note",children:[', html.index('function ve({upcoming:'))
    note_end = html.index(']}),e("div",{className:"table-wrap"', note_start)
    note = 'a("p",{className:"schedule-note",children:["\\uC7A0\\uC815 \\uC77C\\uC815\\uC740 \\uACF5\\uC2DD \\uACF5\\uACE0 \\uC804\\uAE4C\\uC9C0 \\uBCC0\\uACBD\\uB420 \\uC218 \\uC788\\uC2B5\\uB2C8\\uB2E4."'
    html = html[:note_start] + note + html[note_end:]
    html = replace_once(html, 'i.rate.toFixed(2)', 'i.rate.toFixed(4)')
    html = replace_once(html, '''    const sourceTime = root.querySelector(".time-strip > span:last-child");
    if (!sourceTime) return;
    let asOf = topRight.querySelector(".ust-asof");
    if (!asOf) {
      asOf = document.createElement("span");
      asOf.className = "ust-asof";
      zoneSwitch.before(asOf);
    }
    const value = sourceTime.textContent.trim();
    if (asOf.textContent !== value) asOf.textContent = value;
''', '')
    html = replace_once(html, "fonts, including any derivative works, can be bundled, embedded, \n",
                        "fonts, including any derivative works, can be bundled, embedded,\n")
    translations = {
        "미국 재무부 Fiscal Data 및 TreasuryDirect 공식 API 자료입니다.": "Data from the U.S. Treasury Fiscal Data and TreasuryDirect official APIs.",
        "조회 범위": "Query range",
        "응찰률": "Bid-to-cover",
        "최근 입찰 결과 엑셀 다운로드": "Download recent auction results as Excel",
        "공식 Fiscal Data API 수신에 실패했습니다.": "Could not fetch the official Fiscal Data API.",
        "공식 API 재조회 실패": "Official API refresh failed",
        "API 재조회 실패": "API refresh failed",
        "수신본을 표시합니다.": "Displaying the saved copy.",
        "공식 발표문으로 검증한": "verified against the official announcement",
        "10년물": "10-year Treasury",
        "건만 표시합니다.": " auction(s) are shown.",
        "다른 입찰의 최신 상태는 확인할 수 없습니다.": "The latest status of other auctions is unavailable.",
        "기준 화면의 데이터 연결 지점을 찾지 못했습니다.": "Could not find the baseline data connection.",
        "실데이터 연결 초기화에 실패했습니다.": "Could not initialize the live data connection.",
        "미국 재무부 · 2026-10-07 입찰 결과": "U.S. Treasury · 2026-10-07 auction result",
        "공고된 예정 입찰": "Announced upcoming auction",
        "공고된 예정": "Announced upcoming",
        "잠정 일정은 공식 공고 전까지 변경될 수 있습니다.": "Tentative dates may change before an official announcement.",
        "잠정 일정 · 공식 공고 전": "Tentative schedule · before official announcement",
        "잠정 · 공고 확인 필요": "Tentative · check announcement",
        "재무부 잠정 일정": "Treasury tentative schedule",
        "공고 전 변경될 수 있습니다.": "Subject to change before announcement.",
        "잠정 일정": "Tentative schedule",
        "공고 확인 필요": "Check announcement",
        "공고": "Announced",
        "잠정": "Tentative",
        "수집": "Collected",
        "입찰": "Auction",
        "을 선택했습니다.": " selected.",
        " 기준 미국 국채 입찰 일정": " U.S. Treasury auction schedule",
        " 기준 ·": " zone ·",
    }
    table_match = re.search(r'(<script type="application/json" id="ust-translation-table">)(.*?)(</script>)', html, re.DOTALL)
    if not table_match:
        raise ValueError("Missing v4 translation table")
    table = json.loads(table_match.group(2))
    table = [entry for entry in table if entry["ko"] not in translations]
    table.extend({"ko": ko, "en": en} for ko, en in translations.items())
    html = html[:table_match.start(2)] + json.dumps(table, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c") + html[table_match.end(2):]
    html = replace_once(html, "document.title = state.language === \"en\" ? \"UST AUCTION · UI Baseline v4\" : \"UST AUCTION · UI 기준 v4\";",
                        "document.title = state.language === \"en\" ? \"UST AUCTION · UI Baseline v5\" : \"UST AUCTION · UI 기준 v5\";")
    html = replace_once(html, ">한국어</button>", ">{{state.language === 'ko' ? '한국어' : 'Korean'}}</button>")
    html = replace_once(html, "result = result.replace(/(\\d+)년/g, '$1Y').replace(/(\\d+)주/g, '$1W').replace(/(\\d+)건/g, '$1 items');",
                        "result = result.replace(/(\\d+)년/g, '$1Y').replace(/(\\d+)주/g, '$1W').replace(/(\\d+)일/g, '$1D').replace(/(\\d+)건/g, '$1 items').replace(/건/g, ' items');")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="build from the verified 2026 Q3 XML fixture without a network request")
    args = parser.parse_args()
    content, url, captured_at = source_bytes(args.fixture)
    snapshot = snapshot_from_xml(content, url, captured_at)
    snapshot["announcementSourceUrl"] = ANNOUNCEMENTS_API
    snapshot["announcementCapturedAt"] = captured_at if not args.fixture else None
    snapshot["announcedRows"] = fetch_announced_rows() if not args.fixture else []
    html = build_html(snapshot)
    OUTPUT.write_text(html, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "source": url, "capturedAt": captured_at,
                      "rows": len(snapshot["rows"]), "sha256": snapshot["sourceSha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
