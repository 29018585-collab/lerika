"use strict";
const {chromium}=require("playwright"),assert=require("node:assert/strict"),fs=require("node:fs"),http=require("node:http");
const html=fs.readFileSync("index.html"),admin=fs.readFileSync("cabinet/templates/admin.html");
const rows=[
 {id:"abcdef1234567890abcdef1234567890",request_number:"L-000123",request_source:"project",request_created:100,category:1,title:"Синтетическая заявка 123",description:"Тест",stage:1,status:"work",published:0,files:[]},
 {id:"bcdefa1234567890bcdefa1234567890",request_number:"L-000124",request_source:"config",request_created:200,category:1,title:"Синтетическая заявка 124",description:"Тест",stage:1,status:"work",published:0,files:[]}
];
const json=(res,data)=>{res.writeHead(200,{"Content-Type":"application/json"});res.end(JSON.stringify(data))};
const server=http.createServer((req,res)=>{
 if(req.method!=="GET"){res.writeHead(405);res.end();return}
 const p=new URL(req.url,"http://127.0.0.1").pathname;
 if(p==="/showroom/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(html);return}
 if(p==="/cabinet/"){res.writeHead(200,{"Content-Type":"text/html; charset=utf-8"});res.end(admin);return}
 if(p==="/session"){json(res,{csrf:"synthetic"});return}
 if(p==="/api/projects"){json(res,{projects:rows,covers:[],categories:["Кухни"],stages:["Замер"]});return}
 if(p==="/public/prices"){json(res,{entries:[],updated:0});return}
 if(p==="/public/portfolio"){json(res,{projects:[],covers:{}});return}
 if(/^\/static\/(?:admin\.js|admin\.css|install\.js)$/.test(p)){res.writeHead(200,{"Content-Type":p.endsWith(".js")?"text/javascript":"text/css"});res.end(fs.readFileSync("cabinet"+p));return}
 if(/^\/showroom\/(?:scene|public)-[a-z0-9-]+\.webp$/.test(p)){const f=p.split("/").pop();if(fs.existsSync(f)){res.writeHead(200,{"Content-Type":"image/webp"});res.end(fs.readFileSync(f));return}}
 res.writeHead(404);res.end();
});
(async()=>{await new Promise(r=>server.listen(0,"127.0.0.1",r));const b=await chromium.launch({headless:true});try{
 const base="http://127.0.0.1:"+server.address().port,p=await b.newPage({viewport:{width:390,height:844}}),errors=[];
 p.on("pageerror",e=>errors.push(e.message));await p.route("**/*",route=>route.request().url().startsWith(base+"/")?route.continue():route.abort());
 await p.goto(base+"/cabinet/");await p.locator("#workspace").waitFor({state:"visible"});await p.locator("#viewRequests").click();
 assert.equal(await p.locator("#requestList .request-item").count(),2);
 await p.locator("#requestSearch").fill("L-000123");assert.equal(await p.locator("#requestList .request-item").count(),1);assert.match(await p.locator("#requestList").innerText(),/L-000123/);
 await p.getByRole("button",{name:"Открыть заявку",exact:true}).click();assert.match(await p.locator("#requestOrigin").innerText(),/L-000123.*Коллекция изделий/);assert.equal(await p.locator("#publish").isVisible(),false);
 await p.locator("#requestSearch").fill("bcdefa123456");assert.match(await p.locator("#requestList").innerText(),/L-000124/);assert.equal(await p.locator("#requestList .request-item").count(),1);
 await p.locator("#requestSearch").fill("");await p.getByRole("button",{name:"Коллекция изделий · 1",exact:true}).click();assert.match(await p.locator("#requestList").innerText(),/L-000123/);assert.equal(await p.locator("#requestList .request-item").count(),1);
 await p.goto(base+"/showroom/");const assets=fs.readdirSync(".").filter(f=>/^(?:scene|public)-[a-z0-9-]+\.webp$/.test(f));
 assert.equal(assets.length,16);
 const decoded=await p.evaluate(async names=>Promise.all(names.map(async name=>{const img=new Image();img.src=name;await img.decode();return [name,img.naturalWidth,img.naturalHeight]})),assets);
 assert.ok(decoded.every(v=>v[1]>0&&v[2]>0));assert.deepEqual(decoded.find(v=>v[0].startsWith("public-kitchen-")).slice(1),[1080,1400]);assert.deepEqual(decoded.find(v=>v[0].startsWith("public-stairs-")).slice(1),[1080,1020]);
 assert.equal(await p.locator("#kitchen img").count(),5);
 assert.equal(await p.locator("#kitchen .lit").evaluateAll(v=>new Set(v.map(x=>x.src)).size),1);
 await p.locator("#kitchen .switch").click();assert.equal(await p.locator("#kitchen").evaluate(e=>e.classList.contains("on")),true);
 assert.deepEqual(errors,[]);
 console.log("PASS V5.23 actual admin search/filter/number, legacy lookup, publication guard, 16 decoded WebP assets and illumination");
}finally{await b.close();server.close()}})().catch(e=>{console.error(e);server.close();process.exitCode=1});
