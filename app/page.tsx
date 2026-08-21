import AuctionDashboard from "./AuctionDashboard";
import { getTreasuryData } from "../lib/treasury";

export default async function Home() {
  const data = await getTreasuryData();
  return <AuctionDashboard {...data} />;
}
