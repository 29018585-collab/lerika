"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html");let priceMode="full";
const server=http.createServer((req,res)=>{if(req.url==="/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html)}else if(req.url==="/public/prices"){if(priceMode==="error"){res.writeHead(503);res.end();return}res.writeHead(200,{"Content-Type":"application/json"});res.end(JSON.stringify({updated:1760000000,entries:priceMode==="empty"?[]:[{group:"корпус",material:"ЛДСП",price:1000},{group:"фасады",material:"ЛДСП",price:2000},{group:"фасады",material:"МДФ эмаль",price:3500}]}))}else{res.writeHead(404);res.end()}});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const b=await chromium.launch({headless:true});try{
const p=await b.newPage({viewport:{width:390,height:844},hasTouch:true,acceptDownloads:true});const errors=[];p.on("pageerror",e=>errors.push(e.message));p.on("dialog",d=>d.accept());
const root="http://127.0.0.1:"+server.address().port+"/";
await p.goto(root+"#design-lab",{waitUntil:"domcontentloaded"});
assert.equal(await p.locator("#project-paths").isVisible(),true);await p.locator('#project-paths a[href="#design-lab/order"]').click();await p.locator("#lo-panel").waitFor({state:"visible"});assert.equal(await p.locator("#lo-files").isVisible(),true);
await p.evaluate(()=>location.hash="#design-lab/3d");await p.locator("#lab-3d-panel").waitFor({state:"visible"});
assert.equal(await p.locator("#lab3-panel-summary").count(),0);
await p.locator("#lab3-w").fill("1700");await p.locator("#lab3-body-m").selectOption("ЛДСП");await p.locator("#lab3-face-m").selectOption("ЛДСП");await p.locator("#lab3-top-m").selectOption("ЛДСП");await p.locator("#lab3-sections select").first().selectOption("drawers");
await p.locator("#lab3-project-save").click();assert.match(await p.locator("#lab3-project-status").textContent(),/Сохранено/);
await p.locator("#lab3-order").click();await p.locator("#estimate-panel").waitFor({state:"visible"});await p.waitForFunction(()=>document.querySelector("#estimate-price-status").textContent.startsWith("Прайс от"));
assert.equal(await p.locator(".project-item").count(),1,"estimate shortcut must not add the same saved item twice");
const data=await p.evaluate(()=>{const a=JSON.parse(localStorage.getItem("lerika-project-v519")).items[0],m=LerikaRoomPlanner.model(a),r=LerikaProject.compute([a]);return {a,expected:m.areas.Корпус*1000+m.areas.Фасад*2000,actual:r.total,missing:r.missing}});
assert.equal(data.a.w,1700);assert.equal(data.a.config[0],"drawers");assert.equal(data.missing,0);assert.ok(Math.abs(data.actual-data.expected)<.00001,"exact published rate calculation");
// V5.21: pricing must follow explicit physical part roles, not names or decor.
const calc=await p.evaluate(()=>{
 const P=LerikaRoomPlanner,E=LerikaFurniture;
 const reports=[];
 for(const type of Object.keys(E.presets)){
   const a={...P.item(type,1),bodyM:"ЛДСП",faceM:"ЛДСП",topM:"ЛДСП"};
   const model=P.model(a),r=LerikaProject.compute([a]),changed=LerikaProject.compute([{...a,topM:"Кварцевый агломерат"}]);
   const sum=model.parts.reduce((n,p)=>n+p.a*p.b*p.qty/1e6,0);
   const areaSum=Object.values(r.areas).reduce((n,v)=>n+v,0);
   const pricedBody=r.lines.filter(l=>l.group==="корпус").reduce((n,l)=>n+l.area,0);
   const pricedFront=r.lines.filter(l=>l.group==="фасады").reduce((n,l)=>n+l.area,0);
   reports.push({type,sum,areaSum,pricedBody,pricedFront,body:r.areas.Корпус,front:r.areas.Фасад,top:r.areas.Столешница,changedBody:changed.areas.Корпус,total:r.total,changedTotal:changed.total,partRoles:model.parts.map(p=>({name:p.name,role:p.role,area:p.a*p.b*p.qty/1e6}))});
 }
 const bed={...P.item("bed",1),bodyM:"ЛДСП",faceM:"ЛДСП"},a=LerikaProject.compute([bed]),b=LerikaProject.compute([{...bed,faceM:"МДФ эмаль"}]);
 return {reports,bedDelta:b.total-a.total,bedFront:a.areas.Фасад,bedMissing:b.missing};
});
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,JSON.stringify({a,b}));
for(const r of calc.reports){
 close(r.sum,r.areaSum);close(r.body,r.pricedBody);close(r.front,r.pricedFront);
 close(r.body,r.changedBody);close(r.total,r.changedTotal);close(r.total,r.body*1000+r.front*2000);
 assert.ok(r.partRoles.every(p=>["body","front","top","back"].includes(p.role)));
 assert.ok(r.partRoles.filter(p=>/^Верх |^Сиденье/.test(p.name)).every(p=>p.role==="body"));
 close(r.top,r.partRoles.filter(p=>p.role==="top").reduce((n,p)=>n+p.area,0));
}
assert.ok(calc.bedFront>0);close(calc.bedDelta,calc.bedFront*1500);assert.equal(calc.bedMissing,0);
assert.ok(calc.reports.find(r=>r.type==="kitchen").top>0);assert.ok(calc.reports.find(r=>r.type==="hall").body>0);
console.log("PASS V5.21 BUG-005/011/012: 12 types, role-based area conservation, prices and bed headboard");
await p.reload();await p.locator("#estimate-panel").waitFor({state:"visible"});assert.equal(await p.locator(".project-item").count(),1,"persisted furniture");
await p.locator(".project-item").getByRole("button",{name:"Разместить в комнате"}).click();await p.locator("#lab-plan-panel").waitFor({state:"visible"});
await p.locator("#lp-clear").click();await p.locator("#lp-project-add").click();assert.equal(await p.locator("#lp-fw").inputValue(),"1700");assert.equal(await p.locator("#lp-bodyM").inputValue(),"ЛДСП");assert.equal(await p.locator("#lp-summary").getByText("Корпус",{exact:true}).count(),0);
const room=await p.evaluate(()=>LerikaRoomProject.snapshot());assert.equal(room.items.length,1);assert.equal(room.items[0].config[0],"drawers");assert.deepEqual(room.items[0].construction,data.a.construction);
await p.locator("#lp-order").click();await p.locator("#estimate-panel").waitFor({state:"visible"});assert.equal(await p.locator("#estimate-source").inputValue(),"plan");await p.waitForFunction(()=>document.querySelector("#estimate-price-status").textContent.startsWith("Прайс от"));assert.equal(await p.locator(".estimate-line").count(),1);
let download=p.waitForEvent("download");await p.locator("#estimate-download").click();let file=await download;assert.equal(file.suggestedFilename(),"LERIKA-Estimate.csv");const csv=fs.readFileSync(await file.path(),"utf8");assert.match(csv,/ЛДСП/);assert.match(csv,/1000/);assert.match(csv,/2000/);assert.match(csv,/"\d+,\d{3}"/,"BUG-026 area exported with decimal comma");assert.match(csv,/"\d+,\d{2}"/,"BUG-026 money exported with decimal comma");
priceMode="empty";await p.locator("#estimate-refresh").click();await p.waitForFunction(()=>document.querySelector("#estimate-price-status").textContent.includes("не опубликован"));assert.match(await p.locator("#estimate-totals").textContent(),/Нет цены/);assert.doesNotMatch(await p.locator("#estimate-totals").textContent(),/0 ₽/);
priceMode="error";await p.locator("#estimate-refresh").click();await p.waitForFunction(()=>document.querySelector("#estimate-price-status").textContent.includes("недоступен"));assert.match(await p.locator("#estimate-totals").textContent(),/Нет цены/);
priceMode="full";await p.locator("#estimate-refresh").click();await p.waitForFunction(()=>document.querySelector("#estimate-price-status").textContent.startsWith("Прайс от"));await p.locator("#estimate-order").click();await p.locator("#lo-panel").waitFor({state:"visible"});assert.match(await p.locator("#lo-files-status").textContent(),/4 \/ 10 файлов/);for(const n of ["LERIKA-Project.txt","LERIKA-Estimate.csv","LERIKA-Room-Plan.png","LERIKA-Room-3D.png"])assert.match(await p.locator("#lo-list").textContent(),new RegExp(n.replace(".","\\.")));
assert.equal(await p.locator("#lo-source").inputValue(),"plan");
await p.evaluate(()=>location.hash="#design-lab/config");await p.locator("#lab-config-panel").waitFor({state:"visible"});assert.equal(await p.locator("#lab-price").count(),0);const oldWidth=await p.locator("#lab-w").inputValue();await p.locator("#lab-w").fill("1800.5");assert.equal(await p.locator("#lab-project-save").isDisabled(),true,"fractional width must disable save before rendering");assert.equal(await p.locator("#lab-contact").isDisabled(),true);await p.locator("#lab-w").fill(oldWidth);assert.equal(await p.locator("#lab-project-save").isEnabled(),true);await p.locator("#lab-project-save").click();assert.match(await p.locator("#lab-project-status").textContent(),/Сохранено/);
await p.evaluate(()=>location.hash="#design-lab/cut");await p.locator("#le-cut-card").waitFor({state:"visible"});assert.equal(await p.locator("#le-drawing-card").isVisible(),false);await p.locator("#le-cut").click();assert.ok(await p.locator("#le-sheet option").count()>0);await p.locator("#le-drawing-link").click();await p.locator("#le-drawing-card").waitFor({state:"visible"});assert.equal(await p.locator("#le-cut-card").isVisible(),false);
await p.evaluate(()=>location.hash="#contact");const vk=p.getByRole("link",{name:/Написать в VK/});await vk.waitFor({state:"visible"});assert.equal(await vk.getAttribute("href"),"https://vk.ru/lerikamebel");
const raster=await p.evaluate(()=>{const P=LerikaRoomPlanner,s=P.demo(),r=P.inspect(s.r,s.items,s.openings),cv=document.createElement("canvas");cv.width=500;cv.height=370;const ctx=cv.getContext("2d");return [0,1,2,3].map(i=>{const angle=.56+i*Math.PI/2,boxes=[...P.roomBoxes(s.r,s.openings,angle),...r.models.flatMap(m=>m.boxes.map(b=>({...b,pickId:m.item.id})))];ctx.fillStyle="#ece0cc";ctx.fillRect(0,0,cv.width,cv.height);const pick=LerikaRoomRaster(ctx,cv,boxes,{yaw:angle,pitch:.43,zoom:1.04},null),counts={1:0,2:0,3:0};for(let y=0;y<cv.height;y++)for(let x=0;x<cv.width;x++){const id=pick.hit(x,y);if(id)counts[id]++}return counts})});assert.ok(raster.every(v=>Object.values(v).every(n=>n>100)),JSON.stringify(raster));
// V5.22 recovery: one malformed item must not erase the valid collection.
const savedRaw=await p.evaluate(()=>localStorage.getItem("lerika-project-v519"));
const original=JSON.parse(savedRaw);const damaged={...original,items:[...original.items,{...original.items[0],projectId:"corrupt",w:1}]};
await p.evaluate(raw=>localStorage.setItem("lerika-project-v519",raw),JSON.stringify(damaged));
await p.reload();assert.equal(await p.locator(".project-item").count(),original.items.length);
assert.match(await p.locator("#project-save-status").textContent(),/Восстановлено/);
assert.equal(await p.evaluate(()=>localStorage.getItem("lerika-project-v519-recovery")),JSON.stringify(damaged));
assert.deepEqual(errors,[]);console.log("PASS V5.19 saved geometry, no duplicate, shared room, exact published rates, missing/error rates, four order files, separate cut, 4 camera angles and VK");
}finally{await b.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
