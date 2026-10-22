import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
await page.route('**/*.json',async route=>{await new Promise(resolve=>setTimeout(resolve,80));await route.continue();});
await page.goto('http://127.0.0.1:8855/site/');
await page.waitForFunction(()=>window.__filmStats?.frame===0&&window.__filmStats.quality==='full');
await page.setViewportSize({width:1440,height:900});
await page.waitForFunction(()=>window.__filmStats.ready&&window.__filmStats.frame===window.__filmStats.target&&window.__filmStats.size[0]>1000&&window.__filmStats.variant.startsWith('desktop-'));
await page.emulateMedia({colorScheme:'dark'});
await page.setViewportSize({width:390,height:844});
await page.waitForFunction(()=>window.__filmStats.ready&&window.__filmStats.frame===window.__filmStats.target&&window.__filmStats.size[0]<1000&&window.__filmStats.variant==='phone-dark');
await page.emulateMedia({reducedMotion:'reduce'});
await page.waitForFunction(()=>!document.documentElement.classList.contains('motion-enabled')).catch(async error=>{
  console.error(await page.evaluate(()=>({reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,classes:document.documentElement.className,frame:window.__filmStats.frame,target:window.__filmStats.target,ready:window.__filmStats.ready,variant:window.__filmStats.variant,subscribedReduced:window.__filmStats.reduced})));
  throw error;
});
await page.emulateMedia({reducedMotion:'no-preference'});
await page.waitForFunction(()=>window.__filmStats.ready&&window.__filmStats.frame===window.__filmStats.target);
for(const target of [240,70,418,0]) {
  await page.evaluate(frame=>scrollTo(0,(document.querySelector('.film-section').offsetHeight-innerHeight)*frame/419),target);
  await page.waitForFunction(frame=>window.__filmStats.frame===frame,target);
}
await page.waitForFunction(()=>!window.__filmStats.positionWatchActive);
await page.waitForFunction(()=>window.__filmStats.cacheSize===420);
assert.ok(await page.evaluate(()=>window.__filmStats.peakCache===420));
results.push({check:'Native-position watcher releases after rest',pass:true});
results.push({check:'Forward and reverse jumps settle on the exact pose with all 420 compiled poses',pass:true});
assert.deepEqual(errors,[]);
results.push({check:'Delayed fetch, resize, theme change, reduce and resume',pass:true,pageErrors:errors});
await page.close();
// Hold a fetch while a preference changes without a delivered notification.
for(const extension of ['json']){
const delayed=await browser.newPage({viewport:{width:390,height:844},reducedMotion:'no-preference'});
await delayed.addInitScript(()=>{
  const original=window.matchMedia.bind(window);
  window.matchMedia=query=>{
    const result=original(query);
    if(query==='(prefers-reduced-motion: reduce)')result.addEventListener=()=>{};
    return result;
  };
});
let release;const gate=new Promise(resolve=>{release=resolve;});
await delayed.route(`**/*.${extension}`,async route=>{await gate;await route.continue();});
const requested=delayed.waitForRequest(`**/*.${extension}`);
await delayed.goto('http://127.0.0.1:8855/site/');await requested;
await delayed.emulateMedia({reducedMotion:'reduce'});release();
await delayed.waitForFunction(()=>!window.__filmStats.ready&&!document.documentElement.classList.contains('motion-enabled'));
assert.equal(await delayed.locator('.opening').evaluate(img=>getComputedStyle(img).visibility==='visible'),true);
results.push({check:`Pending ${extension} cannot restore motion after an unnotified reduced-motion change`,pass:true});
await delayed.waitForFunction(()=>window.__filmStats.memory.reservedBytes===0);
await delayed.close();
}
const completing=await browser.newPage({viewport:{width:390,height:844}});
await completing.addInitScript(()=>{
  const media=window.matchMedia.bind(window),decode=HTMLImageElement.prototype.decode;
  window.matchMedia=query=>{const result=media(query);if(query.includes('prefers-reduced-motion'))result.addEventListener=()=>{};return result;};
  const gate=new Promise(resolve=>{window.__releaseMaterials=resolve;});
  HTMLImageElement.prototype.decode=async function(){window.__materialPending=true;await gate;return decode.call(this);};
});
await completing.goto('http://127.0.0.1:8855/site/');
await completing.waitForFunction(()=>window.__materialPending);
await completing.emulateMedia({reducedMotion:'reduce'});
await completing.evaluate(()=>window.__releaseMaterials());
await completing.waitForFunction(()=>!window.__filmStats.ready&&!document.documentElement.classList.contains('motion-enabled')&&window.__filmStats.memory.reservedBytes===0);
results.push({check:'Pending material decode cannot restore motion after an unnotified reduced-motion change',pass:true});
await completing.close();
const active=await browser.newPage({viewport:{width:390,height:844}});
await active.addInitScript(()=>{const media=window.matchMedia.bind(window);window.matchMedia=query=>{const result=media(query);if(query.includes('prefers-reduced-motion'))result.addEventListener=()=>{};return result;};});
await active.goto('http://127.0.0.1:8855/site/');await active.waitForFunction(()=>window.__filmStats?.cacheSize===420);
await active.evaluate(()=>scrollTo(0,250));await active.waitForFunction(()=>window.__filmStats.positionWatchActive);
await active.emulateMedia({reducedMotion:'reduce'});
await active.waitForFunction(()=>window.__filmStats.memory.reservedBytes===0&&!document.documentElement.classList.contains('motion-enabled'));
results.push({check:'Active gesture releases materials after an unnotified reduced-motion change',pass:true});await active.close();
const fallback=await browser.newPage({viewport:{width:390,height:844}});
await fallback.route('**/*.json',route=>route.fulfill({status:404,body:''}));
await fallback.goto('http://127.0.0.1:8855/site/');
await fallback.waitForFunction(()=>!document.documentElement.classList.contains('motion-enabled')&&document.querySelector('.opening').src.endsWith('-poster.svg')&&document.querySelector('.opening').naturalWidth>0);
results.push({check:'Missing sequence shows finished poster',pass:true});
await fallback.close();
for(const mode of ['absent','rejected']) {
  const compatible=await browser.newPage({viewport:{width:390,height:844}});
  await compatible.addInitScript(mode=>{
    if(mode==='absent')delete window.createImageBitmap;
    else window.createImageBitmap=async()=>{throw new Error('Unsupported SVG bitmap');};
  },mode);
  await compatible.goto('http://127.0.0.1:8855/site/');
  await compatible.waitForFunction(()=>window.__filmStats?.frame===0&&window.__filmStats.quality==='full');
  assert.equal(await compatible.locator('canvas').evaluate(canvas=>getComputedStyle(canvas).visibility==='visible'),true);
  results.push({check:`Direct vector path when createImageBitmap is ${mode}`,pass:true});
  await compatible.close();
}
await fs.writeFile(path.resolve(import.meta.dirname,'../state-metrics.json'),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results));await browser.close();
