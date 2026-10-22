/* Compile the authored SVG scene into reusable Canvas paths after first paint.
Text stays vector-sharp during a swipe; shared material images decode once. */
(() => {
const html=document.documentElement,region=document.querySelector('.film-section'),figure=document.querySelector('.film');
const canvas=figure.querySelector('canvas'),ctx=canvas.getContext('2d',{alpha:false}),poster=figure.querySelector('.opening');
const reduce=matchMedia('(prefers-reduced-motion: reduce)'),mobile=matchMedia('(max-width:700px)'),dark=matchMedia('(prefers-color-scheme:dark)');
const theme=()=>html.dataset.theme==='dark'||html.dataset.theme!=='light'&&dark.matches?'dark':'light';
let run=0,abort=null,pack=null,frames=[],background=null,rasters=[],current=-1,desired=0,variant='',readyAt=0,draws=0,misses=0,lastDrawAt=0,lastInputAt=0,positionTimer=0,lastPosition=0,lastMovementAt=0,compiled=0,quality='',compileFrame=null,chunks=[],stillFrames=new Map(),pendingStills=new Map(),firstResponseAt=0;
let swapping=false;
const times=[],latencies=[],distances=[],preparation=[];
const record=(list,value)=>{list.push(value);if(list.length>900)list.shift();};
window.__filmStats={get samples(){return times},get latencies(){return latencies},get distances(){return distances},get preparation(){return preparation},get misses(){return misses},get draws(){return draws},get frame(){return current},get target(){return desired},get ready(){return readyAt>0},get variant(){return variant},get reduced(){return reduce.matches},get size(){return[canvas.width,canvas.height]},get cacheSize(){return compiled},get peakCache(){return compiled},get quality(){return quality},get instantDraws(){return 0},get fullDraws(){return draws},get memory(){const bytes=rasters.reduce((n,i)=>n+i.naturalWidth*i.naturalHeight*4,0);return{decodedBytes:bytes,reservedBytes:bytes,peakDecodedBytes:bytes,peakReservedBytes:bytes,compiledFrames:compiled}},get readyAt(){return readyAt},get firstResponseAt(){return firstResponseAt},get loadedBeats(){return chunks.filter(c=>c.done).length},get lastDrawAt(){return lastDrawAt},get lastInputAt(){return lastInputAt},get positionWatchActive(){return positionTimer!==0}};
function resize(){const r=figure.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);const w=Math.round(r.width*d),h=Math.round(r.height*d);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;current=-1;}update();}
function update(){if(reduce.matches){load();return;}lastInputAt=performance.now();const travel=region.offsetHeight-innerHeight;desired=Math.round(Math.min(1,Math.max(0,-region.getBoundingClientRect().top/travel))*419);html.style.setProperty('--film-chrome',Math.min(1,Math.max(0,(desired-54)/24)));draw();}
function draw(){
if(!pack||reduce.matches)return;
const exact=frames[desired],beat=pack.chunks.findLastIndex(c=>desired>=c.start),fallback=stillFrames.get(beat),fn=exact||fallback;
if(!exact){requestChunk(beat);if(!chunks[beat].stillTimer){const token=run;chunks[beat].stillTimer=setTimeout(()=>{if(token!==run)return;chunks[beat].stillTimer=0;if(!frames[desired]&&pack.chunks.findLastIndex(c=>desired>=c.start)===beat)requestStill(beat);},80);}}
if(!fn||swapping&&!exact)return;
const pose=exact?desired:pack.chunks[beat].stillFrame,nextQuality=exact?'full':'beat';
const start=performance.now();if(current!==pose||quality!==nextQuality){
const scale=Math.max(canvas.width/pack.width,canvas.height/pack.height);ctx.setTransform(scale,0,0,scale,(canvas.width-pack.width*scale)/2,(canvas.height-pack.height*scale)/2);
background(ctx);fn(ctx);swapping=false;current=pose;quality=nextQuality;lastDrawAt=performance.now();if(!firstResponseAt)firstResponseAt=lastDrawAt;
if(exact){draws++;if(!readyAt)readyAt=lastDrawAt;}figure.classList.add('ready');record(times,performance.now()-start);
}
record(latencies,performance.now()-start);if(exact)record(distances,0);
}
async function requestStill(beat){
if(!pack||stillFrames.has(beat)||pendingStills.has(beat))return;
const token=run,promise=fetch(`assets/motion/${pack.chunks[beat].still}`,{signal:abort.signal}).then(r=>{if(!r.ok)throw new Error('Missing beat still');return r.text();}).then(svg=>{if(token!==run)return;if(reduce.matches){load();return;}stillFrames.set(beat,compileFrame(parse(svg)));draw();}).catch(()=>{});
pendingStills.set(beat,promise);
}
async function requestChunk(beat){
const chunk=chunks[beat];if(!chunk||chunk.pending||chunk.done)return;
chunk.pending=true;const token=run;
try{
const response=await fetch(`assets/motion/${chunk.file}`,{signal:abort.signal});if(!response.ok)throw new Error('Missing beat');const data=await response.json();
if(token!==run)return;if(reduce.matches){load();return;}
const expand=i=>{if(i>=0)return pack.dictionary[i];const j=-i-1,v=data.dictionary[j];return Array.isArray(v)?(data.dictionary[j]=v.map(expand).join('')):v;};
const todo=new Set(data.frames.map((_,i)=>chunk.start+i));let budget=performance.now();
while(todo.size){
const f=[...todo].reduce((a,b)=>Math.abs(a-desired)<=Math.abs(b-desired)?a:b);todo.delete(f);
const svg=data.frames[f-chunk.start].map(expand).join(''),start=performance.now();
frames[f]=compileFrame(parse(`<svg xmlns="http://www.w3.org/2000/svg">${svg}</svg>`));compiled++;record(preparation,performance.now()-start);
if(f===desired)draw();
if(performance.now()-budget>4){await new Promise(r=>setTimeout(r,0));budget=performance.now();if(token!==run)return;if(reduce.matches){load();return;}}
}
chunk.done=true;draw();
}catch(error){if(token===run&&pack.chunks.findLastIndex(c=>desired>=c.start)===beat&&!frames[desired])requestStill(beat);}
}
const parse=svg=>new DOMParser().parseFromString(svg,'image/svg+xml').documentElement;
function compiler(defs,images,color){
const paths=new Map(),resolved=new Map();
const numbers=s=>(s||'').match(/[-+]?(?:\d*\.)?\d+(?:e[-+]?\d+)?/gi)?.map(Number)||[];
function transform(value){const m=new DOMMatrix();for(const match of (value||'').matchAll(/(\w+)\(([^)]+)\)/g)){const a=numbers(match[2]);if(match[1]==='translate')m.translateSelf(a[0],a[1]||0);if(match[1]==='scale')m.scaleSelf(a[0],a[1]??a[0]);if(match[1]==='rotate'){if(a.length>1)m.translateSelf(a[1],a[2]);m.rotateSelf(a[0]);if(a.length>1)m.translateSelf(-a[1],-a[2]);}if(match[1]==='matrix')m.multiplySelf(new DOMMatrix(a));}return m;}
function paint(value,c,bounds){if(value==='currentColor')return color;if(!value?.startsWith('url('))return value;const id=value.slice(5,-1),el=defs.get(id);if(!el)return color;const user=el.getAttribute('gradientUnits')==='userSpaceOnUse';const [x,y,w,h]=user?[0,0,1,1]:bounds;const at=(key,axis,fallback)=>{const v=el.getAttribute(key)??fallback;return (axis?y:x)+(parseFloat(v)/(v.includes('%')?100:1))*(axis?h:w);};let g;if(el.localName==='radialGradient')g=c.createRadialGradient(at('cx',0,'50%'),at('cy',1,'50%'),0,at('cx',0,'50%'),at('cy',1,'50%'),user?parseFloat(el.getAttribute('r')):parseFloat(el.getAttribute('r')||'50')/100*Math.max(w,h));else g=c.createLinearGradient(at('x1',0,'0'),at('y1',1,'0'),at('x2',0,'100%'),at('y2',1,'0'));for(const stop of el.children){let off=stop.getAttribute('offset')||'0';let v=parseFloat(off)/(off.includes('%')?100:1);const col=stop.getAttribute('stop-color')||color,alpha=stop.getAttribute('stop-opacity');g.addColorStop(v,alpha===null?col:col+Math.round(Number(alpha)*255).toString(16).padStart(2,'0'));}return g;}
function resolve(id){if(!resolved.has(id)){const el=defs.get(id);resolved.set(id,el?compile(el):()=>{});}return resolved.get(id);}
function compile(el){
const tag=el.localName,a=Object.fromEntries([...el.attributes].map(a=>[a.name,a.value]));
const num=(k,d=0)=>Number(a[k]??d),matrix=transform(a.transform);let render;
if(tag==='use'){
const id=a.href?.slice(1),target=defs.get(id),fn=resolve(id);let m=new DOMMatrix().translate(num('x'),num('y'));
if(target?.localName==='symbol'){const box=numbers(target.getAttribute('viewBox'));m.scaleSelf(num('width')/box[2],num('height')/box[3]).translateSelf(-box[0],-box[1]);}
render=c=>{c.transform(m.a,m.b,m.c,m.d,m.e,m.f);fn(c);};
}else if(tag==='image'){const im=images.get(a.id);render=c=>{if(im)c.drawImage(im,num('x'),num('y'),num('width'),num('height'));};}
else if(['path','rect','circle','ellipse'].includes(tag)){
let path,bounds=[0,0,1,1];
if(tag==='path'){if(!paths.has(a.d))paths.set(a.d,new Path2D(a.d));path=paths.get(a.d);}
else {path=new Path2D();if(tag==='rect'){bounds=[num('x'),num('y'),num('width'),num('height')];path.roundRect(...bounds,num('rx'));}else{const rx=num(tag==='circle'?'r':'rx'),ry=num(tag==='circle'?'r':'ry');bounds=[num('cx')-rx,num('cy')-ry,rx*2,ry*2];path.ellipse(num('cx'),num('cy'),rx,ry,0,0,Math.PI*2);}}
const fillRule=a['fill-rule']||el.parentElement?.closest('[fill-rule]')?.getAttribute('fill-rule')||'nonzero';
render=c=>{if(a.fill!==undefined)c.fillStyle=paint(a.fill,c,bounds)||color;if(a.stroke!==undefined)c.strokeStyle=paint(a.stroke,c,bounds)||color;if(a['stroke-width'])c.lineWidth=num('stroke-width');if(a['stroke-linecap'])c.lineCap=a['stroke-linecap'];if(a['stroke-linejoin'])c.lineJoin=a['stroke-linejoin'];if(a.fill!=='none'){const old=c.globalAlpha;c.globalAlpha*=num('fill-opacity',1);c.fill(path,fillRule);c.globalAlpha=old;}if(a.stroke&&a.stroke!=='none')c.stroke(path);};
}else if(['defs','linearGradient','radialGradient','filter'].includes(tag))render=()=>{};
else {const children=[...el.children].filter(e=>e.localName!=='defs').map(compile);render=c=>{for(const fn of children)fn(c);};}
return c=>{if(num('opacity',1)===0)return;c.save();c.transform(matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f);c.globalAlpha*=num('opacity',1);if(a.fill&&a.fill!=='none'&&!a.fill.startsWith('url('))c.fillStyle=a.fill==='currentColor'?color:a.fill;render(c);c.restore();};
}
return compile;
}
function watchPosition(){
positionTimer=0;if(reduce.matches){load();return;}
const now=performance.now();if(scrollY!==lastPosition){lastPosition=scrollY;lastMovementAt=now;update();}
if(now-lastMovementAt<240)positionTimer=setTimeout(watchPosition,4);
}
function onScroll(){lastMovementAt=performance.now();lastPosition=scrollY;update();if(!positionTimer&&!reduce.matches)positionTimer=setTimeout(watchPosition,4);}
async function load(){
swapping=figure.classList.contains('ready')&&!reduce.matches;
const token=++run;clearTimeout(positionTimer);positionTimer=0;abort?.abort();abort=new AbortController();pack=null;frames=[];background=null;rasters=[];variant='';current=-1;compiled=0;quality='';readyAt=0;firstResponseAt=0;chunks=[];stillFrames=new Map();pendingStills=new Map();if(!swapping)figure.classList.remove('ready');
const selected=`${mobile.matches?'phone':'desktop'}-${theme()}`,still=reduce.matches||!ctx;
poster.src=`assets/motion/${selected}-${still?'poster':'first'}.svg`;
html.classList.toggle('motion-enabled',!still);if(still){canvas.width=1;canvas.height=1;html.style.setProperty('--film-chrome',1);return;}
resize();
try{
const response=await fetch(`assets/motion/${selected}.json`,{signal:abort.signal});if(!response.ok)throw new Error('Missing sequence');const data=await response.json();if(token!==run)return;
const defs=new Map(),images=new Map(),doc=parse(data.prefix+data.suffix);for(const el of doc.querySelectorAll('[id]'))defs.set(el.id,el);
const material=parse(`<svg xmlns="http://www.w3.org/2000/svg">${data.materials}</svg>`);
await Promise.all([...material.querySelectorAll('image')].map(async el=>{const im=new Image();im.src=el.getAttribute('href');await im.decode();images.set(el.id,im);defs.set(el.id,el);}));
if(token!==run)return;if(reduce.matches){load();return;}
compileFrame=compiler(defs,images,selected.endsWith('dark')?'#ffffff':'#000000');background=compileFrame(doc);pack=data;chunks=data.chunks.map(c=>({...c}));rasters=[...images.values()];variant=selected;
update();const first=data.chunks.findLastIndex(c=>desired>=c.start);await requestChunk(first);
for(let distance=1;distance<8;distance++){
if(token!==run)return;if(reduce.matches){load();return;}
await Promise.all([first+distance,first-distance].filter(i=>i>=0&&i<8).map(requestChunk));
}
}catch(error){if(token===run){swapping=false;figure.classList.remove('ready');html.classList.remove('motion-enabled');poster.src=`assets/motion/${selected}-poster.svg`;html.style.setProperty('--film-chrome',1);}}
}
addEventListener('scroll',onScroll,{passive:true});addEventListener('resize',resize,{passive:true});for(const mq of [reduce,mobile])mq.addEventListener('change',load);new MutationObserver(load).observe(html,{attributes:true,attributeFilter:['data-theme']});
let started=false;const start=()=>{if(!started){started=true;setTimeout(load,0);}};
if(performance.getEntriesByName('first-contentful-paint').length)start();else if(window.PerformanceObserver?.supportedEntryTypes.includes('paint')){const observer=new PerformanceObserver(entries=>{if(entries.getEntries().some(e=>e.name==='first-contentful-paint')){observer.disconnect();start();}});observer.observe({type:'paint',buffered:true});}else requestAnimationFrame(()=>requestAnimationFrame(start));
})();
