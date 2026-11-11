"""Build the offline terminal using DB_TABLE.xlsx as the only data source."""
from pathlib import Path
from datetime import date, datetime
import hashlib
import json
import openpyxl

ROOT = Path(__file__).resolve().parents[1]


def extract(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    tables = {}
    for row in book['Table'].values:
        if isinstance(row[3], (int, float)):
            key = str(int(row[3]))
            values = list(book[key].values)
            headers = values[0]
            records = []
            for number, cells in enumerate(values[1:], 2):
                if not any(v is not None for v in cells):
                    continue
                record = dict(zip(headers, cells))
                record['_row'] = number
                records.append(record)
            tables[key] = {'name': row[1], 'description': row[2], 'headers': list(headers), 'rows': records}
    specs = [dict(zip(['table', 'column', 'type', 'length', 'required', 'default', 'description'], r[1:]))
             for r in list(book['Column'].values)[2:] if r[1]]
    for table in tables.values():
        expected = {s['column'] for s in specs if s['table'] == table['name']}
        if expected != set(table['headers']):
            raise ValueError('Column spec mismatch: ' + table['name'])
    book.close()
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'tables': tables, 'specs': specs}


def build():
    data = extract(ROOT / 'DB_TABLE.xlsx')
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        raise TypeError(type(value).__name__)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=encode).replace('<', '\\u003c')
    folder = Path(__file__).parent
    html = (folder / 'template.html').read_text(encoding='utf-8')
    html = html.replace('/*__STYLE__*/', (folder / 'style.css').read_text(encoding='utf-8'))
    html = html.replace('/*__DATA__*/', payload).replace('/*__APP__*/', (folder / 'app.js').read_text(encoding='utf-8'))
    target = ROOT / 'KTB_AUCTION_DB.html'
    target.write_text(html, encoding='utf-8')
    print(f'{target.name}: {sum(len(t["rows"]) for t in data["tables"].values())} records, {len(data["tables"])} tables')


if __name__ == '__main__':
    build()
