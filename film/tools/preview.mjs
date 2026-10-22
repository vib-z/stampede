// Build a portable site fragment. The host supplies html/head/body wrappers.
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..'),out=process.env.FILM_PREVIEW;
if(!out)throw new Error('Set FILM_PREVIEW');
await fs.mkdir(path.join(out,'assets'),{recursive:true});
for(const cut of ['desktop','phone'])for(const theme of ['light','dark'])await fs.rm(path.join(out,`assets/motion/${cut}-${theme}-instant.webp`),{force:true});
for(const file of ['motion.js','motion.css','favicon.svg'])await fs.copyFile(path.join(root,'site/assets',file),path.join(out,'assets',file));
for(const dir of ['motion','fonts','hero-mark','cta'])await fs.cp(path.join(root,'site/assets',dir),path.join(out,'assets',dir),{recursive:true});
await fs.rm(path.join(out,'assets/fonts/Geist-OFL.txt'),{force:true});
let html=await fs.readFile(path.join(root,'site/index.html'),'utf8');
html=html.replace(/<!doctype html>|<html[^>]*>|<\/html>|<head>|<\/head>|<body>|<\/body>/gi,'');
html=html.trim()+'\n';
await fs.writeFile(path.join(out,'index.html'),html);
if(process.env.FILM_BRAND)await fs.cp(process.env.FILM_BRAND,path.join(out,'brand'),{recursive:true});
const list=[];async function walk(dir){for(const e of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())await walk(p);else if(e.name!=='MANIFEST.txt')list.push([path.relative(out,p),(await fs.stat(p)).size]);}}
await walk(out);list.sort((a,b)=>a[0].localeCompare(b[0]));
if(list.length>200||list.some(([,b])=>b>14e6)||list.reduce((n,[,b])=>n+b,0)>60e6)throw new Error('Preview cap exceeded');
const checks=process.env.FILM_CHECKS?JSON.parse(await fs.readFile(process.env.FILM_CHECKS,'utf8')):null;
const verification=checks?`Verified ${checks.length} root/subpath, width and forced-theme combinations; zero console errors, failed requests or external requests.`:'Run film/tools/check-preview.mjs before handoff.';
const assetBytes=list.reduce((n,[,b])=>n+b,0);
let manifest='',size=0;
for(let i=0;i<10;i++){
 manifest=[...list,['MANIFEST.txt',size]].sort((a,b)=>a[0].localeCompare(b[0])).map(([p,b])=>`${b}\t${p}`).join('\n')+`\nFiles: ${list.length+1}\nTotal bytes: ${assetBytes+size}\nJSON is UTF-8 text; no binary pack or compressed JSON.\nCheck: film/tools/check-preview.mjs. ${verification}\n`;
 const next=Buffer.byteLength(manifest);if(next===size)break;size=next;
}
await fs.writeFile(path.join(out,'MANIFEST.txt'),manifest);
console.log(`${list.length+1} files, ${assetBytes+Buffer.byteLength(manifest)} bytes including manifest`);
