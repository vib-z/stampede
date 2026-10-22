// Build lossless vector frames for canvas; masters are rendered separately.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright-core');
const root=path.resolve(import.meta.dirname,'../..');
const browser=await chromium.launch({channel:'chrome',headless:true});
const metrics=[];
for(const cut of ['desktop','phone']) for(const theme of ['light','dark']) {
  const page=await browser.newPage({viewport:{width:cut==='phone'?1080:1920,height:cut==='phone'?1920:1080}});
  await page.goto(pathToFileURL(path.join(root,'film/index.html')).href+`?cut=${cut}&theme=${theme}`);
  await page.evaluate(()=>window.__ready);
  const check=await page.evaluate(()=>Motion.selfTest(Motion.last,{samples:24}));
  if(!check.ok)throw new Error(JSON.stringify(check));
  const data=await page.evaluate(()=>{
    const frames=[];
    for(let f=0;f<420;f++){window.__seek(f/30);frames.push(window.__lastParts.body);}
    return {...window.__lastParts,body:undefined,fps:30,frames};
  });
  data.materials=data.prefix.match(/<g id="raster-materials">[\s\S]*?<\/g>/)[0];
  data.prefix=data.prefix.replace(data.materials,'');
  const prefixes=[],prefixKeys=new Map();
  data.prefixForFrame=data.frames.map(body=>{
    const ids=[...new Set([...body.matchAll(/href="#([^"]+)"/g)].map(m=>m[1]))].sort();
    const key=ids.join(',');
    if(!prefixKeys.has(key)){
      const prefix=data.prefix.replace(/<path id="(word\d+)"[^>]*\/>/g,(all,id)=>ids.includes(id)?all:'')
        .replace(/<symbol id="([^"]+)"[\s\S]*?<\/symbol>/g,(all,id)=>ids.includes(id)?all:'');
      prefixKeys.set(key,prefixes.length);prefixes.push(prefix);
    }
    return prefixKeys.get(key);
  });
  data.prefixes=prefixes;delete data.prefix;
  // A small shared vocabulary and material sheet serve all eight beat chunks.
  // Each chunk has its own local vocabulary; loading one never needs another.
  const tags=svg=>(svg.match(/<[^>]+>|[^<]+/g)||[]).flatMap(tag=>tag.split(/(\s(?:opacity|transform)="[^"]+")/).filter(Boolean).flatMap(part=>part.startsWith(' transform=')?part.split(/(translate\(|\) rotate\(|\) scale\(|\)")/).filter(Boolean):[part]));
  const counts=new Map();for(const frame of data.frames)for(const tag of tags(frame))counts.set(tag,(counts.get(tag)||0)+1);
  const dictionary=[...counts].filter(([,count])=>count>=8).map(([tag])=>tag),lookup=new Map(dictionary.map((s,i)=>[s,i]));
  const starts=await page.evaluate(()=>window.__beatStarts),stills=[0,76,117,151,246,306,384,419];
  const union=[...new Set(data.prefixes.flatMap(p=>[...p.matchAll(/<(?:path|symbol)[^>]*id="([^"]+)"/g)].map(m=>m[1])))];
  // Reuse the authored full prefix once; remove unused definitions and opacity-zero branches.
  const prefix=await page.evaluate(()=>{window.__seek(0);return window.__lastParts.prefix;});
  const shared=prefix.replace(/<g id="raster-materials">[\s\S]*?<\/g>/,'').replace(/<path id="(word\d+)"[^>]*\/>/g,(s,id)=>union.includes(id)?s:'');
  const chunks=[];
  for(let beat=0;beat<8;beat++){
    const start=starts[beat],end=starts[beat+1]??420,local=[],localLookup=new Map();
    let frames=data.frames.slice(start,end).map(svg=>tags(svg).map(tag=>{
      if(lookup.has(tag))return lookup.get(tag);
      if(!localLookup.has(tag)){localLookup.set(tag,local.length);local.push(tag);}
      return -localLookup.get(tag)-1;
    }));
    // Repeated token pairs form a tiny acyclic grammar inside each chunk.
    // It expands to the exact SVG text, using ordinary JSON arrays and strings.
    for(let pass=0;pass<10;pass++){
      const counts=new Map();for(const frame of frames)for(let i=0;i<frame.length-1;i++){const key=frame[i]+','+frame[i+1];counts.set(key,(counts.get(key)||0)+1);}
      const pairs=new Map();
      frames=frames.map(frame=>{const packed=[];for(let i=0;i<frame.length;i++){
        const key=frame[i]+','+frame[i+1];
        if(i+1<frame.length&&counts.get(key)>=4){if(!pairs.has(key)){local.push([frame[i],frame[i+1]]);pairs.set(key,-local.length);}packed.push(pairs.get(key));i++;}else packed.push(frame[i]);
      }return packed;});
    }
    const decoded=new Map(),expand=i=>{if(i>=0)return dictionary[i];if(decoded.has(i))return decoded.get(i);const v=local[-i-1],s=Array.isArray(v)?v.map(expand).join(''):v;decoded.set(i,s);return s;};
    for(let i=0;i<frames.length;i++)if(frames[i].map(expand).join('')!==data.frames[start+i])throw new Error(`Lossless round trip failed at ${start+i}`);
    const name=`${cut}-${theme}-beat-${beat}.json`,bytes=Buffer.from(JSON.stringify({start,frames,dictionary:local}));
    await fs.writeFile(path.join(root,`site/assets/motion/${name}`),bytes);
    const stillName=`${cut}-${theme}-beat-${beat}.svg`;
    // The runtime adds the shared material and outlined-type definitions once.
    const still=`<svg xmlns="http://www.w3.org/2000/svg" width="${data.width}" height="${data.height}">${data.frames[stills[beat]]}</svg>`;
    await fs.writeFile(path.join(root,`site/assets/motion/${stillName}`),still);
    chunks.push({start,end,file:name,bytes:bytes.length,still:stillName,stillFrame:stills[beat],stillBytes:Buffer.byteLength(still)});
  }
  const wire={encoding:'svg-beats-v2',width:data.width,height:data.height,fps:30,prefix:shared,suffix:data.suffix,materials:data.materials,dictionary,chunks};
  const bytes=Buffer.from(JSON.stringify(wire));
  await fs.writeFile(path.join(root,`site/assets/motion/${cut}-${theme}.json`),bytes);
  for(const [label,f] of [['first',0],['poster',419]]) {
    const svg=await page.evaluate(({svg})=>{
      const doc=new DOMParser().parseFromString(svg,'image/svg+xml');
      for(const el of doc.querySelectorAll('[opacity="0"]'))el.remove();
      const used=new Set([...doc.querySelectorAll('use')].map(el=>el.getAttribute('href').slice(1)));
      for(const el of doc.querySelectorAll('[fill],[stroke]'))for(const name of ['fill','stroke']){const id=el.getAttribute(name)?.match(/^url\(#([^)]+)\)$/)?.[1];if(id)used.add(id);}
      for(const el of doc.querySelectorAll('defs [id]'))if(!used.has(el.id)&&!['raster-materials'].includes(el.id))el.remove();
      return new XMLSerializer().serializeToString(doc.documentElement);
    },{svg:data.prefixes[data.prefixForFrame[f]].replace('<defs>','<defs>'+data.materials)+data.frames[f]+data.suffix});
    await fs.writeFile(path.join(root,`site/assets/motion/${cut}-${theme}-${label}.svg`),svg);
  }
  metrics.push({cut,theme,frames:420,roundTripVerifiedFrames:420,bytes:bytes.length+chunks.reduce((n,c)=>n+c.bytes,0),sharedBytes:bytes.length,chunks,expandedBytes:JSON.stringify(data).length,seekCheck:check});
  console.log(`${cut} ${theme}: ${bytes.length} bytes, seek check ${check.ok}`);
  await page.close();
}
await fs.writeFile(path.join(root,'film/pack-metrics.json'),JSON.stringify(metrics,null,2));
await browser.close();
