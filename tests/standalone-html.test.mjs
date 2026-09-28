import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const htmlUrl = new URL("../UST_AUCTION_ui-baseline-v2.html", import.meta.url);

async function liveScript() {
  const html = await readFile(htmlUrl, "utf8");
  const marker = '<script id="official-live-data-script">';
  const start = html.indexOf(marker);
  const end = html.indexOf("</script>", start);
  assert.ok(start >= 0 && end > start, "official live data script must exist");
  return { html, script: html.slice(start + marker.length, end) };
}

test("standalone baseline opens on an official live-data view", async () => {
  const { html, script } = await liveScript();
  assert.match(html, /공식 실데이터/);
  assert.match(script, /api\.fiscaldata\.treasury\.gov/);
  assert.match(script, /activateLive\(\)/);
  assert.match(script, /requestAnimationFrame\(\(\) => requestAnimationFrame\(init\)\)/);
  assert.doesNotMatch(script, /fallbackUpcoming|fallbackResults|resultSeed/);
});

test("standalone loader follows every Fiscal Data page and rejects partial results", async () => {
  const { script } = await liveScript();
  assert.match(script, /page\[number\]/);
  assert.match(script, /total-pages/);
  assert.match(script, /total-count/);
  assert.match(script, /rows\.length !== expected/);
  assert.match(script, /페이지 누락/);
});

test("standalone loader maps official result fields and has valid JavaScript", async () => {
  const { script } = await liveScript();
  assert.doesNotThrow(() => new Function(script));
  for (const field of [
    "inflation_index_security", "floating_rate", "high_discnt_rate", "high_discnt_margin",
    "high_yield", "bid_to_cover_ratio", "allocation_pctage", "primary_dealer_accepted",
    "direct_bidder_accepted", "indirect_bidder_accepted",
  ]) assert.ok(script.includes(field), field);
  assert.match(script, /표본값으로 대체하지 않았습니다/);
});

test("standalone auction navigation switches between result and schedule views", async () => {
  const { html, script } = await liveScript();
  assert.match(html, /official-live-view \[hidden\] \{ display: none !important; \}/);
  assert.match(script, /function applyLiveMode\(\)/);
  assert.match(script, /activateLive\(label === "입찰 일정" \? "schedule" : "results"\)/);
  assert.match(script, /results\.hidden = scheduleOnly/);
  assert.match(script, /upcoming\.hidden = resultsOnly/);
  assert.match(script, /label === "입찰 결과"/);
  assert.match(script, /label === "입찰 일정"/);
});
