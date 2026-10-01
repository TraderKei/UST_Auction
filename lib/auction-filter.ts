export const AUCTION_FILTER_IDS = [
  "all",
  "bill",
  "note-2",
  "note-3",
  "note-5",
  "note-7",
  "note-10",
  "bond-20",
  "bond-30",
  "tips",
  "frn",
] as const;

export type AuctionFilterId = typeof AUCTION_FILTER_IDS[number];

export function resolveAuctionFilter(value: string | string[] | undefined): AuctionFilterId {
  const candidate = Array.isArray(value) ? value[0] : value;
  return AUCTION_FILTER_IDS.includes(candidate as AuctionFilterId) ? candidate as AuctionFilterId : "all";
}
