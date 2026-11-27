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
