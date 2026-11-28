"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html"),server=http.createServer((req,res)=>{if(req.url==="/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html)}else{res.writeHead(404);res.end()}});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const b=await chromium.launch({headless:true});try{
const p=await b.newPage({viewport:{width:390,height:844}});const errors=[];p.on("pageerror",e=>errors.push(e.message));await p.goto("http://127.0.0.1:"+server.address().port+"/#design-lab/3d");
const results=await p.evaluate(()=>{
 const E=LerikaFurniture,canvas=document.createElement("canvas");canvas.width=144;canvas.height=112;const ctx=canvas.getContext("2d",{willReadFrequently:true}),out=[];
 // Independent inverse-camera ray / axis-aligned slab intersection in each box's own coordinates.
 function scene(type,m,view,label){
  const boxes=m.boxes.map((b,i)=>({...b,pickId:i+1})),W=canvas.width,H=canvas.height,sy=Math.sin(view.yaw),cy=Math.cos(view.yaw),sp=Math.sin(view.pitch),cp=Math.cos(view.pitch);
  const rotate=(b,p)=>{if(!b.hinge)return p;const [hx,hz]=b.hinge,c=Math.cos(b.angle),s=Math.sin(b.angle),dx=p[0]-hx,dz=p[2]-hz;return [hx+c*dx-s*dz,p[1],hz+s*dx+c*dz]};
  const bounds=boxes.flatMap(b=>[0,b.a].flatMap(x=>[0,b.b].flatMap(y=>[0,b.c].map(z=>rotate(b,[b.x+x,b.y+y,b.z+z]))))).map(([x,y,z])=>[x*cy-z*sy,-y*cp+(x*sy+z*cy)*sp]);
  const xs=bounds.map(p=>p[0]),ys=bounds.map(p=>p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),cx=(minX+maxX)/2,cyy=(minY+maxY)/2,k=Math.min(W*.79/(maxX-minX||1),H*.73/(maxY-minY||1))*(view.zoom||1);
  const dir=[sy*cp,sp,cy*cp],inverse=(b,p,vector=false)=>{if(!b.hinge)return p;const [hx,hz]=vector?[0,0]:b.hinge,c=Math.cos(b.angle),s=Math.sin(b.angle),dx=p[0]-hx,dz=p[2]-hz;return [hx+c*dx+s*dz,p[1],hz-s*dx+c*dz]};
  const rays=boxes.map(b=>({b,d:inverse(b,dir,true)}));
  ctx.clearRect(0,0,W,H);const actual=E.draw(ctx,canvas,{}, {boxes},view);
  let checked=0,different=0,ambiguous=0,visible=0;
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
   const u=(x+.5-W/2)/k+cx,v=(y+.5-H*.53)/k+cyy;
   const origin=[u*cy+v*sy*sp,-v*cp,-u*sy+v*cy*sp];
   let best=-Infinity,ids=[];
   for(const {b,d} of rays){
    const o=inverse(b,origin),lo=[b.x,b.y,b.z],hi=[b.x+b.a,b.y+b.b,b.z+b.c];let near=-Infinity,far=Infinity;
    for(let i=0;i<3;i++){if(Math.abs(d[i])<1e-10){if(o[i]<lo[i]-1e-7||o[i]>hi[i]+1e-7){near=Infinity;break}}else{const a=(lo[i]-o[i])/d[i],z=(hi[i]-o[i])/d[i];near=Math.max(near,Math.min(a,z));far=Math.min(far,Math.max(a,z));if(near>far+1e-7)break}}
    if(near>far+1e-7||!Number.isFinite(far))continue;
    if(far>best+.002){best=far;ids=[b.pickId]}else if(Math.abs(far-best)<=.002)ids.push(b.pickId);
   }
   const got=actual.hit(x,y);if(ids.length>1)ambiguous++;else checked++;
   if(ids.length)visible++;
   if(ids.length?!ids.includes(got):got!==null)different++;
  }
  out.push({type,label,checked,different,ambiguous,visible});
 }
 for(const [type,p] of Object.entries(E.presets)){
  const m={type,w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16};
  const opt={doors:"closed",drawers:"closed",light:false};
  for(let i=0;i<8;i++){const view={yaw:.23+i*Math.PI/4,pitch:.31,zoom:1};scene(type,E.build(m,opt),view,"closed-"+i)}
  if(["wardrobe","kitchen"].includes(type))for(let i=0;i<8;i++)scene(type,E.build(m,{...opt,doors:"all",drawers:"all"}),{yaw:.23+i*Math.PI/4,pitch:.31,zoom:1},"open-"+i);
 }
 return out;
});
const expected=["wardrobe","coupe","coupeMirror","hall","kitchen","wallcab","sideboard","tv","bookcase","desk","table","bed","nightstand","bath"].flatMap(type=>[...Array.from({length:8},(_,i)=>type+":closed-"+i),...(["wardrobe","kitchen"].includes(type)?Array.from({length:8},(_,i)=>type+":open-"+i):[])]);assert.equal(results.length,128);assert.deepEqual(results.map(q=>q.type+":"+q.label).sort(),expected.sort());for(const q of results){assert.ok(q.visible>0,JSON.stringify(q));assert.equal(q.different,0,JSON.stringify(q))}
await p.locator("#lab3-type").selectOption("wardrobe");await p.locator("#lab3-shelf-0").selectOption("7");assert.match(await p.locator("#lab3-sections select").first().locator('option[value="shelves"]').textContent(),/7 полок/);
assert.deepEqual(errors,[]);console.log("PASS BUG-004 independent ray-box oracle:",results.length,"views,",results.reduce((n,r)=>n+r.checked+r.ambiguous,0),"pixels,",results.reduce((n,r)=>n+r.different,0),"owner mismatches; BUG-024 dynamic shelf label");
}finally{await b.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
