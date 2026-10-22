// Check whether each requested 30 fps pose is ready before the following step.
import fs from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright-core';

const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
for(const width of [390,1440])for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width,height:width===390?844:900},deviceScaleFactor:2,colorScheme:theme});
  await page.goto('http://127.0.0.1:8855/site/');
  await page.waitForFunction(()=>window.__filmStats?.frame===0);
  await page.waitForFunction(()=>window.__filmStats?.cacheSize===420);
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:width===390?4:1});
  const result=await page.evaluate(async()=>{
    const s=window.__filmStats;
    s.samples.length=0;s.latencies.length=0;
    const startMisses=s.misses,late=[],intervals=[];
    const travel=document.querySelector('.film-section').offsetHeight-innerHeight;
    for(let frame=1;frame<420;frame++) {
      if(s.frame!==frame-1)late.push({requested:frame-1,delivered:s.target,displayed:s.frame});
      const start=performance.now();
      scrollTo(0,travel*frame/419);
      await new Promise(resolve=>setTimeout(resolve,1000/30));
      intervals.push(performance.now()-start);
    }
    if(s.frame!==419)late.push({requested:419,delivered:s.target,displayed:s.frame});
    const summarize=values=>{values=[...values].sort((a,b)=>a-b);return{samples:values.length,median:values[Math.floor(values.length*.5)],p95:values[Math.floor(values.length*.95)],max:Math.max(...values)};};
    return{requestedPoses:420,lateAtNextStep:late,inputDeliveryLate:late.filter(v=>v.delivered!==v.requested).length,playerBehindDelivered:late.filter(v=>v.displayed!==v.delivered).length,noReadyCallbacks:s.misses-startMisses,drawMs:summarize(s.samples),readySelectionAndDrawMs:summarize(s.latencies),stepIntervalMs:summarize(intervals)};
  });
  results.push({width,theme,cpu:width===390?4:1,...result});
  console.log(`${width} ${theme}: ${result.lateAtNextStep.length} late poses`);
  await page.close();
}
const controls=[];
for(const width of [390,1440]) {
  const page=await browser.newPage({viewport:{width,height:width===390?844:900},deviceScaleFactor:2});
  await page.setContent('<style>body{height:6000px}div{position:sticky;top:0;height:100vh}</style><div>Plain scroll timing control</div>');
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:width===390?4:1});
  const control=await page.evaluate(async()=>{
    let events=0,frames=0,active=true;const start=performance.now();
    addEventListener('scroll',()=>events++);
    function tick(){frames++;if(active)requestAnimationFrame(tick);}requestAnimationFrame(tick);
    for(let i=1;i<=60;i++){scrollTo(0,i*10);await new Promise(resolve=>setTimeout(resolve,1000/30));}
    active=false;return{requests:60,scrollEvents:events,animationCallbacks:frames,durationMs:performance.now()-start};
  });
  controls.push({width,cpu:width===390?4:1,...control});await page.close();
}
await fs.writeFile(path.resolve(import.meta.dirname,'../pace-metrics.json'),JSON.stringify(results,null,2)+'\n');
await fs.writeFile(path.resolve(import.meta.dirname,'../pace-control.json'),JSON.stringify(controls,null,2)+'\n');
await browser.close();
