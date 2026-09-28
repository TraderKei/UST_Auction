(() => {
  "use strict";

  const API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query";
  const FIELDS = [
    "record_date", "cusip", "security_type", "security_term", "original_security_term",
    "inflation_index_security", "floating_rate", "announcemt_date", "auction_date",
    "issue_date", "maturity_date", "closing_time_comp", "offering_amt", "reopening",
    "cash_management_bill_cmb", "high_discnt_rate", "high_investment_rate",
    "high_discnt_margin", "high_yield", "int_rate", "price_per100", "bid_to_cover_ratio",
    "allocation_pctage", "total_tendered", "total_accepted", "primary_dealer_accepted",
    "direct_bidder_accepted", "indirect_bidder_accepted",
  ].join(",");

  const number = (value) => {
    if (value == null || String(value).trim() === "" || String(value).toLowerCase() === "null") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const yes = (value) => String(value ?? "").trim().toLowerCase() === "yes";
  const isoDate = (value) => value.toISOString().slice(0, 10);
  const addUtcDays = (value, days) => {
    const copy = new Date(value);
    copy.setUTCDate(copy.getUTCDate() + days);
    return copy;
  };

  function normalize(row) {
    const type = yes(row.inflation_index_security)
      ? "TIPS"
      : yes(row.floating_rate)
        ? "FRN"
        : row.security_type || "Unknown";
    const cmb = yes(row.cash_management_bill_cmb);
    const stopRate = type === "Bill" || cmb
      ? number(row.high_discnt_rate)
      : type === "FRN"
        ? number(row.high_discnt_margin)
        : number(row.high_yield);
    const stopLabel = type === "Bill" || cmb
      ? "High rate"
      : type === "FRN"
        ? "Discount margin"
        : type === "TIPS"
          ? "High real yield"
          : "High yield";

    return {
      cusip: row.cusip || "",
      auctionDate: row.auction_date || "",
      announcementDate: row.announcemt_date || "",
      issueDate: row.issue_date || "",
      maturityDate: row.maturity_date || "",
      type,
      term: row.original_security_term || row.security_term || "",
      securityTerm: row.security_term || "",
      offeringAmount: number(row.offering_amt),
      closingTimeCompetitive: row.closing_time_comp || "",
      reopening: yes(row.reopening),
      cmb,
      bidToCover: number(row.bid_to_cover_ratio),
      allottedAtHigh: number(row.allocation_pctage),
      stopRate,
      stopLabel,
      investmentRate: number(row.high_investment_rate),
      couponRate: number(row.int_rate),
      pricePer100: number(row.price_per100),
      totalTendered: number(row.total_tendered),
      totalAccepted: number(row.total_accepted),
      dealerAccepted: number(row.primary_dealer_accepted),
      directAccepted: number(row.direct_bidder_accepted),
      indirectAccepted: number(row.indirect_bidder_accepted),
    };
  }

  async function fetchRows(from, to) {
    const rows = [];
    let totalPages = 1;
    let totalCount = 0;

    for (let page = 1; page <= totalPages; page += 1) {
      const url = new URL(API);
      url.searchParams.set("fields", FIELDS);
      url.searchParams.set("filter", `auction_date:gte:${from},auction_date:lte:${to}`);
      url.searchParams.set("sort", "-auction_date,cusip,issue_date");
      url.searchParams.set("format", "json");
      url.searchParams.set("page[number]", String(page));
      url.searchParams.set("page[size]", "1000");

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      let response;
      try {
        response = await fetch(url, {
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      if (!response.ok) throw new Error(`Fiscal Data API HTTP ${response.status} (page ${page})`);

      const payload = await response.json();
      rows.push(...(payload.data || []));
      if (page === 1) {
        totalPages = Number(payload.meta?.["total-pages"] ?? 1);
        totalCount = Number(payload.meta?.["total-count"] ?? rows.length);
        if (!Number.isInteger(totalPages) || totalPages < 1 || !Number.isInteger(totalCount) || totalCount < 0) {
          throw new Error("Fiscal Data API returned invalid pagination metadata");
        }
      }
    }

    if (rows.length !== totalCount) {
      throw new Error(`Fiscal Data API pagination incomplete (${rows.length}/${totalCount})`);
    }
    return rows;
  }

  function keepStatusVisible(kind, badgeText, message) {
    const apply = () => {
      const badge = document.querySelector(".source-badge");
      const status = document.querySelector(".data-status");
      const sourceLink = document.querySelector(".terminal-shell > footer a");
      if (badge && (badge.textContent !== badgeText || !badge.classList.contains(kind))) {
        badge.className = `source-badge ${kind}`;
        badge.textContent = badgeText;
      }
      if (status) {
        status.className = `data-status ${kind}`;
        const messageNode = Array.from(status.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
        if (messageNode && messageNode.nodeValue !== message) messageNode.nodeValue = message;
      }
      if (kind === "live" && sourceLink) {
        if (sourceLink.href !== API) sourceLink.href = API;
        if (sourceLink.textContent !== "미국 재무부 · Fiscal Data") sourceLink.textContent = "미국 재무부 · Fiscal Data";
      }
    };
    apply();
    new MutationObserver(apply).observe(document.getElementById("root"), {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  async function init() {
    if (typeof window.__UST_RENDER_AUCTIONS__ !== "function") {
      throw new Error("기준 화면의 데이터 연결 지점을 찾지 못했습니다.");
    }

    const retrievedAt = new Date();
    const today = new Date(retrievedAt);
    today.setUTCHours(0, 0, 0, 0);
    const from = isoDate(addUtcDays(today, -730));
    const to = isoDate(addUtcDays(today, 90));

    try {
      const rows = (await fetchRows(from, to))
        .map(normalize)
        .filter((row) => row.cusip && row.auctionDate);
      const todayText = isoDate(today);
      const results = rows
        .filter((row) => row.bidToCover !== null)
        .sort((a, b) => b.auctionDate.localeCompare(a.auctionDate) || a.cusip.localeCompare(b.cusip));
      const upcoming = rows
        .filter((row) => row.auctionDate >= todayText && row.bidToCover === null)
        .sort((a, b) => a.auctionDate.localeCompare(b.auctionDate) || a.cusip.localeCompare(b.cusip));
      if (!results.length) throw new Error("Fiscal Data API returned no auction results");

      window.__UST_RENDER_AUCTIONS__({
        upcoming,
        results,
        source: "live",
        updatedAt: retrievedAt.toISOString(),
      });
      const message = `미국 재무부 Fiscal Data 공식 API 자료입니다. 조회 범위 ${from}~${to}, 결과 ${results.length}건, 예정 ${upcoming.length}건.`;
      requestAnimationFrame(() => keepStatusVisible("live", "공식 API 수신", message));
    } catch (error) {
      window.__UST_RENDER_AUCTIONS__({
        upcoming: [],
        results: [],
        source: "unavailable",
        updatedAt: retrievedAt.toISOString(),
      });
      const reason = error instanceof Error ? error.message : String(error);
      requestAnimationFrame(() => keepStatusVisible(
        "unavailable",
        "수신 실패",
        `공식 Fiscal Data API 수신에 실패했습니다. 표본값으로 대체하지 않습니다. 원인: ${reason}`,
      ));
    }
  }

  const start = () => requestAnimationFrame(() => requestAnimationFrame(() => init().catch((error) => {
    keepStatusVisible(
      "unavailable",
      "수신 실패",
      `실데이터 연결 초기화에 실패했습니다. ${error instanceof Error ? error.message : error}`,
    );
  })));
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
})();
