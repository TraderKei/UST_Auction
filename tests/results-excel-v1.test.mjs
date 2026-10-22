import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../scripts/results_excel_v1.js", import.meta.url), "utf8");
const context = {
  window: {},
  document: { readyState: "loading", addEventListener() {} },
  TextEncoder,
};
vm.runInNewContext(source, context);
const { workbook, tableRows } = context.window.__UST_RESULTS_EXCEL_V1__;

function storedFiles(archive) {
  const bytes = Buffer.from(archive);
  const files = new Map();
  let offset = 0;
  while (bytes.readUInt32LE(offset) === 0x04034b50) {
    const length = bytes.readUInt32LE(offset + 18);
    const nameLength = bytes.readUInt16LE(offset + 26);
    const name = bytes.toString("utf8", offset + 30, offset + 30 + nameLength);
    const start = offset + 30 + nameLength;
    files.set(name, bytes.toString("utf8", start, start + length));
    offset = start + length;
  }
  assert.equal(bytes.readUInt32LE(offset), 0x02014b50);
  return files;
}

test("Excel workbook contains visible table headers and rows with valid XML escaping", () => {
  const table = {
    querySelectorAll(selector) {
      if (selector === "thead th") return [{ textContent: "입찰일" }, { textContent: "만기 / 종류" }];
      if (selector === "tbody tr") return [
        { querySelector: () => null, querySelectorAll: () => [{ textContent: "2026-10-22" }, { textContent: "10일 단기채 & 재발행" }] },
        { querySelector: () => ({}), querySelectorAll: () => [{ textContent: "결과 없음" }] },
      ];
      throw new Error(selector);
    },
  };
  const rows = tableRows(table);
  assert.deepEqual(JSON.parse(JSON.stringify(rows)), [
    ["입찰일", "만기 / 종류"],
    ["2026-10-22", "10일 단기채 & 재발행"],
  ]);
  const files = storedFiles(workbook(rows));
  assert.equal(files.size, 5);
  assert.match(files.get("xl/workbook.xml"), /sheet name="Auction Results"/);
  assert.match(files.get("xl/worksheets/sheet1.xml"), /<c r="B2" t="inlineStr"><is><t xml:space="preserve">10일 단기채 &amp; 재발행<\/t>/);
  assert.doesNotMatch(files.get("xl/worksheets/sheet1.xml"), /결과 없음/);
});
