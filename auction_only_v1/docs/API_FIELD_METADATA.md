# 실제 Fiscal Data API 필드 메타데이터

기준: tests_pipeline/fixtures/auctions_page_1.json. URL/수집시각/hash는 MANIFEST.json. 첫 응답의 전체 labels/dataTypes/dataFormats를 그대로 대조한다. price_per100/high_price는 원천 STRING이지만 Decimal로 정규화한다.

| 원천 snake_case | label | dataType | dataFormat | 최소 수집 | DB 원천 보존 |
|---|---|---|---|---|---|
| `record_date` | Record Date | DATE | YYYY-MM-DD | 예 | record_date |
| `cusip` | CUSIP | STRING | String | 예 | cusip |
| `security_type` | Security Type | STRING | String | 예 | security_type |
| `security_term` | Security Term | STRING | String | 예 | security_term |
| `auction_date` | Auction Date | DATE | YYYY-MM-DD | 예 | auction_date |
| `issue_date` | Issue Date | DATE | YYYY-MM-DD | 예 | issue_date |
| `maturity_date` | Maturity Date | DATE | YYYY-MM-DD | 예 | maturity_date |
| `price_per100` | Price per $100 | STRING | String | 예 | price_per_100 |
| `accrued_int_per100` | Accrued Interest per $100 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `accrued_int_per1000` | Accrued Interest per $1,000 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `adj_accrued_int_per1000` | Adjusted Accrued Interest per $1,000 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `adj_price` | Adjusted Price | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `allocation_pctage` | Allocation Percentage | NUMBER | 10.2 | 예 | allocation_percentage |
| `allocation_pctage_decimals` | Allocation Percentage Decimals | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `announcemtd_cusip` | Announced CUSIP | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `announcemt_date` | Announcement Date | DATE | YYYY-MM-DD | 예 | announcement_date |
| `auction_format` | Auction Format | STRING | String | 예 | auction_format |
| `avg_med_discnt_rate` | Average/Median Discount Rate | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `avg_med_investment_rate` | Average/Median Investment Rate | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `avg_med_price` | Average/Median Price | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `avg_med_discnt_margin` | Average/Median Discount Margin | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `avg_med_yield` | Average/Median Yield | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `back_dated` | Back Dated | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `back_dated_date` | Back Dated Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `bid_to_cover_ratio` | Bid-to-Cover Ratio | NUMBER | 10.2 | 예 | bid_to_cover_ratio |
| `callable` | Callable | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `call_date` | Call Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `called_date` | Called Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `cash_management_bill_cmb` | Cash Management Bill (CMB) | STRING | String | 예 | cash_management_bill |
| `closing_time_comp` | Closing Time (ET) - Competitive | STRING | String | 예 | closing_time_comp |
| `closing_time_noncomp` | Closing Time (ET) - Noncompetitive | STRING | String | 예 | closing_time_noncomp |
| `comp_accepted` | Competitive Accepted | NUMBER | 10.2 | 예 | competitive_accepted_usd |
| `comp_bid_decimals` | Competitive Bid Decimals | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `comp_tendered` | Competitive Tendered | NUMBER | 10.2 | 예 | competitive_tendered_usd |
| `comp_tenders_accepted` | Competitive Tenders Accepted | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `corpus_cusip` | Corpus CUSIP | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `cpi_base_reference_period` | CPI Base Reference Period | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `currently_outstanding` | Currently Outstanding | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `dated_date` | Dated Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `direct_bidder_accepted` | Direct Bidder Accepted | NUMBER | 10.2 | 예 | direct_bidder_accepted |
| `direct_bidder_tendered` | Direct Bidder Tendered | NUMBER | 10.2 | 예 | direct_bidder_tendered |
| `est_pub_held_mat_by_type_amt` | Estimated Amount of Publicly Held Maturing Securities by Type | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `fima_included` | FIMA Included | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `fima_noncomp_accepted` | FIMA Noncompetitive Accepted | NUMBER | 10.2 | 예 | fima_noncomp_accepted |
| `fima_noncomp_tendered` | FIMA Noncompetitive Tendered | NUMBER | 10.2 | 예 | fima_noncomp_tendered |
| `first_int_period` | First Interest Period | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `first_int_payment_date` | First Interest Payment Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `floating_rate` | Floating Rate | STRING | String | 예 | floating_rate |
| `frn_index_determination_date` | FRN Index Determination Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `frn_index_determination_rate` | FRN Index Determination Rate | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `high_discnt_rate` | High Discount Rate | NUMBER | 10.2 | 예 | high_discount_rate |
| `high_investment_rate` | High Investment Rate | NUMBER | 10.2 | 예 | high_investment_rate |
| `high_price` | High Price | STRING | String | 예 | high_price |
| `high_discnt_margin` | High Discount Margin | NUMBER | 10.2 | 예 | high_discount_margin |
| `high_yield` | High Yield | NUMBER | 10.2 | 예 | high_yield |
| `index_ratio_on_issue_date` | Index Ratio On Issue Date | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `indirect_bidder_accepted` | Indirect Bidder Accepted | NUMBER | 10.2 | 예 | indirect_bidder_accepted |
| `indirect_bidder_tendered` | Indirect Bidder Tendered | NUMBER | 10.2 | 예 | indirect_bidder_tendered |
| `int_payment_frequency` | Interest Payment Frequency | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `int_rate` | Interest Rate | NUMBER | 10.2 | 예 | interest_rate |
| `low_discnt_rate` | Low Discount Rate | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `low_investment_rate` | Low Investment Rate | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `low_price` | Low Price | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `low_discnt_margin` | Low Discount Margin | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `low_yield` | Low Yield | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `mat_date` | Maturing Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `max_comp_award` | Maximum Competitive Award | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `max_noncomp_award` | Maximum Noncompetitive Award | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `max_single_bid` | Maximum Single Bid | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `min_bid_amt` | Minimum Bid Amount | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `min_strip_amt` | Minimum Strip Amount | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `min_to_issue` | Minimum To Issue | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `multiples_to_bid` | Multiples To Bid | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `multiples_to_issue` | Multiples To Issue | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `nlp_exclusion_amt` | NLP Exclusion Amount | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `nlp_reporting_threshold` | NLP Reporting Threshold | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `noncomp_accepted` | Noncompetitive Accepted | NUMBER | 10.2 | 예 | noncompetitive_accepted_usd |
| `noncomp_tenders_accepted` | Noncompetitive Tenders Accepted | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `offering_amt` | Offering Amount | CURRENCY0 | $1,000,000 | 예 | offering_amount_usd |
| `original_cusip` | Original CUSIP | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `original_dated_date` | Original Dated Date | DATE | YYYY-MM-DD | 아니오 | 최소집합 밖; 메타만 보존 |
| `original_issue_date` | Original Issue Date | DATE | YYYY-MM-DD | 예 | original_issue_date |
| `original_security_term` | Original Security Term | STRING | String | 예 | original_security_term |
| `pdf_filenm_announcemt` | Download PDF - Announcement | STRING | String | 예 | pdf_filename_announcement |
| `pdf_filenm_comp_results` | Download PDF - Competitive Results | STRING | String | 예 | pdf_filename_comp_results |
| `pdf_filenm_noncomp_results` | Download PDF - Noncompetitive Results | STRING | String | 예 | pdf_filename_noncomp_results |
| `primary_dealer_accepted` | Primary Dealer Accepted | NUMBER | 10.2 | 예 | primary_dealer_accepted |
| `primary_dealer_tendered` | Primary Dealer Tendered | NUMBER | 10.2 | 예 | primary_dealer_tendered |
| `ref_cpi_on_dated_date` | Reference CPI On Dated Date | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `ref_cpi_on_issue_date` | Reference CPI On Issue Date | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `reopening` | Reopening | STRING | String | 예 | reopening |
| `security_term_day_month` | Security Term Day Month | STRING | String | 예 | security_term_day_month |
| `security_term_week_year` | Security Term Week Year | STRING | String | 예 | security_term_week_year |
| `series` | Series | STRING | String | 예 | series |
| `soma_accepted` | SOMA Accepted | NUMBER | 10.2 | 예 | soma_accepted |
| `soma_holdings` | SOMA Holdings | NUMBER | 10.2 | 예 | soma_holdings |
| `soma_included` | SOMA Included | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `soma_tendered` | SOMA Tendered | NUMBER | 10.2 | 예 | soma_tendered |
| `spread` | Spread | NUMBER | 10.2 | 예 | spread |
| `std_int_payment_per1000` | Standard Interest Payment per $1,000 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `strippable` | Strippable | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `tiin_conversion_factor_per1000` | TIIN Conversion Factor per $1,000 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `total_accepted` | Total Accepted | NUMBER | 10.2 | 예 | total_accepted_usd |
| `total_tendered` | Total Tendered | NUMBER | 10.2 | 예 | total_tendered_usd |
| `treas_retail_accepted` | Treasury Retail Accepted | NUMBER | 10.2 | 예 | treasury_retail_accepted_usd |
| `treas_retail_tenders_accepted` | Treasury Retail Tenders Accepted | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `unadj_accrued_int_per1000` | Unadjusted Accrued Interest per $1,000 | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `unadj_price` | Unadjusted Price | NUMBER | 10.2 | 아니오 | 최소집합 밖; 메타만 보존 |
| `xml_filenm_announcemt` | Download XML - Announcement | STRING | String | 예 | xml_filename_announcement |
| `xml_filenm_comp_results` | Download XML - Competitive Results | STRING | String | 예 | xml_filename_comp_results |
| `inflation_index_security` | Inflation Index Security | STRING | String | 예 | inflation_index_security |
| `tint_cusip_1` | Tint CUSIP 1 | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `tint_cusip_2` | Tint CUSIP 2 | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
| `pdf_filenm_spec_announcemt` | PDF Filename - Special Announcement | STRING | String | 아니오 | 최소집합 밖; 메타만 보존 |
