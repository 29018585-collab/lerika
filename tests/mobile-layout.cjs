"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html"),server=http.createServer((req,res)=>{if(req.url==="/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html)}else{res.writeHead(404);res.end()}});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const browser=await chromium.launch({headless:true});try{
for(const width of [320,360,384,390,480,600,768,1280]){
const p=await browser.newPage({viewport:{width,height:844},hasTouch:width<721});
const base="http://127.0.0.1:"+server.address().port+"/";
await p.goto(base+"#home",{waitUntil:"domcontentloaded"});
await p.locator(".client-entry-link").waitFor({state:"visible"});
assert.equal(await p.locator("#client").isVisible(),false);
assert.equal(await p.locator("#client-form").isVisible(),false);
await p.locator(".client-entry-link").click();
await p.locator("#client-form").waitFor({state:"visible"});
assert.equal(await p.locator("#catalog").isVisible(),false);
assert.equal(await p.locator(".client-entry-link").isVisible(),false);
assert.equal(await p.locator("#client").locator(".client-guide").isVisible(),true);
assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),"client screen overflow "+width);
await p.locator("#client-login-tab").click();
assert.equal(await p.locator("#client-name").isVisible(),false);
await p.locator("#client-register-tab").click();
assert.equal(await p.locator("#client-name").isVisible(),true);
await p.locator('#client a[href="#home"]').click();
await p.locator(".client-entry-link").waitFor({state:"visible"});
await p.locator(".menu-button").click();
await p.locator('#navigation a[href="#client"]').click();
await p.locator("#client-form").waitFor({state:"visible"});
assert.equal(await p.locator("#navigation").isVisible(),false);
await p.goBack();
await p.locator(".client-entry-link").waitFor({state:"visible"});
console.log("PASS isolated client screen and menu at "+width+"px");
for(const [route,selector] of [["plan","#lab-plan-panel"],["engineering","#le-panel"],["order","#lo-panel"],["3d","#lab-3d-panel"],["ai","#lab-ai-panel"],["config","#lab-config-panel"]]){
await p.goto("http://127.0.0.1:"+server.address().port+"/#design-lab/"+route,{waitUntil:"domcontentloaded"});
await p.locator(selector).waitFor({state:"visible"});
const issues=await p.locator(selector).evaluate(root=>{
const errors=[];const buttons=[...root.querySelectorAll(".lab-actions > .lab-btn, .lp-mode > .lab-btn")].filter(b=>b.getClientRects().length);
for(const b of buttons){const r=b.getBoundingClientRect();if(b.scrollWidth>b.clientWidth+2||r.left< -2||r.right>innerWidth+2)errors.push(b.textContent.trim()+": overflow "+b.scrollWidth+"/"+b.clientWidth);const range=document.createRange();range.selectNodeContents(b);for(const t of range.getClientRects())if(t.left<r.left-2||t.right>r.right+2)errors.push(b.textContent.trim()+": text outside button");}
for(const group of root.querySelectorAll(".lab-actions,.lp-mode")){const rects=[...group.querySelectorAll(":scope > .lab-btn")].filter(b=>b.getClientRects().length).map(b=>b.getBoundingClientRect());for(let i=0;i<rects.length;i++)for(let j=0;j<i;j++)if(Math.min(rects[i].right,rects[j].right)-Math.max(rects[i].left,rects[j].left)>1&&Math.min(rects[i].bottom,rects[j].bottom)-Math.max(rects[i].top,rects[j].top)>1)errors.push("overlapping buttons");}
if(innerWidth<=720)for(const t of root.querySelectorAll(".lp-table")){if(t.scrollWidth>t.clientWidth+2)errors.push("summary table clipped");}
return errors});
assert.deepEqual(issues,[],width+"px "+route);if(width<=480&&route==="plan"){const rects=await p.locator("#lp-csv,#lp-local-save,#lp-local-load,#lp-studio,#le-from-plan").evaluateAll(bs=>bs.map(b=>({x:b.getBoundingClientRect().x,y:b.getBoundingClientRect().y,w:b.getBoundingClientRect().width})));assert.equal(new Set(rects.map(r=>Math.round(r.y))).size,5);assert.ok(rects.every(r=>r.w>200));}
}
await p.close();console.log("PASS responsive buttons and tables at "+width+"px");
}
}finally{await browser.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
