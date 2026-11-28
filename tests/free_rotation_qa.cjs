const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){if(!/\bsrc=/.test(m[1])&&!/type="(?:application\/json|importmap)"/.test(m[1]))new vm.Script(m[2]);}
const context=vm.createContext({window:{}});
for(const key of ['window.LerikaFurniture=(()=>{','window.LerikaRoomPlanner=(()=>{']){
 const i=html.indexOf(key),j=html.indexOf('</script>',i);assert(i>=0&&j>i,key);vm.runInContext(html.slice(i,j),context);
}
const result=vm.runInContext(`
(()=>{
const P=window.LerikaRoomPlanner,r={w:4000,d:3500,h:2700},o=[];
const sofa=P.item("cornerLeft",1,100,900),block=P.item("wardrobe",2,100,0);
const list=[sofa,block],m=P.model(sofa),rot=P.rotationCandidate(r,list,o,sofa,1,true);
const turned=P.changePlacement(r,list,o,rot,true),report=P.inspect(r,turned,o);
const small={w:1800,d:1000,h:2700},table=P.item("table",3,0,0),forced=P.rotationCandidate(small,[table],o,table,1,true),strict=P.rotationCandidate(small,[table],o,table,1);
const moved=P.changePlacement(r,turned,o,{...turned[0],x:2200,z:1000},true);
const desk=P.item("desk",4,1000,1000),lamp=P.freePosition(r,[desk],o,P.item("tableLamp",5)),pair=[desk,lamp];
const d=P.rotationCandidate(r,pair,o,desk,1,true),pairTurn=P.changePlacement(r,pair,o,d,true);
const invalid=P.changePlacement(r,pair,o,{...lamp,x:3500,z:2500},true);
let round=[sofa];for(let i=0;i<4;i++){const a=round[0],b=P.rotationCandidate(r,round,o,a,(a.rot+1)%4,true);round=P.changePlacement(r,round,o,b,true)}
return {rot:rot.rot,center:[rot.x+P.model(rot).w/2,rot.z+P.model(rot).d/2],oldCenter:[sofa.x+m.w/2,sofa.z+m.d/2],bad:!report.ok,forced:forced.rot,strict:strict===null,forcedBad:!P.inspect(small,[forced],o).ok,moved:!!moved,pairTurn:!!pairTurn,attached:pairTurn?.[1].supportId,invalid:invalid===null,round:round[0],sofa};
})()
`,context);
assert.equal(result.rot,1);assert.deepEqual(result.center,result.oldCenter);
assert(result.bad);assert.equal(result.forced,1);assert(result.strict);assert(result.forcedBad);
assert(result.moved);assert(result.pairTurn);assert.equal(result.attached,4);assert(result.invalid);
assert.equal(result.round.rot,0);assert.equal(result.round.x,result.sofa.x);assert.equal(result.round.z,result.sofa.z);
console.log("PASS free rotation, overlapping draft, oversized room, four turns, recovery movement, attached objects");
