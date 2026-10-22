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
