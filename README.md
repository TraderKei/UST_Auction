# FV Terminal — U.S. Treasury Auctions

A light-mode primary-market terminal mockup powered by the official TreasuryDirect securities APIs.

## Product surfaces

- `AU Monitor`: upcoming auction calendar, recent results, bid-to-cover chart, and bidder take-down detail.
- `AP Fields`: recommended extraction set and type-aware transformation rules for the wide TreasuryDirect payload.
- `DB Model`: normalized production data model, ingestion flow, and query-first indexes.

The app attempts a live server-side fetch and falls back to a verified August 21, 2026 snapshot if TreasuryDirect is unavailable.

## Source endpoints

- `https://www.treasurydirect.gov/TA_WS/securities/announced?format=json`
- `https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&day=45`

Detailed field rationale and the ER model are documented in `docs/API_AND_DB_DESIGN.md`. Executable PostgreSQL DDL is in `db/treasury_auction_schema.sql`.

## Local development

```bash
pnpm install
pnpm dev
pnpm build
```
