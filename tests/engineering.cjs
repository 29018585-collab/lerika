"use strict";
const fs=require("node:fs"),a=require("node:assert/strict");const html=fs.readFileSync("index.html","utf8");
const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);for(const s of scripts)if(s.trim())new Function(s);
const selected=["window.LerikaDecors=(()=>","window.LerikaFurniture=(()=>","window.LerikaEngineering=(()=>"].map(key=>scripts.find(s=>s.includes(key)));const w=new Function("const window={};"+selected.join("\n")+";return window")(),E=w.LerikaFurniture,Q=w.LerikaEngineering;let n=0;
function test(name,fn){fn();n++;console.log("PASS "+name)}
for(const [type,p] of Object.entries(E.presets)){test(type+" engineering geometry, orthographic, cut and area conservation",()=>{
const m=Q.build({type,w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16});a.ok(m);
for(const v of ["front","side","top","section"]){const q=Q.projection(m,v);a.ok(q.w>0&&q.h>0&&q.rects.length>0);for(const r of q.rects)a.ok(r.x>=-1e-6&&r.y>=-1e-6&&r.x+r.w<=q.w+1e-6&&r.y+r.h<=q.h+1e-6);a.match(Q.dxf(m,v),/EOF/)}
a.equal(Q.projection(m,"front").w,m.bounds.w);a.equal(Q.projection(m,"side").w,m.bounds.d);
a.deepEqual(Q.exploded(m,0).map(b=>[b.x,b.y,b.z]),m.boxes.map(b=>[b.x,b.y,b.z]));a.equal(Q.exploded(m,70).length,m.boxes.length);
for(const k of Object.keys(m.areas))a.ok(Math.abs(m.parts.filter(p=>p.material===k).reduce((s,p)=>s+p.area,0)-m.areas[k])<1e-8);
const c=Q.packing(m.parts,{w:2800,h:2070,margin:10,kerf:4,rotate:true});a.equal(c.sheets.reduce((n,s)=>n+s.placed.length,0)+c.oversize.length,m.parts.reduce((n,p)=>n+p.qty,0));
for(const s of c.sheets)for(let i=0;i<s.placed.length;i++){const p=s.placed[i];a.ok(p.x>=10&&p.y>=10&&p.x+p.w<=2790+1e-6&&p.y+p.h<=2060+1e-6);for(let j=0;j<i;j++){const v=s.placed[j];a.ok(p.x+p.w+4<=v.x+1e-6||v.x+v.w+4<=p.x+1e-6||p.y+p.h+4<=v.y+1e-6||v.y+v.h+4<=p.y+1e-6,"kerf overlap")}}
})}
test("invalid size rejected",()=>a.equal(Q.build({type:"wardrobe",w:100,h:2200,d:600,n:3,t:16,ft:16}),null));
test("packing does not silently omit oversized panel",()=>{const p={id:1,name:"Panel",a:3000,b:1000,qty:2,material:"Корпус",th:16};const c=Q.packing([p],{w:2800,h:2070,margin:10,kerf:4,rotate:true});a.equal(c.oversize.length,2)});
test("packing separates groups and thicknesses",()=>{const p={id:1,name:"Panel",a:100,b:100,qty:1,material:"Корпус",th:16};a.equal(Q.packing([p,{...p,id:2,th:18},{...p,id:3,material:"Фасад"}],{w:2800,h:2070,margin:10,kerf:4,rotate:false}).sheets.length,3)});
test("BUG-010 default wardrobe cut respects declared grain and fits all panels",()=>{
const p=E.presets.wardrobe,m=Q.build({type:"wardrobe",w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16});
for(const rotate of [false,true]){
 const cut=Q.packing(m.parts,{w:2800,h:2070,margin:10,kerf:4,rotate});
 a.equal(cut.oversize.length,0);a.equal(cut.sheets.reduce((n,s)=>n+s.placed.length,0),m.parts.reduce((n,p)=>n+p.qty,0));
 for(const sh of cut.sheets)for(const pos of sh.placed){const p=m.parts.find(p=>p.id===pos.id);if(p.grain==="a")a.equal(pos.rot,false);if(p.grain==="b")a.equal(pos.rot,true)}
}
});
test("BUG-013 invalid construction and fractional dimensions are rejected",()=>{
const m={type:"kitchen",w:300,h:400,d:250,n:1,t:18,ft:18,construction:{foot:200,top:"double",shelves:[8,8,8,8]}};
a.equal(E.build(m),null);a.equal(E.valid(m),false);
const p=E.presets.wardrobe,base={type:"wardrobe",w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16};
a.equal(E.valid(base),true);a.equal(E.valid({...base,w:1800.5}),false);
for(const [type,p] of Object.entries(E.presets))for(const foot of [0,100,200])for(const top of ["inset","overlay","double"])for(const count of [0,4,8]){
 const x={type,w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16,construction:{foot,top,shelves:[count,count,count,count]}};
 a.equal(E.valid(x),!!E.build(x));
}
});
test("BUG-026 engineering CSV uses decimal commas",()=>{
const p=E.presets.wardrobe,m=Q.build({type:"wardrobe",w:p[1],h:p[2],d:p[3],n:p[4],t:16,ft:16});
const lines=Q.csv(m).trim().split("\n").slice(1);a.ok(lines.length);for(const l of lines)a.match(l.split(";").at(-1),/^\d+,\d{5}$/);
});
console.log(n+" engineering core tests PASS");
