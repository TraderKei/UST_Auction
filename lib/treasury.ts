export type TreasuryAuction = {
  cusip: string;
  auctionDate: string;
  announcementDate: string;
  issueDate: string;
  maturityDate: string;
  type: string;
  term: string;
  securityTerm: string;
  offeringAmount: number;
  closingTimeCompetitive: string;
  reopening: boolean;
  cmb: boolean;
  bidToCover: number | null;
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

type RawTreasuryAuction = Record<string, string>;

const n = (value?: string) => value && Number.isFinite(Number(value)) ? Number(value) : null;

function normalize(row: RawTreasuryAuction): TreasuryAuction {
  const stop = n(row.highYield) ?? n(row.highDiscountRate) ?? n(row.highDiscountMargin);
  const stopLabel = row.highYield ? "High yield" : row.highDiscountMargin ? "Discount margin" : "High rate";
  return {
    cusip: row.cusip,
    auctionDate: row.auctionDate,
    announcementDate: row.announcementDate,
    issueDate: row.issueDate,
    maturityDate: row.maturityDate,
    type: row.type || row.securityType,
    term: row.term || row.securityTerm,
    securityTerm: row.securityTerm,
    offeringAmount: n(row.offeringAmount) ?? 0,
    closingTimeCompetitive: row.closingTimeCompetitive,
    reopening: row.reopening === "Yes",
    cmb: row.cashManagementBillCMB === "Yes",
    bidToCover: n(row.bidToCoverRatio),
    stopRate: stop,
    stopLabel,
    investmentRate: n(row.highInvestmentRate),
    couponRate: n(row.interestRate),
    pricePer100: n(row.pricePer100),
    totalTendered: n(row.totalTendered),
    totalAccepted: n(row.totalAccepted),
    dealerAccepted: n(row.primaryDealerAccepted),
    directAccepted: n(row.directBidderAccepted),
    indirectAccepted: n(row.indirectBidderAccepted),
  };
}

const fallbackUpcoming: TreasuryAuction[] = [
  ["912797SU2","2026-08-24","2026-08-20","2026-08-27","2026-11-27","Bill","13-Week",92e9,"11:30 AM",true],
  ["912797WC7","2026-08-24","2026-08-20","2026-08-27","2027-02-25","Bill","26-Week",79e9,"11:30 AM",false],
  ["912797UJ4","2026-08-25","2026-08-20","2026-08-27","2026-10-08","Bill","6-Week",95e9,"11:30 AM",true],
  ["91282CRH6","2026-08-25","2026-08-20","2026-08-31","2028-08-31","Note","2-Year",69e9,"01:00 PM",false],
  ["91282CRD5","2026-08-26","2026-08-20","2026-08-28","2028-07-31","FRN","2-Year",28e9,"11:30 AM",true],
  ["91282CRK9","2026-08-26","2026-08-20","2026-08-31","2031-08-31","Note","5-Year",70e9,"01:00 PM",false],
  ["91282CRJ2","2026-08-27","2026-08-20","2026-08-31","2033-08-31","Note","7-Year",44e9,"01:00 PM",false],
].map(([cusip,auctionDate,announcementDate,issueDate,maturityDate,type,term,offeringAmount,closingTimeCompetitive,reopening]) => ({
  cusip,auctionDate,announcementDate,issueDate,maturityDate,type,term,securityTerm:term,offeringAmount,closingTimeCompetitive,reopening,cmb:false,
  bidToCover:null,stopRate:null,stopLabel:"High rate",investmentRate:null,couponRate:null,pricePer100:null,totalTendered:null,totalAccepted:null,dealerAccepted:null,directAccepted:null,indirectAccepted:null,
} as TreasuryAuction));

const resultSeed = [
  ["912810US5","2026-08-20","TIPS","30-Year",8e9,2.82,2.973,null,2.375,91.015136,23.588952e9,9.0284534e9,.167e9,1.06813e9,6.7076114e9,true],
  ["912797VD6","2026-08-20","Bill","4-Week",110e9,2.84,3.64,3.701,null,99.716889,319.3290709e9,117.0259859e9,32.060545e9,3.344965e9,67.110826e9,true],
  ["912797VM6","2026-08-20","Bill","8-Week",100e9,3.06,3.655,3.727,null,99.431444,312.0270386e9,106.3874386e9,29.6976e9,2.61e9,64.572081e9,true],
  ["912810UX4","2026-08-19","Bond","20-Year",16e9,2.53,5.204,null,5.125,99.021288,42.4761081e9,18.0569281e9,1.974395e9,3.8868579e9,9.9479391e9,false],
  ["912797WG8","2026-08-19","Bill","17-Week",72e9,3.35,3.75,3.85,null,98.760417,245.4651552e9,76.5997096e9,23.3937e9,4.496357e9,43.2326644e9,false],
  ["912797SA6","2026-08-18","Bill","6-Week",95e9,2.97,3.645,3.711,null,99.57475,289.3626839e9,101.9445423e9,27.3294e9,4.34352e9,60.2078384e9,true],
  ["912797UZ8","2026-08-17","Bill","13-Week",92e9,2.86,3.715,3.802,null,99.060931,269.5519569e9,98.7258639e9,35.21688e9,6.074e9,48.1358881e9,true],
  ["912797TV9","2026-08-17","Bill","26-Week",79e9,2.97,3.78,3.907,null,98.089,240.5495353e9,84.7753723e9,18.9740375e9,8.0723875e9,49.934964e9,true],
  ["912810UW6","2026-08-13","Bond","30-Year",25e9,2.39,5.216,null,5.125,98.627017,66.1245288e9,31.3235338e9,2.866735e9,5.39015e9,16.647723e9,false],
];

const fallbackResults: TreasuryAuction[] = resultSeed.map(([cusip,auctionDate,type,term,offeringAmount,bidToCover,stopRate,investmentRate,couponRate,pricePer100,totalTendered,totalAccepted,dealerAccepted,directAccepted,indirectAccepted,reopening]) => ({
  cusip,auctionDate,announcementDate:"",issueDate:"",maturityDate:"",type,term,securityTerm:term,offeringAmount,closingTimeCompetitive:"",reopening,cmb:false,bidToCover,stopRate,
  stopLabel:type === "Bill" ? "High rate" : "High yield",investmentRate,couponRate,pricePer100,totalTendered,totalAccepted,dealerAccepted,directAccepted,indirectAccepted,
} as TreasuryAuction));

async function fetchRows(url: string) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`TreasuryDirect ${response.status}`);
  return await response.json() as RawTreasuryAuction[];
}

export async function getTreasuryData() {
  try {
    const [announced, auctioned] = await Promise.all([
      fetchRows("https://www.treasurydirect.gov/TA_WS/securities/announced?format=json"),
      fetchRows("https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&day=45"),
    ]);
    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);
    const upcoming = announced.map(normalize).filter((row) => new Date(row.auctionDate) >= today).sort((a,b) => a.auctionDate.localeCompare(b.auctionDate)).slice(0, 24);
    const results = auctioned.map(normalize).filter((row) => row.bidToCover !== null).sort((a,b) => b.auctionDate.localeCompare(a.auctionDate)).slice(0, 36);
    if (!upcoming.length || !results.length) throw new Error("No current records");
    return { upcoming, results, source: "live" as const, updatedAt: new Date().toISOString() };
  } catch {
    return { upcoming: fallbackUpcoming, results: fallbackResults, source: "snapshot" as const, updatedAt: "2026-08-21T06:30:00.000Z" };
  }
}
