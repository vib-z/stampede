import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
const require=createRequire(import.meta.url);const {chromium}=require('playwright-core');
const out=process.env.FILM_MEDIA;if(!out)throw new Error('Set FILM_MEDIA');
const browser=await chromium.launch({channel:'chrome',headless:true});
for(const width of [390,1440]) {
 const height=width===390?844:900;
 const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1,colorScheme:'light'});
 await page.goto('http://127.0.0.1:8855/site/');await page.waitForFunction(()=>window.__filmStats?.frame===0);
 const dir=await fs.mkdtemp(path.join(out,`scroll-${width}-frames-`));
 const cdp=await page.context().newCDPSession(page);
 let count=0;const writes=[];
 cdp.on('Page.screencastFrame',event=>{
  writes.push(fs.writeFile(path.join(dir,`${String(count++).padStart(5,'0')}.jpg`),Buffer.from(event.data,'base64')));
  cdp.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
 });
 await cdp.send('Page.startScreencast',{format:'jpeg',quality:82,maxWidth:width,maxHeight:height,everyNthFrame:1});
 await page.evaluate(async()=>{
  const max=document.documentElement.scrollHeight-innerHeight;
  const start=performance.now();
  await new Promise(resolve=>{function tick(now){const p=Math.min(1,(now-start)/14500);scrollTo(0,max*p);if(p<1)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});
 });
 await page.waitForTimeout(500);await cdp.send('Page.stopScreencast');await Promise.all(writes);
 const rate=count/15;
 await new Promise((resolve,reject)=>{
  const p=spawn('ffmpeg',['-hide_banner','-loglevel','error','-y','-framerate',String(rate),'-i',path.join(dir,'%05d.jpg'),'-c:v','libvpx-vp9','-crf','37','-b:v','0','-pix_fmt','yuv420p',path.join(out,`full-scroll-${width}.webm`)]);
  p.on('close',code=>code?reject(new Error(`ffmpeg ${code}`)):resolve());
 });
 console.log(`${width}: ${count} captured frames`);await fs.rm(dir,{recursive:true});await page.close();
}
await browser.close();
