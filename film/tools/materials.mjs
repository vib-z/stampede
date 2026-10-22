// Original deterministic raster surfaces. No model, remote image or texture input.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {chromium} from 'playwright-core';
const root=path.resolve(import.meta.dirname,'../..');
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage();
const materials=await page.evaluate(async()=>{
 const output={};
 for(const dark of [false,true]){
  const theme=dark?'dark':'light',items={};
  const stone=dark?['#484848','#242424','#0a0a0a']:['#fafafa','#d9d9d9','#b9b9b9'];
  const metal=dark?['#8a8a8a','#535353','#1f1f1f','#5c5c5c']:['#ffffff','#e5e5e5','#a3a3a3','#d4d4d4'];
  const make=(name,w,h,draw,resolution=2)=>{
   const c=document.createElement('canvas');c.width=w*resolution;c.height=h*resolution;const x=c.getContext('2d');x.scale(resolution,resolution);
   const gradient=(a,b,c,d,colors)=>{const g=x.createLinearGradient(a,b,c,d);colors.forEach((v,i)=>g.addColorStop(i/(colors.length-1),v));return g;};
   const rounded=(a,b,c,d,r,fill)=>{x.beginPath();x.roundRect(a,b,c,d,r);x.fillStyle=fill;x.fill();};
   const noise=(a,b,c,d,opacity=.035)=>{
    let seed=1987;x.save();x.beginPath();x.rect(a,b,c,d);x.clip();
    for(let i=0;i<c*d*.3;i++){seed=(1664525*seed+1013904223)>>>0;const px=a+(seed/4294967296)*c;seed=(1664525*seed+1013904223)>>>0;const py=b+(seed/4294967296)*d;x.fillStyle=i%2?`rgba(255,255,255,${opacity})`:`rgba(0,0,0,${opacity})`;x.fillRect(px,py,.6,.4);}x.restore();
   };
   draw(x,gradient,rounded,noise);
   items[name]={w,h,url:c.toDataURL('image/webp',name.startsWith('paper')?.86:.92)};
  };
  const drawPaper=(x,g,r,noise)=>{
   // A short, dense contact shadow sits inside the wider cast shadow.
   for(const [blur,dx,dy,alpha] of [[22,9,17,.22],[5,3,9,.33]]){
    x.save();x.shadowColor=`rgba(0,0,0,${alpha})`;x.shadowBlur=blur;x.shadowOffsetX=dx;x.shadowOffsetY=dy;
    r(18,12,860,690,11,dark?'#171717':'#d7d7d7');x.restore();
   }
   // Three cut edges make thickness visible, including at the phone scale.
   r(18,22,860,690,11,g(0,0,900,740,dark?['#6b6b6b','#1f1f1f']:['#fafafa','#a3a3a3']));
   r(18,18,860,690,11,dark?'#8a8a8a':'#ffffff');
   r(18,16,860,690,11,dark?'#3d3d3d':'#bcbcbc');
   r(18,12,860,690,11,g(25,20,850,700,dark?['#333333','#1f1f1f','#0a0a0a']:['#ffffff','#f2f2f2','#e5e5e5']));
   x.save();x.beginPath();x.roundRect(18,12,860,690,11);x.clip();
   const light=x.createRadialGradient(210,90,8,360,200,600);light.addColorStop(0,dark?'#ffffff25':'#ffffffa0');light.addColorStop(1,'#ffffff00');x.fillStyle=light;x.fillRect(18,12,860,690);
   noise(18,12,860,690,.025);x.restore();
   x.strokeStyle=g(0,0,820,700,[dark?'#d2d2d2b0':'#ffffff',dark?'#737373':'#c8c8c8']);x.lineWidth=2;x.beginPath();x.roundRect(19,13,858,688,10);x.stroke();
   x.strokeStyle=dark?'#111111':'#8a8a8a';x.lineWidth=1.8;x.beginPath();x.moveTo(31,712);x.lineTo(863,712);x.stroke();
  };
  make('paper',900,740,drawPaper);
  make('paper-phone',900,740,drawPaper,1);
  make('agent',146,172,(x,g,r,noise)=>{
   x.save();x.shadowColor=dark?'#000a':'#00000050';x.shadowBlur=5;x.shadowOffsetY=4;
   r(7,6,132,156,25,g(0,0,135,170,metal));x.restore();
   r(12,10,122,145,21,g(10,10,140,170,[stone[0],stone[1],stone[2]]));
   r(17,14,112,136,18,g(0,0,100,180,dark?['#484848','#242424']:['#ffffff','#eeeeee']));
   x.save();x.beginPath();x.roundRect(17,14,112,136,18);x.clip();noise(17,14,112,136,.018);x.restore();
   x.lineWidth=1;x.strokeStyle=dark?'#d4d4d466':'#fff';x.beginPath();x.roundRect(12,10,122,145,21);x.stroke();
  });
  output[theme]=items;
 }
 // Keep the existing material quality/weight tradeoff, then remove codec chroma.
 // The final lossless file preserves these neutral pixels without adding it back.
 for(const items of Object.values(output))for(const m of Object.values(items)){
  const image=new Image();image.src=m.url;await image.decode();const c=document.createElement('canvas');c.width=image.naturalWidth;c.height=image.naturalHeight;
  const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(image,0,0);const pixels=x.getImageData(0,0,c.width,c.height);
  for(let p=0;p<pixels.data.length;p+=4){const grey=Math.round((pixels.data[p]+pixels.data[p+1]+pixels.data[p+2])/3);pixels.data[p]=pixels.data[p+1]=pixels.data[p+2]=grey;}
  x.putImageData(pixels,0,0);m.url=c.toDataURL('image/png');
 }
 return output;
});
await browser.close();
// Lossy WebP introduces chroma into neutral pixels. Lossless keeps R = G = B.
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'film-mono-materials-'));
try{
 for(const [theme,items] of Object.entries(materials))for(const [name,m] of Object.entries(items)){
  const input=path.join(temp,`${theme}-${name}.png`),output=path.join(temp,`${theme}-${name}.webp`);
  await fs.writeFile(input,Buffer.from(m.url.split(',')[1],'base64'));
  execFileSync('cwebp',['-quiet','-lossless','-exact','-m','6',input,'-o',output]);
  m.url='data:image/webp;base64,'+(await fs.readFile(output)).toString('base64');
 }
}finally{await fs.rm(temp,{recursive:true,force:true});}
await fs.writeFile(path.join(root,'film/brand/materials.js'),'window.MATERIALS = '+JSON.stringify(materials)+';\n');
console.log(Object.fromEntries(Object.entries(materials).map(([k,v])=>[k,Object.fromEntries(Object.entries(v).map(([name,m])=>[name,Math.round(m.url.length*.75)]))])));
