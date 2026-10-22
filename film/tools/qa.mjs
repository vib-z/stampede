import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const {chromium}=require('playwright-core');
const root=path.resolve(import.meta.dirname,'../..');
const dest=path.join(root,'film/renders/screenshots');
await fs.mkdir(dest,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
const beats=['ask','lead','team','cross','work','return','reply','closed'];
for(const width of [390,1440])for(const theme of ['light','dark']) {
 const height=width===390?844:900;
 const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:2,colorScheme:theme});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8855/site/');
 await page.waitForFunction(()=>window.__filmStats?.frame===0&&window.__filmStats.quality==='full');
 await page.waitForFunction(()=>window.__filmStats.cacheSize===420);
 await page.screenshot({path:path.join(dest,`${width}-${theme}-first.jpg`),type:'jpeg',quality:92});
 for(const name of beats) {
  const phoneFrames={ask:12,lead:70,team:117,cross:151,work:246,return:336,reply:384,closed:419};
  const target=phoneFrames[name];
  await page.evaluate(f=>scrollTo(0,(document.querySelector('.film-section').offsetHeight-innerHeight)*f/419),target);
  await page.waitForFunction(f=>window.__filmStats.frame===f&&window.__filmStats.quality==='full',target);
  await page.screenshot({path:path.join(dest,`${width}-${theme}-${name}.jpg`),type:'jpeg',quality:92});
 }
 const cdp=await page.context().newCDPSession(page);
 await cdp.send('Emulation.setCPUThrottlingRate',{rate:width===390?4:1});
 await page.evaluate(()=>scrollTo(0,0));
 await page.waitForFunction(()=>window.__filmStats.frame===0&&window.__filmStats.quality==='full');
 await page.evaluate(()=>{window.__filmStats.samples.length=0;window.__filmStats.latencies.length=0;window.__filmStats.distances.length=0;});
 // Stress scroll at 30 updates/s: three poses forward, seven poses backward.
 await page.evaluate(async()=>{
  const max=document.querySelector('.film-section').offsetHeight-innerHeight;
  for(let f=0;f<=419;f+=3){scrollTo(0,max*f/419);await new Promise(r=>setTimeout(r,33));}
  for(let f=419;f>=0;f-=7){scrollTo(0,max*f/419);await new Promise(r=>setTimeout(r,33));}
  scrollTo(0,0);
 });
 await page.waitForFunction(()=>window.__filmStats.frame===0&&window.__filmStats.quality==='full');
 const metrics=await page.evaluate(()=>{
  const s=window.__filmStats;
  const summarize=a=>{a=[...a].sort((a,b)=>a-b);return{samples:a.length,median:a[Math.floor(a.length*.5)],p95:a[Math.floor(a.length*.95)],max:Math.max(...a)};};
  return{drawMs:summarize(s.samples),readySelectionAndDrawMs:summarize(s.latencies),backgroundPreparationMs:summarize(s.preparation),readyDistanceFrames:summarize(s.distances),cachePeak:s.peakCache,decodedMemory:s.memory,instantDraws:s.instantDraws,fullDraws:s.fullDraws,readyAt:s.readyAt,draws:s.draws,noReadyCallbacks:s.misses,canvas:s.size,overflow:document.documentElement.scrollWidth>innerWidth,paint:performance.getEntriesByType('paint').map(p=>({name:p.name,t:p.startTime})),sequence:performance.getEntriesByType('resource').filter(r=>/\.(json|webp)$/.test(r.name)).map(r=>({start:r.startTime,bytes:r.transferSize,duration:r.duration}))};
 });
 if(width===390&&metrics.readySelectionAndDrawMs.p95>=16.7)throw new Error('Phone paint path exceeds 16.7 ms');
 if(metrics.readyDistanceFrames.p95>0)throw new Error('Pose distance exceeds two frames');
 if(metrics.readyDistanceFrames.max>0)throw new Error('Instant tier exceeded two frames');
 if(metrics.instantDraws!==0)throw new Error('A soft frame was used');
 if(metrics.cachePeak!==420)throw new Error('All poses must compile in the background');
 const geometry=await page.locator('canvas').boundingBox();if(geometry.width!==width||geometry.height!==height)throw new Error('Film is not full viewport');
 if(await page.locator('.beat').count())throw new Error('External beat chrome remains');
 if(await page.evaluate(()=>performance.getEntriesByType('resource').some(r=>r.name.endsWith('-poster.svg'))))throw new Error('Hidden finished poster fetched');
 if(errors.length||metrics.overflow)throw new Error(JSON.stringify({errors,metrics}));
 if(metrics.sequence[0].start<metrics.paint[0].t)throw new Error('Film fetched before paint');
 const result={width,height,theme,cpu:width===390?4:1,errors,...metrics};
 results.push(result);
 await cdp.send('Emulation.setCPUThrottlingRate',{rate:1});
 await page.evaluate(()=>scrollTo(0,document.querySelector('.film-section').offsetHeight-innerHeight+220));
 await page.waitForFunction(()=>window.__filmStats.frame===419&&window.__filmStats.quality==='full');
 await page.screenshot({path:path.join(dest,`${width}-${theme}-unpin.jpg`),type:'jpeg',quality:92});
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.waitForFunction(()=>!document.documentElement.classList.contains('motion-enabled'));
 await page.evaluate(()=>scrollTo(0,0));
 await page.screenshot({path:path.join(dest,`${width}-${theme}-reduced.jpg`),type:'jpeg',quality:92});
 await page.close();
 const staticPage=await browser.newPage({viewport:{width,height},deviceScaleFactor:2,colorScheme:theme,javaScriptEnabled:false});
 let noJsRequests=0;staticPage.on('request',r=>{if(/\.(json|webp)$/.test(r.url()))noJsRequests++;});
 await staticPage.goto('http://127.0.0.1:8855/site/');
 await staticPage.screenshot({path:path.join(dest,`${width}-${theme}-nojs.jpg`),type:'jpeg',quality:92});
 await staticPage.close();
 result.noJsFrameRequests=noJsRequests;
 const reducedPage=await browser.newPage({viewport:{width,height},colorScheme:theme,reducedMotion:'reduce'});
 let reducedRequests=0;reducedPage.on('request',r=>{if(/\.(json|webp)$/.test(r.url()))reducedRequests++;});
 await reducedPage.goto('http://127.0.0.1:8855/site/');await reducedPage.waitForTimeout(300);
 result.reducedInitialFrameRequests=reducedRequests;
 if(noJsRequests||reducedRequests)throw new Error('Static fallback requested film');
 await reducedPage.close();
 console.log(`${width} ${theme} checked`);
}
await fs.writeFile(path.join(root,'film/browser-metrics.json'),JSON.stringify(results,null,2));
await browser.close();
