import AuctionDashboard from "./AuctionDashboard";
import { getTreasuryData } from "../lib/treasury";
import { defaultAuctionDateRange, resolveAuctionDateRange } from "../lib/auction-date-range";
import { resolveAuctionFilter } from "../lib/auction-filter";

type SearchParameters = { from?: string | string[]; to?: string | string[]; filter?: string | string[] };

export default async function Home({ searchParams }: { searchParams?: Promise<SearchParameters> }) {
  const today = new Date();
  const defaults = defaultAuctionDateRange(today);
  const parameters = await searchParams;
  const resultRange = resolveAuctionDateRange(parameters, today);
  const initialFilter = resolveAuctionFilter(parameters?.filter);
  const data = await getTreasuryData(resultRange);
  return <AuctionDashboard {...data} initialFilter={initialFilter} resultFrom={resultRange.from} resultTo={resultRange.to} defaultResultFrom={defaults.from} defaultResultTo={defaults.to} />;
}
