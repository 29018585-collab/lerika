"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html"),server=http.createServer((req,res)=>{if(req.url==="/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html)}else{res.writeHead(404);res.end()}});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const browser=await chromium.launch({headless:true});try{
const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,acceptDownloads:true});const errors=[];page.on("pageerror",e=>errors.push(e.message));
await page.goto("http://127.0.0.1:"+server.address().port+"/#design-lab/engineering",{waitUntil:"domcontentloaded"});
await page.locator("#le-view").waitFor({state:"visible"});assert.equal(await page.locator("#le-type option").count(),12);
assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),"mobile overflow");
for(const v of ["side","top","section","explode","front"])await page.locator('[data-le-view="'+v+'"]').click();
await page.locator("#le-w").fill("100");assert.equal(await page.locator("#le-pdf").isDisabled(),true);await page.locator("#le-build").click();assert.equal(await page.locator("#le-status").getAttribute("data-state"),"error");
await page.locator("#le-w").fill("1800");await page.locator("#le-build").click();assert.equal(await page.locator("#le-pdf").isEnabled(),true);
let promise=page.waitForEvent("download");await page.locator("#le-pdf").click();let d=await promise;assert.equal(d.suggestedFilename(),"LERIKA-Drawings.pdf");let b=fs.readFileSync(await d.path());assert.ok(b.toString("ascii",0,8).startsWith("%PDF"));assert.ok(b.includes(Buffer.from("/Count 5")));
promise=page.waitForEvent("download");await page.locator("#le-dxf").click();d=await promise;assert.match(fs.readFileSync(await d.path(),"utf8"),/EOF/);
await page.locator("#le-order").click();await page.locator("#lo-panel").waitFor({state:"visible"});assert.match(await page.locator("#lo-files-status").textContent(),/2 \/ 10 файлов/);
await page.locator("#lo-files").setInputFiles([{name:"sample.zip",mimeType:"application/zip",buffer:Buffer.from("PK\u0003\u0004sample")},{name:"reference.png",mimeType:"image/png",buffer:Buffer.from("reference")}]);assert.match(await page.locator("#lo-files-status").textContent(),/4 \/ 10 файлов/);
await page.evaluate(()=>location.hash="#design-lab/3d");await page.locator("#lab3-panel, #lab-3d-panel").first().waitFor({state:"visible"});await page.locator("#le-from-3d").click();await page.locator("#le-panel").waitFor({state:"visible"});assert.match(await page.locator("#le-source").textContent(),/3D-конструктор/);
await page.evaluate(()=>location.hash="#design-lab/plan");await page.locator("#lab-plan-panel").waitFor({state:"visible"});await page.locator("#le-from-plan").click();await page.locator("#le-panel").waitFor({state:"visible"});assert.match(await page.locator("#le-source").textContent(),/Планировщик/);assert.deepEqual(errors,[]);
console.log("Engineering mobile views, PDF/DXF, invalidation, order attachments, 3D and planner handoff PASS");
}finally{await browser.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
