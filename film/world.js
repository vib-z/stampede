/* Original illustration. Motion curves and clock from motionmaxxing (Apache-2.0). */
(() => {
  const q = new URLSearchParams(location.search);
  const phone = q.get('cut') === 'phone';
  const dark = q.get('theme') === 'dark';
  const W = phone ? 1080 : 1920, H = phone ? 1920 : 1080;
  const M = Motion.film({fps:30, duration:14, width:W, height:H, clock:'smooth'});
  const C = dark ? {paper:'#0a0a0a',light:'#1f1f1f',ink:'#f5f5f5',soft:'#a3a3a3',edge:'#5c5c5c',slip:'#1f1f1f',shadow:'#000000'} :
    {paper:'#ffffff',light:'#fafafa',ink:'#0a0a0a',soft:'#6b6b6b',edge:'#a3a3a3',slip:'#fafafa',shadow:'#000000'};
  const clamp = v => Math.min(1, Math.max(0,v));
  const ease = (t,a,b,name='softLand') => Motion.ease[name](clamp((t-a)/(b-a)));
  const mix = (a,b,p) => a+(b-a)*p;
  const n = v => Number(v.toFixed(3));
  // Element fades keep the SVG master and direct Canvas compositor identical.
  // Zero-opacity groups stay intact so the opening export can omit hidden art.
  const group = (s,x=0,y=0,scale=1,rot=0,opacity=1) => {
    if(opacity>0&&opacity<1){
      s=s.replace(/<(?:path|use|rect|circle|ellipse|image)\b[^>]*>/g,tag=>{
        const old=tag.match(/\sopacity="([^"]+)"/),alpha=n(opacity*Number(old?.[1]??1));
        return old?tag.replace(old[0],` opacity="${alpha}"`):tag.replace(/(\/?>)$/,` opacity="${alpha}"$1`);
      });
    }
    return `<g transform="translate(${n(x)} ${n(y)}) rotate(${n(rot)}) scale(${n(scale)})" opacity="${opacity===0?0:1}">${s}</g>`;
  };
  const path = (d, width=3, color=C.ink, extra='') => `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
  const rect = (x,y,w,h,r=0,fill=C.slip,stroke=C.edge,sw=2) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
  function text(s,x,y,size=48,anchor='middle',color=C.ink) {
    const a=SHAPES.text[s];
    const offset=anchor==='middle'?-a.width*size/2:anchor==='end'?-a.width*size:0;
    return `<g aria-label="${s}" transform="translate(${n(x+offset)} ${n(y)}) scale(${size})" fill="${color}"><use href="#word${Object.keys(SHAPES.text).indexOf(s)}"/></g>`;
  }
  const sourceMaterials=MATERIALS[dark?'dark':'light'];
  const materials={paper:sourceMaterials[phone?'paper-phone':'paper'],agent:sourceMaterials.agent};
  const materialDefs=Object.entries(materials).filter(([name])=>!name.startsWith('cable-')).map(([name,m])=>`<image id="mat-${name}" width="${m.w}" height="${m.h}" href="${m.url}"/>`).join('');
  const material=(name,x,y,w,h)=>`<use href="#mat-${name}" transform="translate(${x} ${y}) scale(${w/materials[name].w} ${h/materials[name].h})"/>`;
  const logo = (name,x,y,size) => `<use href="#${name}" x="${x-size/2}" y="${y-size/2}" width="${size}" height="${size}"/>`;
  const shadow = (x,y,rx,ry,op=.15) => [1,.78,.55,.3].map(k=>`<ellipse cx="${n(x)}" cy="${n(y)}" rx="${n(rx*k)}" ry="${n(ry*k)}" fill="${C.shadow}" opacity="${op*.22}"/>`).join('');
  const defs = Object.entries(SHAPES.logos).map(([key,svg]) => svg.replace(/<svg[^>]*>/,tag=>`<symbol id="${key}" viewBox="${tag.match(/viewBox="([^"]+)"/)[1]}">`).replace('</svg>','</symbol>').replace(/var\(--paper[^)]*\)/g,C.paper)).join('')+Object.values(SHAPES.text).map((v,i)=>`<path id="word${i}" d="${v.path}"/>`).join('');
  function ground(){return `<defs><linearGradient id="phone-metal" x1="0" y1="0" x2="100%" y2="100%"><stop offset="0" stop-color="#eeeeee"/><stop offset=".16" stop-color="#777777"/><stop offset=".48" stop-color="#222222"/><stop offset=".82" stop-color="#999999"/><stop offset="1" stop-color="#444444"/></linearGradient><linearGradient id="phone-glass" x1="0" y1="0" x2="100%" y2="100%"><stop offset="0" stop-color="#ffffff" stop-opacity=".16"/><stop offset=".45" stop-color="#ffffff" stop-opacity=".025"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient><g id="raster-materials">${materialDefs}</g>${defs}<radialGradient id="pool" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="1"><stop offset="0" stop-color="${dark?'#a3a3a3':'#f2f2f2'}" stop-opacity="${dark?.16:.74}"/><stop offset="1" stop-color="${dark?'#a3a3a3':'#f2f2f2'}" stop-opacity="0"/></radialGradient></defs><rect width="${W}" height="${H}" fill="${C.paper}"/>`;}
  let clock=0;
  const unit=phone?480/211:1.2,T={meta:16*unit,beat:24*unit,headline:(phone?24:36)*unit,ask:(phone?36:48)*unit};
  const starts=[0,54,84,129,192,258,318,390];window.__beatStarts=starts;
  const tween=(f,a,b)=>ease(f,a,b,'softInOut');
  const safe=(s,name)=>s.replace('<g ',`<g data-safe="${name}" `);
  const fade=(f,a,b,c,d)=>tween(f,a,b)*(1-tween(f,c,d));
  function badge(p){
    const local=[[-18,12],[-18,12,-13,7,-13,6],[-13,6,-13,-10,-13,-11],[-13,-13,13,-13,13,-11],[13,-11,13,6,13,6],[13,7,18,12,18,12],[15,14,-15,14,-18,12]];
    const cloud=[[-15,11],[-25,8,-24,-7,-13,-7],[-12,-22,8,-24,13,-10],[24,-13,30,4,20,10],[17,13,12,12,10,12],[3,12,-5,12,-10,12],[-12,12,-14,12,-15,11]];
    const pts=local.map((v,i)=>v.map((n,j)=>mix(n,cloud[i][j],p)));
    const d=`M ${pts[0].map(n).join(' ')} `+pts.slice(1).map(v=>'C '+v.map(n).join(' ')).join(' ');
    return `<g data-badge="${p===0?'local':p===1?'cloud':'morph'}" data-progress="${n(p)}"><circle r="27" fill="${C.slip}" stroke="${C.edge}" stroke-width="1.5"/>${path(d,2.6)}${path('M -12 7 H 12',2,C.ink,`opacity="${n(1-p)}"`)}</g>`;
  }
  function agent(name,role,x,y,location=0,alpha=1,action=0,size=1,badgeScale=1,closing=0){
    const breath=Math.sin(clock*2.4+role.length*.79)*2.3;
    const legs=path(`M -44 101 L -51 126 M 44 101 L ${n(mix(51,110,action))} 126`,8);
    const body=path('M -67 47 Q -78 67 -72 85 M 67 47 Q 78 67 72 85',6)+material('agent',-73,-59,146,172)+(dark?rect(-43,-36,86,86,14,'#eeeeee','none',0):'')+logo(name,0,7,77)+(closing?group(rect(-60,-49,120,150,20,C.shadow,'none',0),0,0,1,0,closing*.8):'');
    const figure=group(shadow(0,131,80,7,.35)+legs+group(body,0,breath),0,0,size)+group(badge(location),66*size,-39*size,badgeScale);
    return safe(group(`<g data-close="${n(closing)}" transform="scale(1 ${n(Math.max(.005,1-closing))})">${figure}</g>`,x,y-closing*20,1,0,alpha),`agent-${role}`);
  }
  // Original generic handset. Storyboard press timing; source studies in site/README.md.
  function handset(x,y,f,reply=false,scale=1,rotation=0,alpha=1){
    const w=reply?(phone?430:350):(phone?660:400),h=reply?(phone?700:590):(phone?1100:670);
    const left=-w/2,top=-h/2,inset=phone?30:20,r=phone?54:38,screen=dark?'#111111':'#fafafa';
    let body='';
    for(let i=14;i>0;i--){const spread=i*1.35;body+=group(rect(left-spread,top-spread,w+spread*2,h+spread*2,r+spread,'#000000','none',0),5,7+i*.9,1,0,.004+(15-i)*.0011);}
    body+=rect(left-4,top+h*.23,6,h*.12,3,'#777777','none',0)+rect(w/2-2,top+h*.29,6,h*.09,3,'#777777','none',0);
    body+=rect(left,top,w,h,r,'url(#phone-metal)','#8a8a8a',1.5);
    body+=rect(left+4,top+4,w-8,h-8,r-3,'#181818','#bcbcbc',.8);
    body+=rect(left+9,top+9,w-18,h-18,r-8,'#050505','#303030',1);
    body+=rect(left+inset,top+inset+13,w-inset*2,h-inset*2-26,r-inset*.65,screen,dark?'#333333':'#e5e5e5',1);
    body+=path(`M -${w*.065} ${top+18} H ${w*.065}`,3,'#777777');
    // Reflect light below the mark and chat so their original ink stays sharp.
    body+=group(rect(left+inset+2,top+inset+15,w-inset*2-4,h-inset*2-30,r-inset*.65,'url(#phone-glass)','none',0),0,0,1,0,.55);
    const header=top+(phone?98:76),mark=phone?50:34;
    body+=logo('grokbot',left+inset+mark/2+16,header-12,mark)+text('Grok Bot',left+inset+mark+28,header,T.meta,'start');
    body+=path(`M ${left+inset+16} ${header+28} H ${w/2-inset-16}`,1,dark?'#333333':'#e5e5e5');
    const contentY=reply?top+h*.39:top+h*.42,inner=w-inset*2-32,bx=-inner/2;
    let content='';
    if(reply){
      content+=rect(bx,contentY-50,inner,phone?268:216,18,C.light,dark?'#444444':'#d4d4d4',1.2);
      const tx=bx+20,headline=T.headline;
      content+=text('Ready on',tx,contentY,headline,'start')+text('staging.',tx,contentY+headline*1.18,headline,'start');
      content+=text('Tested. Reviewed.',tx,contentY+(phone?151:117),T.meta,'start',C.soft)+text('Your call.',tx,contentY+(phone?202:151),T.meta,'start',C.soft);
      content+=path(`M ${inner/2-45} ${contentY-27} l 7 7 15 -17`,3,C.ink);
      body+=group(content,0,mix(12,0,tween(f,phone?368:349,phone?375:356)),1,0,tween(f,phone?368:349,phone?375:356));
    }else{
      const sent=tween(f,40,46),typed=Math.min(23,5+Math.floor(Math.max(0,f)*2/3));
      const line1='Build the'.slice(0,Math.min(9,typed)),line2='pricing page.'.slice(0,Math.max(0,typed-10));
      const size=phone?T.ask:T.headline,lineHeight=size*1.2,ty=contentY-20;
      content+=rect(bx,ty-size-25,inner,lineHeight*2+36,18,C.light,dark?'#444444':'#d4d4d4',1.2);
      if(line1)content+=text(line1,bx+22,ty,size,'start');
      if(line2)content+=text(line2,bx+22,ty+lineHeight,size,'start');
      if(f<34){const value=line2||line1,cx=bx+22+SHAPES.text[value].width*size+5,cy=ty+(line2?lineHeight:0);content+=path(`M ${n(cx)} ${n(cy-size*.76)} V ${n(cy+3)}`,2.5,C.ink);}
      if(f>=40)content+=group(path(`M ${inner/2-51} ${ty+lineHeight+5} l 9 9 18 -21`,3,C.ink),0,0,1,0,sent);
      body+=group(content,0,-sent*(phone?24:16));
      const press=tween(f,32,36)*(1-tween(f,37,42)),cy=h/2-inset-(phone?121:83),radius=phone?34:25;
      body+=group(`<circle r="${radius}" fill="${C.ink}"/>${path('M 0 12 V -12 M -10 -2 L 0 -12 10 -2',3,C.paper)}`,w/2-inset-radius-17,cy,1-press*.06,0,1-tween(f,43,48));
    }
    return safe(group(`<g data-phone="${reply?'reply':'ask'}">${body}</g>`,x,y,scale,rotation,alpha),reply?'reply':'ask');
  }
  function paper(w,h){return material('paper',-w/2,-h/2,w,h);}
  function note(x,y,s=1,rot=0,check=false){
    return safe(group(paper(150,185)+path('M -46 -48 H 41 M -46 -23 H 35 M -46 2 H 13',4,C.soft)+(check?path('M -28 41 l 17 17 39 -43',5,C.ink):''),x,y,s,rot),'result');
  }
  function research(f){
    let art='';const cx=phone?540:960,cy=phone?950:520,exit=tween(f,122,137);
    // Back sheets enter first in paint order, at full opacity behind the front sheet.
    for(const i of [2,1,0]){
      const p=tween(f,87+i*7,99+i*7);if(p===0)continue;
      const x=mix(cx,cx+(i-1)*(phone?170:210),p),y=cy+(i===1?-30:60)+exit*200;
      art+=`<g data-sheet="research" opacity="1">${note(x,y,(phone?1.7:1.6)*p*(1-exit),(i-1)*7,false)}</g>`;
      if(f>=101+i*5){const pin=tween(f,101+i*5,108+i*5),px=x+(i-1)*32,py=y-130;art+=safe(group(`${shadow(4,7,46,36,.25)}${rect(-40,-32,80,65,3,dark?'#3d3d3d':'#e5e5e5',C.edge,1)}<circle cy="-22" r="6" fill="${C.ink}"/>${path('M -22 1 H 22 M -22 14 H 9',3)}`,px,py,pin*(1-exit)),'pinned-note');}
    }
    return art;
  }
  function connection(f,back=false){
    const a=back?fade(f,299,306,330,338):fade(f,128,136,186,196);
    const d=phone?(back?'M 280 1460 Q 540 1560 800 1460':'M 280 1165 Q 540 1135 800 1165'):(back?'M 1510 880 C 1230 960 770 960 410 850':'M 500 735 C 790 740 1090 570 1440 590');
    let out=path(d,10,'#5c5c5c')+path(d,6,'#a3a3a3')+path(d,1.6,'#ffffff','transform="translate(-1 -1)"');
    if(!back){
      const x=phone?540:960,y=phone?1150:665;
      out+=group(`<circle r="34" fill="${C.paper}"/>${logo('tailscale',0,0,54)}`,x,y);
      for(const start of [145,166])if(f>=start&&f<=start+12){const p=tween(f,start,start+12);out+=group(path(`M ${n(-85+p*140)} 0 h 30`,5,'#ffffff'),x,y,1,phone?0:-15,Math.sin(p*Math.PI));}
    }
    return group(out,0,0,1,0,a);
  }
  function page(f){
    const enter=tween(f,174,184),layout=tween(f,216,239),retire=phone?tween(f,292,310)*(1-tween(f,338,372)):tween(f,292,310)*(1-tween(f,338,372));
    const end=tween(f,338,372),s=mix(1,phone?.84:.9,end)*(1-retire*(phone?.08:.15));
    const x=mix(W/2,phone?W/2:1200,end),y=mix(phone?1000:540,phone?1400:640,end),w=phone?760:900,h=phone?720:500;
    let art=paper(w,h),copy='';
    // Tabs are paper dividers, with a single active surface and shallow relief.
    for(let i=0;i<3;i++){const p=tween(f,177+i*4,184+i*4);art+=group(rect(-w/2+40+i*95,-h/2+30,82,24,6,i===0?C.slip:C.paper,C.edge,1),0,mix(-12,0,p),1,0,p);}
    if(s>.79&&f>=218)copy+=group(text('Pricing',-w/2+46,-h/2+115,T.beat/s,'start'),0,0,1,0,tween(f,218,226));
    for(let i=0;i<3;i++){
      const p=tween(f,184+i*10,198+i*10),cw=phone?640:245,ch=phone?154:290;
      const cx=phone?0:-275+i*275,cy=phone?-115+i*174:50;
      const dx=(i-1)*mix(26,0,layout),dy=mix(35,0,p)+(i===1?mix(-20,0,layout):0);
      let card=rect(-cw/2,-ch/2,cw,ch,10,C.slip,C.edge,1.6);
      card+=path(phone?`M ${-cw/2+28} 16 h 180 m -180 22 h 124`:`M ${-cw/2+24} -35 h 132 m -132 28 h 94 m -94 28 h 115`,3,C.soft);
      const bx=phone?cw/2-90:0,by=phone?10:ch/2-47;
      card+=rect(bx-(phone?60:87),by-22,phone?120:174,44,8,i===1?C.ink:C.paper,C.ink,1.5)+path(`M ${bx-13} ${by} h 25 m -9 -8 l 9 8 -9 8`,3,i===1?C.paper:C.ink);
      if(s>.79&&p>.97)card+=text(['Starter','Team','Scale'][i],-cw/2+26,-ch/2+45,T.meta/s,'start');
      art+=group(card,cx+dx,cy+dy,1,mix((i-1)*3,0,layout),p);
    }
    if(f>=218&&f<240){const a=fade(f,218,223,235,240);art+=group(path(`M ${-w/2+38} ${-h/2+140} H ${w/2-38} M 0 ${-h/2+140} V ${h/2-28}`,1.8,C.ink),0,0,1,0,a);}
    if(f>=274){const label=f<285?'round 1':'round 2',a=tween(f,f<285?274:285,f<285?278:290);if(s>.79){const sx=w/2-(phone?150+end*30:100),sy=-h/2+106;art+=group(rect(-(phone?112:66),-29,phone?224:132,42,5,'none','#5c5c5c',3.8)+rect(-(phone?112:66),-29,phone?224:132,42,5,'none',C.ink,2.2)+rect(-(phone?112:66)-1,-30,phone?224:132,42,5,'none','#e5e5e5',.7)+text(label,0,0,T.meta,'middle',C.ink),sx,sy,1/s,0,a);}}
    return safe(group(`<g data-work="pricing-page">${art}${copy}</g>`,x,y,s,0,enter),'pricing-page');
  }
  function tester(f){
    const a=fade(f,239,245,266,274),x=phone?280:385,y=phone?1475:690;
    const click=tween(f,244,249),jump=tween(f,251,262),squash=tween(f,262,266);
    const bx=mix(phone?790:685,x+110,jump),by=mix(phone?895:690,y+126,jump)-Math.sin(jump*Math.PI)*(phone?180:90);
    let art=agent('cursor','test',x,y,0,a,squash);
    if(f>=242&&f<254){const p=tween(f,242,247),cx=mix(x+70,phone?790:685,p),cy=mix(y-30,phone?895:690,p);art+=safe(group(`<path d="M 0 0 L 4 30 L 12 22 L 23 25 Z" fill="${C.ink}" stroke="${C.paper}" stroke-width="2"/>`,cx,cy,1,0,a),'test-pointer');}
    if(f>=245&&f<252){const cx=phone?790:685,cy=phone?895:690;art+=group(`<circle cx="${cx}" cy="${cy}" r="${n(16+click*20)}" fill="none" stroke="${C.ink}" stroke-width="3"/>`,0,0,1,0,a*(1-click*.8));}
    if(f>=251&&f<269){const bug=`<ellipse rx="22" ry="29" fill="${C.ink}"/>${path('M -14 -20 l -17 -12 M 14 -20 l 17 -12 M -20 -5 h -17 M 20 -5 h 17 M -20 12 l -14 12 M 20 12 l 14 12',4)}<path d="M 0 -20 V 22" stroke="${C.paper}" stroke-width="2"/>`;art+=safe(group(`<g data-work="bug" transform="scale(1 ${n(1-squash*.94)})">${bug}</g>`,bx,by,phone?1.25:1,0,a*(1-tween(f,266,269))),'bug');}
    return art;
  }
  function reviewer(f){
    const a=fade(f,268,274,294,300),x=phone?800:1535,y=phone?1425:690,p=tween(f,271,291);
    const gx=x-100-Math.sin(p*Math.PI)*30,gy=y-85;
    const glass=`<circle r="${phone?83:68}" fill="${C.paper}" opacity=".12"/><circle r="${phone?83:68}" fill="none" stroke="#5c5c5c" stroke-width="8"/><circle r="${phone?83:68}" fill="none" stroke="#a3a3a3" stroke-width="5"/><circle cx="-1" cy="-1" r="${phone?83:68}" fill="none" stroke="#ffffff" stroke-width="1.4"/>${path(`M ${phone?58:48} ${phone?58:48} l 60 65`,12,C.ink)}`;
    return agent('codex','review',x,y,0,a)+safe(group(`<g data-work="magnifier">${glass}</g>`,gx,gy,1,0,a),'magnifier');
  }
  function render(t){
    const frame=Math.min(419,Math.max(0,t*30)),f=frame<129?frame:frame<192?129+(frame-129)*45/63:frame-18;clock=Math.min(frame,400)/30;
    const lightX=W/2,lightY=phone?mix(950,1150,tween(f,129,174)):mix(520,650,tween(f,300,372));
    let art=group('<circle r="1" fill="url(#pool)"/>',lightX,lightY);art=art.replace('scale(1)',`scale(${phone?650:900} ${phone?590:560})`);
    const leadA=f>=(phone?54:46)?1-tween(f,96,108):0,leadX=phone?540:960,leadY=phone?1090:620;
    if(f<76){const p=phone?ease(f,52,68,'cruise'):tween(f,46,73);art+=handset(mix(W/2,leadX,p),mix(phone?1120:540,leadY+12,p),f,false,mix(1,.18,p),mix(-3,0,p),1-tween(f,68,76));}
    // Workers emerge behind the lead before it moves aside, then keep their positions into the work.
    if(f>=66&&f<137){const p=tween(f,66,94);art+=agent('claude','research',mix(leadX,phone?800:1430,p),mix(leadY,phone?1240:690,p),0,1-tween(f,122,137));}
    if(f>=68&&f<129)for(let i=0;i<2;i++){
      const p=tween(f,68+i*4,94+i*4),depart=tween(f,116,129);
      const tx=phone?mix(i===0?315:765,315,depart):mix(370,540,depart),ty=phone?mix(1490,i===0?995:1280,depart):mix(i===0?760:960,i===0?590:850,depart);
      if(f>=68+i*4)art+=agent('codex',i===0?'build':'design',mix(leadX,tx,p),mix(leadY,ty,p));
    }
    if(leadA>0){const p=tween(f,82,108);art+=agent('claude','lead',mix(leadX,phone?280:440,p),leadY+mix(-65,0,tween(f,54,72)),0,leadA,0,mix(1.8,1,p),1,1-tween(f,phone?54:46,phone?66:58));}
    if(f>=84&&f<137)art+=research(f);
    if(frame>=128&&frame<196)art+=connection(frame);
    if(f>=174)art+=page(f);
    // The same pair changes location once, on passing the link, then stays cloud.
    if(f>=129&&f<245)for(let i=0;i<2;i++){
      const hold=i===0?145:166,morph=tween(frame,hold,hold+12),approach=tween(frame,132+i*3,hold),depart=tween(frame,hold+12,i===0?184:190);
      const p=frame<hold?.5*approach:.5+.5*depart,settle=tween(frame,190,203),a=1-tween(frame,255,263);
      let x=phone?mix(315,765,p):mix(540,1380,p),y=phone?(i===0?995:1280):mix(730,570,p)+(i===0?-140:120);
      x=mix(x,phone?(i===0?280:800):1535,settle);y=mix(y,phone?1475:(i===0?430:730),settle);
      const emphasis=1+tween(frame,hold-3,hold)*(1-tween(frame,hold+12,hold+16));
      art+=agent('codex',i===0?'build':'design',x,y,morph,a,0,1,emphasis);
      if(i===1&&f>=217&&f<240){const px=phone?765:1390,py=phone?1305:650;art+=safe(group(path('M -45 -8 H 45 M -30 -15 V 3 M -10 -15 V 3 M 10 -15 V 3 M 30 -15 V 3',4,C.ink),px,py,1,0,fade(f,217,222,235,240)),'layout-rule');}
    }
    if(f>=239&&f<274)art+=tester(f);
    if(f>=268&&f<300)art+=reviewer(f);
    if(f>=299&&f<342)art+=connection(f,true);
    if(f>=300&&f<338)for(let i=0;i<2;i++){
      const p=tween(f,300+i*7,330+i*7),a=fade(f,300,306,330,338);
      const x=phone?(i===0?mix(280,400,p):mix(800,680,p)):mix(1510,i===0?580:780,p),y=phone?1460+Math.sin(p*Math.PI)*45:mix(i===0?872:660,872,tween(f,300,310));
      art+=group(note(x+(phone?(i===0?100:-100):-110),y+25,.62,i===0?-5:5,true),0,0,1,0,a)+agent('codex',i===0?'build':'design',x,y,1,a);
    }
    const gather=frame<400?tween(f,326,338):0;
    if(gather>0){const x=phone?540:220,y=phone?1650:850;art+=agent('claude','lead',x,y,0,gather,0,1,1,tween(frame,390,400));
      if(f<353)art+=safe(group(paper(phone?265:220,125)+path(`M -78 -25 h ${n(156*tween(f,333,344))} M -78 0 h ${n(130*tween(f,340,351))}`,3,C.ink),x+(phone?0:50),y-145,1,0,gather),'written-reply');
    }
    if(f>=(phone?365:344)){const p=tween(f,phone?365:344,phone?378:360);if(p>0)art+=handset(phone?540:480,mix(phone?840:650,phone?800:610,p),f,true,phone?.78:1,0,p);}
    if(frame>=395)art+=group(text('All agents closed.',W/2,phone?1800:945,T.beat),0,0,1,0,tween(frame,395,400));
    if(frame>=368&&frame<390)art+=group(text('Your call.',phone?174:218,phone?1800:1010,T.beat,'start'),0,0,1,0,tween(frame,368,374)*(1-tween(frame,384,390)));
    const prefix=`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" color="${C.ink}" role="img" aria-label="A Grok Bot ask is typed and sent on a generic phone. Location badges change as builders cross Tailscale. Research, design, testing and two reviews produce a pricing page and return a reply to the phone. The agents close; the finished page stays.">${ground(t)}`;
    window.__lastParts={prefix,body:art,suffix:'</svg>',width:W,height:H};
    const svg=prefix+art+'</svg>';document.getElementById('main').innerHTML=svg;return svg;
  }
  starts.slice(1).forEach((f,i)=>M.mark(f,'beat',`beat ${i+2}`));
  const seek=M.seek;window.__seek=t=>{seek(t);return render(t);};window.__svgAt=render;
  window.__ready=Motion.loaded().then(()=>{render(0);if(q.has('selftest'))Motion.selfTest(M,{samples:24});});
})();
