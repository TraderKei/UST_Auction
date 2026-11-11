// Run with bundled Node; NODE_PATH must include the bundled node_modules.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
 await page.goto(pathToFileURL(path.resolve(__dirname,'../KTB_AUCTION_DB.html')).href);
 assert.equal(await page.locator('#tabs button').count(),6);
 assert.equal(await page.evaluate(()=>Object.values(DB.tables).reduce((n,t)=>n+t.rows.length,0)),1674);
 const check=await page.evaluate(()=>({
   latest:comp.find(r=>r.id==='1!2'),
   november:sum(comp.filter(r=>r.date.startsWith('2026-11')),'won'),
   ambiguity:planGroups(plans.filter(r=>r.date.startsWith('2026-11')&&r.mat==='3Y')),
   missing:sum([],'won'),zero:fmt(0),dateZero:date(0),badDate:date(20260230),
   nullRatio:ratio(null,4),zeroDenominator:ratio(4,0),
   totals: [...group(other.filter(r=>r.s===6),r=>r.date+'|'+r.round)].map(([k,a])=>({k,details:sum(a,'won'),total:a[0].raw.TOTAL_ALLOCATION_AMOUNT}))
 }));
 assert.equal(check.latest.btc,33330/11000);assert.equal(check.latest.tail,0);assert.equal(check.latest.payment,'2026-11-10');
 assert.equal(check.missing,null);assert.equal(check.zero,'0');assert.equal(check.dateZero,null);assert.equal(check.badDate,null);
 assert.equal(check.nullRatio,null);assert.equal(check.zeroDenominator,null);
 assert.equal(check.ambiguity[0].amount,null);assert.equal(check.ambiguity[0].ambiguous,true);
 for(const t of check.totals)assert.equal(t.details,t.total,`buyback reconciliation ${t.k}`);
 for(const tab of ['auc','res','dmd','plan','sd','pd']){await page.locator(`[data-tab=${tab}]`).click();assert((await page.locator('#content').innerText()).length>100);}
 await page.locator('[data-tab=auc]').click();
 await page.locator('#content tr[data-event="1!2"]').click();await page.locator('#detail').waitFor({state:'visible'});
 assert((await page.locator('#detailBody').innerText()).includes('33330'));await page.locator('#closeDetail').click();
 await page.locator('#search').fill('NO_MATCH_BOND');assert((await page.locator('#content').innerText()).includes('조회 조건에 맞는 데이터가 없습니다.'));
 await page.locator('#reset').click();
 await page.locator('#from').fill('2025-07');await page.locator('#from').dispatchEvent('change');
 await page.locator('[data-tab=dmd]').click();await page.locator('#metric').selectOption('tail');
 assert((await page.locator('#content').innerText()).includes('테일'));
 await page.locator('#maturity').selectOption('3Y');await page.locator('[data-tab=res]').click();
 assert(await page.evaluate(()=>filtered(comp).every(r=>r.mat==='3Y')));
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#export').click()]);
 const csv=fs.readFileSync(await download.path(),'utf8');assert(csv.includes('원본 행'));assert(csv.includes('3Y'));
 await page.locator('#source > summary').click();
 for(let i=1;i<=13;i++){await page.locator('#sourceTable').selectOption(String(i));assert((await page.locator('#raw tbody tr').count())>0);}
 await page.locator('#sourceSearch').fill('NO_MATCH_BOND');assert((await page.locator('#raw').innerText()).includes('데이터가 없습니다'));
 await page.locator('#source > summary').click();await page.locator('#reset').click();await page.locator('[data-tab=auc]').click();
 await page.screenshot({path:path.join(process.env.TEMP||process.env.TMP||'.','ktb-db-desktop.png'),fullPage:true});
 await page.locator('#theme').click();assert(await page.locator('body').evaluate(e=>e.classList.contains('light')));
 await page.setViewportSize({width:600,height:850});
 await page.screenshot({path:path.join(process.env.TEMP||process.env.TMP||'.','ktb-db-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
 assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
 console.log(JSON.stringify({status:'PASS',checks:'6 screens, source rows, formulas, zero/null, join, ambiguous plans, buyback reconciliation, filters, modal, CSV, 13 raw tables, theme, responsive, no network/errors',novemberCompetitive:check.november,screenshots:process.env.TEMP},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
