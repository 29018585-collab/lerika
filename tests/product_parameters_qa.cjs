const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){if(!/\bsrc=/.test(m[1])&&!/type="(?:application\/json|importmap)"/.test(m[1]))new vm.Script(m[2]);}
const context=vm.createContext({window:{}});
for(const key of ['window.LerikaFurniture=(()=>{','window.LerikaRoomPlanner=(()=>{','window.LerikaEngineering=(()=>{']){
 const i=html.indexOf(key),j=html.indexOf('</script>',i);assert(i>=0&&j>i,key);vm.runInContext(html.slice(i,j),context);
}
const result=vm.runInContext(`
(()=>{
const E=window.LerikaFurniture,P=window.LerikaRoomPlanner,Q=window.LerikaEngineering,r={w:5000,d:4000,h:2700};
const shelfItem=P.item("bookcase",1,100,100),count=g=>g.parts.filter(p=>p.name.toLowerCase().includes("полк")).reduce((s,p)=>s+p.qty,0);
const before=E.build(shelfItem),afterItem={...shelfItem,construction:{shelves:[2,3,4,4]}},after=E.build(afterItem),planned=P.model(afterItem),engineering=Q.build(afterItem);
const wardrobe=P.item("wardrobe",2),wardrobeModes={...wardrobe,config:["rail","shelves","drawers","mixed"]};
const table=P.item("table",3,3300,100),candidate=P.rotationCandidate(r,[table],[],table,1);
const blocked=P.rotationCandidate({w:1800,d:1000,h:2700},[{...table,x:0,z:0}],[],{...table,x:0,z:0},1);
const tested=Object.keys(P.catalog).map((type,i)=>{const a=P.item(type,i+1),q=P.editorSchema(a);return {type,valid:!!P.model(a),schema:!!q&&["w","h","d"].every(k=>Array.isArray(q[k])&&q[k][0]),shelves:q.shelfSlots.length}});
const shelfSlots=Object.fromEntries(["wardrobe","bookcase","kitchen","wallcab","hall","tv","table","bed","desk","sideboard","nightstand","bath","fridge","mirror"].map((t,i)=>[t,E.shelfSlots(P.item(t,i+10)).join(",")]));
return {tested,slots:shelfSlots,modeSlots:E.shelfSlots(wardrobeModes),before:count(before),after:count(after),planned:count(planned),engine:count(engineering),round:P.editorSchema(P.item("roundTable",4)),mirror:P.editorSchema(P.item("mirror",5)),rug:P.editorSchema(P.item("rug",6)),sofa:P.editorSchema(P.item("sofa",7)),built:P.editorSchema(P.item("builtOven",8)),candidate,blocked:blocked===null,candidateValid:!!candidate&&P.inspect(r,[candidate],[]).ok};
})()
`,context);
assert(result.tested.every(x=>x.schema));
assert(result.tested.length>=45);
assert.equal(result.slots.table,'');assert.equal(result.slots.bed,'');assert.equal(result.slots.desk,'');assert.equal(result.slots.sideboard,'');assert.equal(result.slots.fridge,'');
assert.equal(result.slots.bookcase,'0,1');assert.equal(result.slots.kitchen,'1,2');assert.equal(result.slots.wallcab,'0,1');assert.equal(result.slots.wardrobe,'0');assert.equal(result.modeSlots.join(','),'1');
assert.equal(result.before,8);assert.equal(result.after,5);assert.equal(result.planned,5);assert.equal(result.engine,5);
assert.equal(result.round.linkedDiameter,true);assert(result.round.hiddenDimensions.includes('d'));assert(result.mirror.hiddenDimensions.includes('d'));assert(result.rug.hiddenDimensions.includes('h'));assert.equal(result.sofa.elevation,false);assert.equal(result.built.sections,false);assert.equal(result.built.shelfSlots.length,0);
assert(result.candidateValid);assert.equal(result.candidate.rot,1);assert(result.blocked);
console.log('PASS product schemas',result.tested.length,'shelf slots, shared part counts, centred rotation, boundary rejection');
