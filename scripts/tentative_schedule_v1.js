(() => {
  "use strict";

  const element = document.getElementById("ust-tentative-schedule-v1");
  const snapshot = JSON.parse(element?.textContent || "null");
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  const termKey = (value) => String(value || "").trim().toUpperCase()
    .replace(/\bYEARS?\b/g, "YEAR")
    .replace(/\bWEEKS?\b/g, "WEEK")
    .replace(/\bMONTHS?\b/g, "MONTH")
    .replace(/[\s-]/g, "");
  const securityType = (row) => {
    if (String(row.tips ?? row.inflation_index_security ?? "").toUpperCase() === "Y"
      || String(row.inflation_index_security ?? "").toLowerCase() === "yes") return "TIPS";
    if (String(row.floating_rate ?? "").toUpperCase() === "Y"
      || String(row.floating_rate ?? "").toLowerCase() === "yes") return "FRN";
    const type = String(row.security_type || row.type || "").toUpperCase();
    return { BILL: "Bill", NOTE: "Note", BOND: "Bond" }[type] || type;
  };
  const identity = (date, type, term) => `${date}|${type}|${termKey(term)}`;
  const officialIdentity = (row) => {
    const type = securityType(row);
    // Reopened bills can have a different original term (for example, 4-Week vs 17-Week).
    const term = type === "Bill"
      ? row.security_term || row.original_security_term
      : row.original_security_term || row.security_term;
    return identity(row.auction_date, type, term);
  };
  const treasuryDirectRow = (row) => {
    const pdf = String(row.treasuryOfferingAnnouncementPressReleaseFileName || "");
    const auctionDate = String(row.competitiveAuctionCloseDate || "").slice(0, 10);
    const announcementDate = String(row.announcementDate || "").slice(0, 10);
    if (!/^A_\d{8}_\d+\.pdf$/.test(pdf) || !datePattern.test(auctionDate)
      || !datePattern.test(announcementDate) || announcementDate > auctionDate
      || !row.cusip || !row.securityTerm
      || !(Number(row.offeringAmount) > 0)) return null;
    return {
      cusip: row.cusip,
      auction_date: auctionDate,
      announcemt_date: announcementDate,
      security_type: row.securityType || "Bill",
      security_term: row.securityTerm,
      original_security_term: row.originalSecurityTerm || row.securityTerm,
      inflation_index_security: row.type === "TIPS" || row.inflationProtected === "Yes" ? "Yes" : "No",
      floating_rate: row.type === "FRN" || row.floatingRate === "Yes" ? "Yes" : "No",
      cash_management_bill_cmb: row.type === "CMB" || row.cashManagementBill === "Yes" ? "Yes" : "No",
      offering_amt: row.offeringAmount,
      closing_time_comp: row.competitiveAuctionCloseTime || "",
      issue_date: String(row.issueDate || "").slice(0, 10),
      maturity_date: String(row.maturityDate || "").slice(0, 10),
      reopening: row.reopening || "No",
      bid_to_cover_ratio: null,
    };
  };
  const embeddedAnnouncements = Array.isArray(snapshot?.announcedRows) ? snapshot.announcedRows : [];

  const treasuryDirectResult = (row) => {
    const auctionDate = String(row.competitiveAuctionCloseDate || row.auctionDate || "").slice(0, 10);
    const issueDate = String(row.issueDate || "").slice(0, 10);
    const bidToCover = Number(row.bidToCoverRatio);
    const accepted = Number(row.grandTotalParAwarded ?? row.totalAccepted);
    if (!datePattern.test(auctionDate) || !datePattern.test(issueDate) || !row.cusip
      || !row.securityTerm || !Number.isFinite(bidToCover)
      || bidToCover <= 0 || !Number.isFinite(accepted) || accepted <= 0) return null;
    return {
      cusip: row.cusip,
      auction_date: auctionDate,
      announcemt_date: String(row.announcementDate || "").slice(0, 10),
      security_type: row.securityType || "Bill",
      security_term: row.securityTerm || "",
      original_security_term: row.originalSecurityTerm || row.securityTerm || "",
      inflation_index_security: row.type === "TIPS" || row.inflationProtected === "Yes" ? "Yes" : "No",
      floating_rate: row.type === "FRN" || row.floatingRate === "Yes" ? "Yes" : "No",
      cash_management_bill_cmb: row.type === "CMB" || row.cashManagementBill === "Yes" ? "Yes" : "No",
      offering_amt: row.offeringAmount,
      closing_time_comp: row.competitiveAuctionCloseTime || row.closingTimeCompetitive || "",
      issue_date: issueDate,
      maturity_date: String(row.maturityDate || "").slice(0, 10),
      reopening: row.reopening || "No",
      bid_to_cover_ratio: row.bidToCoverRatio,
      high_discnt_rate: row.highRate ?? row.highDiscountRate,
      high_investment_rate: row.investmentRate ?? row.highInvestmentRate,
      high_discnt_margin: row.highDiscountMargin,
      high_yield: row.highYield,
      int_rate: row.interestRate,
      price_per100: row.pricePer100,
      allocation_pctage: row.allottedAtHighYieldPercentage || row.allottedAtHighRatePercentage
        || row.allottedAtHighDiscountMarginPercentage || row.allocationPercentage,
      total_tendered: row.grandTotalParRecognized ?? row.totalTendered,
      total_accepted: row.grandTotalParAwarded ?? row.totalAccepted,
      primary_dealer_accepted: row.primaryDealersCompetitiveParAwarded ?? row.primaryDealerAccepted,
      direct_bidder_accepted: row.directBiddersCompetitiveParAwarded ?? row.directBidderAccepted,
      indirect_bidder_accepted: row.indirectBiddersCompetitiveParAwarded ?? row.indirectBidderAccepted,
    };
  };

  window.__UST_LOAD_OFFICIAL_RESULTS__ = async () => {
    if (!document.createElement || !document.head?.appendChild) return [];
    return new Promise((resolve) => {
      const callback = "__UST_TD_RESULTS_V1__";
      const script = document.createElement("script");
      let settled = false;
      const finish = (rows) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        script.remove();
        window[callback] = () => {};
        resolve(Array.isArray(rows) ? rows.flatMap((row) => treasuryDirectResult(row) || []) : []);
      };
      const timeout = setTimeout(() => finish(null), 6000);
      window[callback] = finish;
      script.src = `https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=jsonp&day=45&callback=${callback}&ts=${Date.now()}`;
      script.onerror = () => finish(null);
      try { document.head.appendChild(script); }
      catch { finish(null); }
    });
  };

  window.__UST_MERGE_RESULTS__ = (fiscalRows, treasuryDirectResults) => {
    const results = new Map(treasuryDirectResults.map((row) => [`${row.cusip}|${row.auction_date}|${row.issue_date}`, row]));
    const merged = fiscalRows.map((row) => {
      const key = `${row.cusip}|${row.auction_date}|${row.issue_date || ""}`;
      const official = results.get(key);
      results.delete(key);
      return official && !(Number(row.bid_to_cover_ratio) > 0) ? { ...row, ...official } : row;
    });
    return [...merged, ...results.values()];
  };

  window.__UST_LOAD_OFFICIAL_ANNOUNCEMENTS__ = async () => {
    if (!document.createElement || !document.head?.appendChild) return embeddedAnnouncements;
    const live = await new Promise((resolve) => {
      const callback = "__UST_TD_UPCOMING_V1__";
      const script = document.createElement("script");
      let settled = false;
      const finish = (rows) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        script.remove();
        window[callback] = () => {};
        resolve(rows);
      };
      const timeout = setTimeout(() => finish(null), 6000);
      window[callback] = (rows) => finish(Array.isArray(rows) ? rows : null);
      script.src = `https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=jsonp&callback=${callback}&ts=${Date.now()}`;
      script.onerror = () => finish(null);
      try { document.head.appendChild(script); }
      catch { finish(null); }
    });
    return live === null ? embeddedAnnouncements : live;
  };

  window.__UST_AUGMENT_OFFICIAL__ = (fiscalRows, treasuryDirectRows, today, until) => {
    const known = new Set(fiscalRows.map(officialIdentity));
    const supplements = (treasuryDirectRows || []).flatMap((row) => {
      const official = treasuryDirectRow(row);
      if (!official || official.auction_date < today || official.auction_date > until) return [];
      const key = officialIdentity(official);
      if (known.has(key)) return [];
      known.add(key);
      return [official];
    });
    return [...fiscalRows, ...supplements];
  };

  window.__UST_TENTATIVE_INFO__ = snapshot && {
    sourceUrl: snapshot.sourceUrl,
    capturedAt: snapshot.capturedAt,
    calendarName: snapshot.calendarName,
    calendarEnd: snapshot.calendarEnd,
    announcementSourceUrl: snapshot.announcementSourceUrl,
    announcementCapturedAt: snapshot.announcementCapturedAt,
  };
  window.__UST_MERGE_TENTATIVE__ = (officialRows, officialUpcoming, today, until) => {
    if (!snapshot || !Array.isArray(snapshot.rows)) return officialUpcoming;
    const officialKeys = new Set(officialRows.map(officialIdentity));
    const tentative = snapshot.rows.flatMap((row) => {
      if (!datePattern.test(row.auctionDate)
        || row.auctionDate < today || row.auctionDate > until
        || row.auctionDate > snapshot.calendarEnd) return [];
      const type = securityType(row);
      const key = identity(row.auctionDate, type, row.term);
      if (officialKeys.has(key)) return [];
      return [{
        cusip: `tentative:${key}`,
        auctionDate: row.auctionDate,
        announcementDate: row.announcementDate,
        issueDate: row.settlementDate || "",
        type,
        term: row.term,
        securityTerm: row.term,
        reopening: row.reopening === "Y",
        closingTimeCompetitive: "",
        offeringAmount: null,
        bidToCover: null,
        tentative: true,
        tentativeUnconfirmed: !!row.announcementDate && row.announcementDate < today,
      }];
    });
    return [...officialUpcoming, ...tentative]
      .sort((a, b) => a.auctionDate.localeCompare(b.auctionDate)
        || a.type.localeCompare(b.type) || termKey(a.term).localeCompare(termKey(b.term)));
  };
})();
