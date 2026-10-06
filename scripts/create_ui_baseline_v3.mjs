import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const sourceUrl = new URL("../UST_AUCTION_ui-baseline-v2.html", import.meta.url);
const targetUrl = new URL("../UST_AUCTION_ui-baseline-v3.html", import.meta.url);

let html = await readFile(sourceUrl, "utf8");

function replaceOnce(label, before, after) {
  const matches = html.split(before).length - 1;
  if (matches !== 1) {
    throw new Error(`${label}: expected one match, found ${matches}`);
  }
  html = html.replace(before, after);
}

replaceOnce(
  "document title",
  "<title>UST AUCTION · UI Baseline v2 · QRA Supply</title>",
  "<title>UST AUCTION · UI Baseline v3</title>",
);

replaceOnce(
  "server-rendered navigation",
  '<nav class="nav" aria-label="주요 메뉴"><button class="" aria-pressed="false">입찰 일정</button><button class="active" aria-pressed="true">입찰 결과</button><button class="" aria-pressed="false">API 필드</button><button class="" aria-pressed="false">데이터 구조</button></nav>',
  '<nav class="nav" aria-label="주요 메뉴"><button class="active" aria-pressed="true">입찰 결과</button></nav>',
);

replaceOnce(
  "interactive navigation",
  'children:[(0,A.jsx)(`button`,{className:a===`market`&&s===`calendar`?`active`:``,"aria-pressed":a===`market`&&s===`calendar`,onClick:()=>Se(`calendar`),children:`입찰 일정`}),(0,A.jsx)(`button`,{className:a===`market`&&s===`results`?`active`:``,"aria-pressed":a===`market`&&s===`results`,onClick:()=>Se(`results`),children:`입찰 결과`}),(0,A.jsx)(`button`,{className:a===`api`?`active`:``,"aria-pressed":a===`api`,onClick:()=>o(`api`),children:`API 필드`}),(0,A.jsx)(`button`,{className:a===`database`?`active`:``,"aria-pressed":a===`database`,onClick:()=>o(`database`),children:`데이터 구조`})]',
  'children:(0,A.jsx)(`button`,{className:`active`,"aria-pressed":!0,children:`입찰 결과`})',
);

const referenceStart = html.indexOf("var xe=[{title:`종류·만기`");
const referenceEnd = html.indexOf("var M=e=>", referenceStart);
if (referenceStart < 0 || referenceEnd < 0) {
  throw new Error("customer-facing API/database reference views were not found");
}
html = `${html.slice(0, referenceStart)}function Ce(){return null}${html.slice(referenceEnd)}`;

const qraStart = html.indexOf('<style id="qra-integration-styles">');
const qraScriptStart = html.indexOf('<script id="qra-integration-script">', qraStart);
const qraScriptEnd = html.indexOf("</script>", qraScriptStart);
if (qraStart < 0 || qraScriptStart < 0 || qraScriptEnd < 0) {
  throw new Error("QRA integration block was not found");
}
html = `${html.slice(0, qraStart)}${html.slice(qraScriptEnd + "</script>".length)}`;

for (const removedLabel of ["QRA 공급", "API 필드", "데이터 구조"]) {
  if (html.includes(removedLabel)) {
    throw new Error(`removed customer section remains: ${removedLabel}`);
  }
}

await writeFile(targetUrl, html, "utf8");
console.log(`Created ${fileURLToPath(targetUrl)}`);
