import hashlib
import json
from datetime import date
from decimal import Decimal

import httpx

from ust_pipeline.fiscal import FiscalDataClient
from ust_pipeline.http_client import TreasuryHttpClient
from ust_pipeline.qra.discovery import discover_qra_index
from ust_pipeline.qra.parsers import ParserDispatcher


def test_manifest_hashes_are_exact(fixture_dir):
    manifest=json.loads((fixture_dir/'MANIFEST.json').read_text(encoding='utf-8'))
    for filename, info in manifest['files'].items():
        assert hashlib.sha256((fixture_dir/filename).read_bytes()).hexdigest()==info['sha256'], filename


def test_total_pages_is_authoritative_even_when_next_link_omitted():
    seen=[]
    def handler(request):
        seen.append(int(request.url.params['page[number]']))
        return httpx.Response(200,json={'data':[{}], 'meta':{'total-pages':2},'links':{}},request=request)
    with TreasuryHttpClient('test',transport=httpx.MockTransport(handler)) as h:
        assert len(list(FiscalDataClient(h).iter_auction_pages(date(2026,1,1),date(2026,1,2))))==2
    assert seen==[1,2]


def test_conditional_304_returns_without_exception():
    def handler(request):
        assert request.headers['If-None-Match']=='test-etag'
        return httpx.Response(304,request=request)
    with TreasuryHttpClient('test',transport=httpx.MockTransport(handler)) as h:
        assert h.get('https://home.treasury.gov/test',etag='test-etag').status_code==304


def test_survey_source_proves_mean_period_and_not_current(fixture_dir):
    result=ParserDispatcher.parse('PRIMARY_DEALER_SURVEY_PDF',(fixture_dir/'dealer_survey_2026q2.pdf').read_bytes())
    index=next(i for i,r in enumerate(result.records) if r['normalized_security_term']=='2Y' and r['security_type']=='Nominal coupon' and r['target_fiscal_year']==2027 and r['statistic']=='TRIMMED_MEAN' and r['scenario']=='SIZE_EXPECTATION')
    row=result.records[index]
    assert row['expected_auction_size_usd']==Decimal('77500000000')
    assert row['current_auction_size_usd'] is None
    assert row['survey_as_of_date'] is None and row['survey_as_of_month']==date(2026,4,1)
    assert result.evidence[index].page_number==1 and 'FY27' in result.evidence[index].column_label
    archive=discover_qra_index((fixture_dir/'survey_archive.html').read_bytes(),'https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/quarterly-refunding-archives/primary-dealer-auction-size-survey')
    assert (archive.links[0].refunding_year,archive.links[0].refunding_quarter)==(2026,2)


def test_actual_borrowing_excludes_counterfactual_cash_adjustment(fixture_dir):
    result=ParserDispatcher.parse('FINANCING_ESTIMATES_HTML',(fixture_dir/'financing_estimates_2026q3.html').read_bytes())
    actual=next(r for r in result.records if r['value_class']=='OFFICIAL_ACTUAL')
    assert actual['borrowing_amount_usd']==Decimal('190000000000')
    assert actual['end_cash_balance_usd']==Decimal('919000000000')
    assert actual['change_from_prior_usd'] is None


def test_xml_holidays_are_not_auction_events(fixture_dir):
    r=ParserDispatcher.parse('TENTATIVE_AUCTION_XML',(fixture_dir/'auction_schedule_2026q3.xml').read_bytes())
    assert len(r.records)==213
    assert len([i for i in r.issues if i.rule=='XML_NON_AUCTION_ROW'])==7
    assert all(row['auction_date'] for row in r.records)


def test_decimal_spelling_does_not_create_a_revision(fixture_dir):
    from ust_pipeline.auction import normalize_auction
    raw=json.loads((fixture_dir/'auctions_page_1.json').read_text())['data'][0]
    first=normalize_auction(dict(raw,bid_to_cover_ratio='2.4800000000'))
    second=normalize_auction(dict(raw,bid_to_cover_ratio='2.48'))
    assert first.canonical_hash()==second.canonical_hash()


def test_official_host_scope_blocks_external_redirect():
    import pytest
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(302,headers={'Location':'https://example.net/out-of-scope'},request=request)
    with TreasuryHttpClient('test',transport=httpx.MockTransport(handler),allowed_hosts={'home.treasury.gov'}) as h:
        with pytest.raises(ValueError,match='scope'): h.get('https://home.treasury.gov/test')
    assert calls==['home.treasury.gov']


def test_missing_xml_auction_date_is_quarantined():
    content=b'<AuctionCalendar><AuctionCalendarDate><SecurityType>NOTE</SecurityType></AuctionCalendarDate></AuctionCalendar>'
    assert ParserDispatcher.parse('TENTATIVE_AUCTION_XML',content).status=='QUARANTINED'
