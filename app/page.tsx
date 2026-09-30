import AuctionDashboard from "./AuctionDashboard";
import { getTreasuryData } from "../lib/treasury";
import { defaultAuctionDateRange, resolveAuctionDateRange } from "../lib/auction-date-range";

type SearchParameters = { from?: string | string[]; to?: string | string[] };

export default async function Home({ searchParams }: { searchParams?: Promise<SearchParameters> }) {
  const today = new Date();
  const defaults = defaultAuctionDateRange(today);
  const resultRange = resolveAuctionDateRange(await searchParams, today);
  const data = await getTreasuryData(resultRange);
  return <AuctionDashboard {...data} resultFrom={resultRange.from} resultTo={resultRange.to} defaultResultFrom={defaults.from} defaultResultTo={defaults.to} />;
}
