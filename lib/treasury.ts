export type TreasuryAuction = {
  cusip: string;
  auctionDate: string;
  announcementDate: string;
  issueDate: string;
  maturityDate: string;
  type: string;
  term: string;
  securityTerm: string;
  offeringAmount: number | null;
  closingTimeCompetitive: string;
  reopening: boolean;
  cmb: boolean;
  bidToCover: number | null;
  allottedAtHigh: number | null;
  stopRate: number | null;
  stopLabel: string;
  investmentRate: number | null;
  couponRate: number | null;
  pricePer100: number | null;
  totalTendered: number | null;
  totalAccepted: number | null;
  dealerAccepted: number | null;
  directAccepted: number | null;
  indirectAccepted: number | null;
};

export type TreasuryData = {
  upcoming: TreasuryAuction[];
  results: TreasuryAuction[];
  source: "fiscal-api" | "unavailable";
  updatedAt: string;
  sourceUrl: string;
  sourceRange: string;
  sourceError?: string;
};

type RawTreasuryAuction = Record<string, string | null>;
type FiscalResponse = {
  data?: RawTreasuryAuction[];
  meta?: { "total-count"?: number | string; "total-pages"?: number | string };
};

const FISCAL_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query";
const FIELDS = [
  "record_date", "cusip", "security_type", "security_term", "original_security_term",
  "inflation_index_security", "floating_rate",
  "announcemt_date", "auction_date", "issue_date", "maturity_date", "closing_time_comp",
  "offering_amt", "reopening", "cash_management_bill_cmb", "high_discnt_rate",
  "high_investment_rate", "high_discnt_margin", "high_yield", "int_rate", "price_per100",
  "bid_to_cover_ratio", "allocation_pctage", "total_tendered", "total_accepted",
  "primary_dealer_accepted", "direct_bidder_accepted", "indirect_bidder_accepted",
].join(",");

const n = (value?: string | null) => {
  if (value == null || value.trim() === "" || value.toLowerCase() === "null") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const yes = (value?: string | null) => value?.trim().toLowerCase() === "yes";

export function normalizeFiscalAuction(row: RawTreasuryAuction): TreasuryAuction {
  const type = yes(row.inflation_index_security)
    ? "TIPS"
    : yes(row.floating_rate)
      ? "FRN"
      : row.security_type ?? "Unknown";
  const cmb = yes(row.cash_management_bill_cmb);
  const stop = type === "Bill" || cmb
    ? n(row.high_discnt_rate)
    : type === "FRN"
      ? n(row.high_discnt_margin)
      : n(row.high_yield);
  const stopLabel = type === "Bill" || cmb
    ? "High rate"
    : type === "FRN"
      ? "Discount margin"
      : type === "TIPS"
        ? "High real yield"
        : "High yield";
  return {
    cusip: row.cusip ?? "",
    auctionDate: row.auction_date ?? "",
    announcementDate: row.announcemt_date ?? "",
    issueDate: row.issue_date ?? "",
    maturityDate: row.maturity_date ?? "",
    type,
    term: row.original_security_term || row.security_term || "",
    securityTerm: row.security_term ?? "",
    offeringAmount: n(row.offering_amt),
    closingTimeCompetitive: row.closing_time_comp ?? "",
    reopening: yes(row.reopening),
    cmb,
    bidToCover: n(row.bid_to_cover_ratio),
    allottedAtHigh: n(row.allocation_pctage),
    stopRate: stop,
    stopLabel,
    investmentRate: n(row.high_investment_rate),
    couponRate: n(row.int_rate),
    pricePer100: n(row.price_per100),
    totalTendered: n(row.total_tendered),
    totalAccepted: n(row.total_accepted),
    dealerAccepted: n(row.primary_dealer_accepted),
    directAccepted: n(row.direct_bidder_accepted),
    indirectAccepted: n(row.indirect_bidder_accepted),
  };
}

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function addUtcDays(value: Date, days: number) {
  const copy = new Date(value);
  copy.setUTCDate(copy.getUTCDate() + days);
  return copy;
}

async function fetchFiscalRows(from: string, to: string) {
  const url = new URL(FISCAL_API);
  url.searchParams.set("fields", FIELDS);
  url.searchParams.set("filter", `auction_date:gte:${from},auction_date:lte:${to}`);
  url.searchParams.set("sort", "-auction_date,cusip,issue_date");
  url.searchParams.set("format", "json");
  url.searchParams.set("page[size]", "1000");
  const rows: RawTreasuryAuction[] = [];
  let totalPages = 1;
  let totalCount = 0;
  for (let page = 1; page <= totalPages; page += 1) {
    url.searchParams.set("page[number]", String(page));
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error(`Fiscal Data API HTTP ${response.status} on page ${page}`);
    const payload = await response.json() as FiscalResponse;
    rows.push(...(payload.data ?? []));
    if (page === 1) {
      totalPages = Number(payload.meta?.["total-pages"] ?? 1);
      totalCount = Number(payload.meta?.["total-count"] ?? rows.length);
      if (!Number.isInteger(totalPages) || totalPages < 1 || !Number.isInteger(totalCount) || totalCount < 0) {
        throw new Error("Fiscal Data API returned invalid pagination metadata");
      }
    }
  }
  if (rows.length !== totalCount) {
    throw new Error(`Fiscal Data API pagination incomplete (${rows.length}/${totalCount}, ${totalPages} pages)`);
  }
  return rows;
}

export async function getTreasuryData(): Promise<TreasuryData> {
  const retrievedAt = new Date();
  const today = new Date(retrievedAt);
  today.setUTCHours(0, 0, 0, 0);
  const from = isoDate(addUtcDays(today, -730));
  const to = isoDate(addUtcDays(today, 90));
  const sourceRange = `${from}~${to}`;
  try {
    const rows = (await fetchFiscalRows(from, to))
      .map(normalizeFiscalAuction)
      .filter((row) => row.cusip && row.auctionDate);
    const todayText = isoDate(today);
    const upcoming = rows
      .filter((row) => row.auctionDate >= todayText && row.bidToCover === null)
      .sort((a, b) => a.auctionDate.localeCompare(b.auctionDate) || a.cusip.localeCompare(b.cusip));
    const results = rows
      .filter((row) => row.bidToCover !== null)
      .sort((a, b) => b.auctionDate.localeCompare(a.auctionDate) || a.cusip.localeCompare(b.cusip));
    if (!results.length) throw new Error("Fiscal Data API returned no auction results");
    return { upcoming, results, source: "fiscal-api", updatedAt: retrievedAt.toISOString(), sourceUrl: FISCAL_API, sourceRange };
  } catch (error) {
    return {
      upcoming: [],
      results: [],
      source: "unavailable",
      updatedAt: retrievedAt.toISOString(),
      sourceUrl: FISCAL_API,
      sourceRange,
      sourceError: error instanceof Error ? error.message : "Unknown data retrieval failure",
    };
  }
}
