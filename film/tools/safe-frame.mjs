import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {chromium} from 'playwright-core';

const root=path.resolve(import.meta.dirname,'../..');
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
for(const cut of ['desktop','phone'])for(const theme of ['light','dark']){
  const width=cut==='phone'?1080:1920,height=cut==='phone'?1920:1080;
  const page=await browser.newPage({viewport:{width,height}});
  await page.goto(pathToFileURL(path.join(root,'film/index.html')).href+`?cut=${cut}&theme=${theme}`);
  await page.evaluate(()=>window.__ready);
  const result=await page.evaluate(({width,height})=>{
    let minimum=1,worst=null,checked=0,minAgentBodyCss=Infinity;const violations=[];
    for(let frame=0;frame<420;frame++){
      window.__seek(frame/30);
      const svg=document.querySelector('#main svg');
      for(const element of svg.querySelectorAll('[data-safe],[data-exiting]')){
        let visible=true;
        for(let parent=element;parent&&parent!==svg;parent=parent.parentElement){
          if(Number(parent.getAttribute('opacity')??1)===0)visible=false;
        }
        if(!visible)continue;
        const b=element.getBBox(),m=element.getCTM();
        // Two authored units cover strokes; diffuse shadows may extend farther.
        const points=[[b.x-2,b.y-2],[b.x+b.width+2,b.y-2],[b.x-2,b.y+b.height+2],[b.x+b.width+2,b.y+b.height+2]]
          .map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));
        const bounds={left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),top:Math.min(...points.map(p=>p.y)),bottom:Math.max(...points.map(p=>p.y))};
        const vh=width<height?844:900,vw=width<height?390:1440,scale=Math.max(vw/width,vh/height),visibleW=vw/scale,visibleH=vh/scale,ox=(width-visibleW)/2,oy=(height-visibleH)/2;
        if(element.dataset.safe?.startsWith('agent-'))minAgentBodyCss=Math.min(minAgentBodyCss,132*Math.hypot(m.a,m.b)*scale);
        const margin=Math.min((bounds.left-ox)/visibleW,1-(bounds.right-ox)/visibleW,(bounds.top-oy)/visibleH,1-(bounds.bottom-oy)/visibleH);
        const evidence={frame,subject:element.dataset.safe??element.dataset.exiting,margin,...bounds};checked++;
        if(margin<minimum){minimum=margin;worst=evidence;}
        if(margin<.06)violations.push(evidence);
      }
    }
    return{frames:420,checked,minAgentBodyCss,minimumMarginPercent:minimum*100,worst,violations};
  },{width,height});
  results.push({cut,theme,...result});await page.close();
}
await browser.close();
await fs.writeFile(path.join(root,'film/safe-frame-metrics.json'),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results.map(({violations,...r})=>({...r,violations:violations.length,first:violations.slice(0,3)})),null,2));
if(results.some(r=>r.violations.length||(r.cut==='phone'&&r.minAgentBodyCss<44)))process.exitCode=1;
