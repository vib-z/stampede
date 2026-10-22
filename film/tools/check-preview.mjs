import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';
const out=process.env.FILM_MEDIA;if(!out)throw new Error('Set FILM_MEDIA');
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
const bases=(process.env.FILM_PREVIEW_URLS||'http://127.0.0.1:8856/,http://127.0.0.1:8865/preview/').split(',');
for(const base of bases)for(const width of [390,1440])for(const theme of ['light','dark']){
 const page=await browser.newPage({viewport:{width,height:width===390?844:900},deviceScaleFactor:2,colorScheme:theme==='light'?'dark':'light'});
 // Exercise the host override against the opposite OS preference.
 await page.addInitScript(theme=>{new MutationObserver(()=>{if(document.documentElement){document.documentElement.dataset.theme=theme;}}).observe(document,{childList:true});},theme);
 const errors=[],failed=[];page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>{if(r.failure()?.errorText!=='net::ERR_ABORTED')failed.push(r.url());});page.on('response',r=>{if(r.status()>=400)failed.push(r.url()+':'+r.status());});
 await page.goto(base);
 const variant=`${width===390?'phone':'desktop'}-${theme}`;
 await page.waitForFunction(v=>window.__filmStats?.variant===v&&window.__filmStats.quality==='full',variant);
 const observed=[];
 for(const frame of [0,48,104,141,170,259,300,357,419,260,20,419]){
  await page.evaluate(f=>{const r=document.querySelector('.film-section');scrollTo(0,r.offsetTop+(r.offsetHeight-innerHeight)*f/419);},frame);
  await page.waitForFunction(f=>window.__filmStats.frame===f&&window.__filmStats.quality==='full',frame);
  observed.push(await page.evaluate(()=>({frame:window.__filmStats.frame,beat:document.querySelector('.beat-title')?.textContent??null})));
 }
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
 const remote=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>r.name).filter(n=>!n.startsWith(location.href)));
 assert.deepEqual(remote,[]);
 results.push({base,width,theme,variant,observed,errors,failed,externalRequests:remote});await page.close();
}
await fs.writeFile(path.join(out,'preview-checks.json'),JSON.stringify(results,null,2));
console.log(`${results.length} root/subpath, width and forced-theme combinations passed`);
await browser.close();
