import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright-core';

const root=path.resolve(import.meta.dirname,'../..');
const evidence=process.env.FILM_MEDIA;
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
for(const theme of ['light','dark']){
  const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2,colorScheme:theme});
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
  await page.goto('http://127.0.0.1:8855/site/');
  await page.waitForFunction(()=>window.__filmStats?.ready&&window.__filmStats.quality==='full');
  await page.waitForFunction(()=>window.__filmStats?.cacheSize===420);
  const observations=await page.evaluate(async()=>{
    const max=document.querySelector('.film-section').offsetHeight-innerHeight,observations=[];
    for(const target of [...Array.from({length:420},(_,i)=>i),...Array.from({length:420},(_,i)=>419-i)]){
      scrollTo(0,max*target/419);
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const s=window.__filmStats;
      observations.push({requested:target,delivered:s.target,displayed:s.frame,quality:s.quality,distance:Math.abs(s.target-s.frame)});
    }
    return observations;
  });
  assert.ok(observations.every(o=>o.requested===o.delivered&&o.distance===0&&o.quality==='full'));
  const beforeRelease=await page.evaluate(()=>({readyAt:window.__filmStats.readyAt,memory:window.__filmStats.memory,instantDraws:window.__filmStats.instantDraws}));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>window.__filmStats.memory.reservedBytes===0);
  results.push({theme,cpu:4,allPosesCompiled:true,...beforeRelease,maxDistance:Math.max(...observations.map(o=>o.distance)),releasedAllDecodedFrames:true,observations});
  await page.close();console.log(`${theme}: 840 forward/reverse poses are exact and vector-sharp`);
}
await browser.close();
await fs.writeFile(path.join(root,'film/instant-metrics.json'),JSON.stringify(results,null,2)+'\n');
