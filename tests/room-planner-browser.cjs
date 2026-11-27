"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html");
const server=http.createServer((req,res)=>{if(req.url==="/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html)}else{res.writeHead(404);res.end()}});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const browser=await chromium.launch({headless:true});try{
const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1,hasTouch:true,acceptDownloads:true});const errors=[];page.on("pageerror",e=>errors.push(e.message));page.on("dialog",d=>d.accept());
await page.goto("http://127.0.0.1:"+server.address().port+"/#design-lab/plan",{waitUntil:"domcontentloaded"});
await page.locator("#lp-view").waitFor({state:"visible"});
assert.equal(await page.locator("#lp-type option").count(),12);
assert.equal(await page.locator("#lp-body option").count(),68);
assert.match(await page.locator("#lp-layout-status").textContent(),/не пересекаются/);
assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),"mobile overflow");
await page.locator("#lp-3d").click();assert.equal(await page.locator("#lp-3d").getAttribute("aria-pressed"),"true");
// Actual mobile touch on visible furniture, not on the bounding box of the room.
const cdp=await page.context().newCDPSession(page);
async function touchDrag(x,y,dx,dy){await cdp.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[{x,y,id:1}]});for(let i=1;i<=5;i++)await cdp.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[{x:x+dx*i/5,y:y+dy*i/5,id:1}]});await cdp.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]})}
async function sourceHit(id){return page.locator("#lp-view").evaluate((cv,id)=>{for(let y=20;y<cv.height-20;y+=5)for(let x=20;x<cv.width-20;x+=5)if(cv.liveEdit.pick(x,y)===id&&cv.liveEdit.pick(x+5,y+5)===id&&cv.liveEdit.pick(x-5,y-5)===id)return {x,y,w:cv.width,h:cv.height};throw Error("No visible target "+id)},id)}
await page.locator("#lp-view").scrollIntoViewIfNeeded();
let hit=await sourceHit(3),box=await page.locator("#lp-view").boundingBox(),k=box.width/hit.w;
await touchDrag(box.x+hit.x*k,box.y+hit.y*k,12,0);
assert.match(await page.locator("#lp-edit-title").textContent(),/#3/);
let x=Number(await page.locator("#lp-x").inputValue()),z=Number(await page.locator("#lp-z").inputValue());
assert.ok(x!==100||z!==2350,"3D furniture must move");
assert.ok(await page.locator("#lp-csv").isEnabled(),"valid 3D move");
await page.locator("#lz-open-lp-view").click();await page.locator("#lz-dialog").waitFor({state:"visible"});
assert.match(await page.locator("#lz-foot").textContent(),/Один палец/);
hit=await sourceHit(3);box=await page.locator("#lz-stage").boundingBox();k=Math.min(box.width/hit.w,box.height/hit.h);
await touchDrag(box.x+(box.width-hit.w*k)/2+hit.x*k,box.y+(box.height-hit.h*k)/2+hit.y*k,10,0);
await page.locator("#lz-close").click();
assert.ok(Number(await page.locator("#lp-x").inputValue())!==x||Number(await page.locator("#lp-z").inputValue())!==z,"live zoom must update underlying layout");
x=Number(await page.locator("#lp-x").inputValue());z=Number(await page.locator("#lp-z").inputValue());
await page.locator("#lp-2d").click();assert.equal(Number(await page.locator("#lp-x").inputValue()),x);assert.equal(Number(await page.locator("#lp-z").inputValue()),z);
assert.ok(await page.locator("#lp-csv").isEnabled());
await page.locator("#lp-demo").click();await page.locator("#lp-3d").click();
console.log("PASS actual touch movement in 3D and live zoom, 2D coordinates and valid layout");
await page.locator("#lp-camera-right").click();await page.locator("#lp-view").screenshot({path:"planner-3d-mobile.png"});
await page.locator("#lp-2d").click();await page.locator("#lp-view").screenshot({path:"planner-2d-mobile.png"});
await page.locator("#lp-fw").fill("100");await page.locator("#lp-item-apply").click();assert.equal(await page.locator("#lp-item-status").getAttribute("data-state"),"error");
await page.locator("#lp-fw").fill("1800");await page.locator("#lp-x").fill("3000");await page.locator("#lp-z").fill("100");await page.locator("#lp-item-apply").click();assert.equal(await page.locator("#lp-csv").isDisabled(),true);
await page.locator("#lp-x").fill("100");await page.locator("#lp-item-apply").click();assert.equal(await page.locator("#lp-csv").isEnabled(),true);
await page.locator("#lp-local-save").click();await page.locator("#lp-clear").click();assert.equal(await page.locator("#lp-csv").isDisabled(),true);
await page.locator("#lp-local-load").click();assert.equal(await page.locator("#lp-csv").isEnabled(),true);
const download=page.waitForEvent("download");await page.locator("#lp-csv").click();assert.equal((await download).suggestedFilename(),"LERIKA-Room-Summary.csv");
await page.locator("#lp-studio").click();await page.locator("#lab-ai-panel").waitFor({state:"visible"});assert.match(await page.locator("#lab-ai-photo-status").textContent(),/2 \/ 6 файлов/);
for(const [hash,id] of [["3d","lab-3d-panel"],["config","lab-config-panel"],["ai","lab-ai-panel"],["plan","lab-plan-panel"]]){await page.evaluate(h=>location.hash="#design-lab/"+h,hash);await page.locator("#"+id).waitFor({state:"visible"});}
assert.deepEqual(errors,[]);
console.log("Mobile browser, model validation, collision/export gate, save/load, CSV download, studio handoff and existing routes PASS");
}finally{await browser.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
