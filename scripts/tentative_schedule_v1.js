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

  window.__UST_TENTATIVE_INFO__ = snapshot && {
    sourceUrl: snapshot.sourceUrl,
    capturedAt: snapshot.capturedAt,
    calendarName: snapshot.calendarName,
    calendarEnd: snapshot.calendarEnd,
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
