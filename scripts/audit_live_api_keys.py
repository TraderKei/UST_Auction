"""Optional read-only full API business-key audit. Saves raw responses and report."""
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from ust_pipeline.config import Settings
from ust_pipeline.fiscal import AUCTIONS_URL
from ust_pipeline.http_client import TreasuryHttpClient
from ust_pipeline.raw_store import RawStore

s=Settings()
keys=Counter(); null_keys=Counter(); total=0; pages=0; paths=[]
with TreasuryHttpClient(s.user_agent, s.http_timeout_seconds, s.http_max_retries, ca_bundle=str(s.ca_bundle) if s.ca_bundle else None) as http:
    while True:
        pages+=1
        r=http.get(AUCTIONS_URL,params={'fields':'cusip,auction_date,issue_date,record_date,security_type,security_term','format':'json','sort':'auction_date,cusip,issue_date','page[number]':pages,'page[size]':5000})
        raw=RawStore(Path('work/source-audit/raw')).put(r.content,'fiscal-auctions',r.headers.get('content-type'));paths.append(str(raw.path))
        payload=json.loads(r.content,parse_float=str)
        for row in payload['data']:
            key=tuple(row[k] for k in ['cusip','auction_date','issue_date']);keys[key]+=1;total+=1
            for k in ['cusip','auction_date','issue_date']:
                if row[k] in (None,'','null'):null_keys[k]+=1
        if pages>=int(payload['meta']['total-pages']):break
report={'checked_at':datetime.now(UTC).isoformat(),'endpoint':AUCTIONS_URL,'rows':total,'meta_total_count':payload['meta']['total-count'],'pages':pages,'null_key_counts':dict(null_keys),'duplicate_key_groups':sum(v>1 for v in keys.values()),'duplicate_examples':[{'key':k,'count':v} for k,v in keys.items() if v>1][:10],'raw_paths':paths}
Path('work/source-audit').mkdir(parents=True,exist_ok=True)
Path('work/source-audit/API_KEY_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
