// Run after compose.py and guide.py. Requires playwright-core and Chrome.
const {chromium}=require('playwright-core');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({deviceScaleFactor:1,colorScheme:'light',reducedMotion:'reduce'});
 for(const size of [16,32,180,192,512]){
  await page.setViewportSize({width:size,height:size});
  const isSmall=size<=32;
  const svg=fs.readFileSync(path.join(root,isSmall?'src/favicon-dark.svg':'mark-dark.svg'),'utf8');
  const inset=isSmall?Math.round(size*.125):Math.round(size*.16);
  await page.setContent(`<style>html,body{margin:0;background:#000;width:100%;height:100%;overflow:hidden}body{box-sizing:border-box;padding:${inset}px}svg{width:100%;height:100%;display:block}</style>${svg}`);
  await page.screenshot({path:path.join(root,isSmall?`favicon-${size}.png`:size===180?'apple-touch-icon.png':`icon-${size}.png`)});
 }
 await page.setViewportSize({width:512,height:512});
 const mask=fs.readFileSync(path.join(root,'mark-dark.svg'),'utf8');
 await page.setContent(`<style>html,body{margin:0;background:#000;width:100%;height:100%;overflow:hidden}body{display:grid;place-items:center}svg{width:320px;height:auto}</style>${mask}`);
 await page.screenshot({path:path.join(root,'icon-maskable-512.png')});
 for(const [width,height,file] of [[1200,630,'og-image.png'],[1280,640,'github-social.png']]){
  await page.setViewportSize({width,height});
  await page.goto(pathToFileURL(path.join(root,'src/og.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  await page.addStyleTag({content:`body{width:${width}px;height:${height}px}`});
  await page.screenshot({path:path.join(root,file)});
 }
 await browser.close();
})();
