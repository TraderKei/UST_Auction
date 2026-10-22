(() => {
  "use strict";

  const encoder = new TextEncoder();
  const icon = '<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" focusable="false"><path fill="#217346" d="M4 2h11l5 5v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path fill="#e8f5ed" d="M14 2v6h6z"/><path fill="#fff" d="m6 10 2.1 3.4L6 17h2l1.2-2.2 1.2 2.2h2l-2.1-3.6L12.4 10h-2l-1.2 2.1L8 10z"/></svg>';

  function xml(value) {
    return String(value ?? "")
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
  }

  function column(index) {
    let letters = "";
    for (let value = index + 1; value; value = Math.floor((value - 1) / 26)) {
      letters = String.fromCharCode(65 + (value - 1) % 26) + letters;
    }
    return letters;
  }

  function crc32(bytes) {
    let crc = -1;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    return (crc ^ -1) >>> 0;
  }

  function zip(files) {
    const localParts = [];
    const directoryParts = [];
    let offset = 0;
    for (const [name, contents] of files) {
      const filename = encoder.encode(name);
      const data = encoder.encode(contents);
      const checksum = crc32(data);
      const local = new Uint8Array(30 + filename.length + data.length);
      const l = new DataView(local.buffer);
      l.setUint32(0, 0x04034b50, true);
      l.setUint16(4, 20, true);
      l.setUint16(6, 0x0800, true);
      l.setUint32(14, checksum, true);
      l.setUint32(18, data.length, true);
      l.setUint32(22, data.length, true);
      l.setUint16(26, filename.length, true);
      local.set(filename, 30);
      local.set(data, 30 + filename.length);
      localParts.push(local);

      const directory = new Uint8Array(46 + filename.length);
      const d = new DataView(directory.buffer);
      d.setUint32(0, 0x02014b50, true);
      d.setUint16(4, 20, true);
      d.setUint16(6, 20, true);
      d.setUint16(8, 0x0800, true);
      d.setUint32(16, checksum, true);
      d.setUint32(20, data.length, true);
      d.setUint32(24, data.length, true);
      d.setUint16(28, filename.length, true);
      d.setUint32(42, offset, true);
      directory.set(filename, 46);
      directoryParts.push(directory);
      offset += local.length;
    }
    const directoryLength = directoryParts.reduce((sum, part) => sum + part.length, 0);
    const end = new Uint8Array(22);
    const e = new DataView(end.buffer);
    e.setUint32(0, 0x06054b50, true);
    e.setUint16(8, files.length, true);
    e.setUint16(10, files.length, true);
    e.setUint32(12, directoryLength, true);
    e.setUint32(16, offset, true);
    const archive = new Uint8Array(offset + directoryLength + end.length);
    let cursor = 0;
    for (const part of [...localParts, ...directoryParts, end]) {
      archive.set(part, cursor);
      cursor += part.length;
    }
    return archive;
  }

  function workbook(rows) {
    const cells = rows.map((row, rowIndex) => `<row r="${rowIndex + 1}">${row.map((value, columnIndex) =>
      `<c r="${column(columnIndex)}${rowIndex + 1}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`
    ).join("")}</row>`).join("");
    const sheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${cells}</sheetData></worksheet>`;
    return zip([
      ["[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'],
      ["_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
      ["xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Auction Results" sheetId="1" r:id="rId1"/></sheets></workbook>'],
      ["xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'],
      ["xl/worksheets/sheet1.xml", sheet],
    ]);
  }

  function tableRows(table) {
    const headers = [...table.querySelectorAll("thead th")].map((cell) => cell.textContent.trim());
    const body = [...table.querySelectorAll("tbody tr")]
      .filter((row) => !row.querySelector(".empty-state"))
      .map((row) => [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim().replace(/\s+/g, " ")));
    return [headers, ...body];
  }

  function download() {
    const table = document.querySelector("#auction-results table");
    if (!table) return;
    const blob = new Blob([workbook(tableRows(table))], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = `UST_auction_results_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.__UST_RESULTS_EXCEL_V1__ = { workbook, tableRows, download, icon };
})();
