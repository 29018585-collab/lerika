const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){if(!/\bsrc=/.test(m[1])&&!/type="(?:application\/json|importmap)"/.test(m[1]))new vm.Script(m[2]);}
const context=vm.createContext({window:{}});
for(const key of ['window.LerikaFurniture=(()=>{','window.LerikaRoomPlanner=(()=>{']){
 const i=html.indexOf(key),j=html.indexOf('</script>',i);assert(i>=0&&j>i,key);vm.runInContext(html.slice(i,j),context);
}
const result=vm.runInContext(`
(()=>{
const P=window.LerikaRoomPlanner,r={w:5000,d:4000,h:2700},opening=[];
const table=P.item("table",1,1000,1000),rawLamp=P.item("tableLamp",2),lamp=P.freePosition(r,[table],opening,rawLamp);
if(!lamp)throw Error("lamp placement failed");
const list=[table,lamp],moved=P.changePlacement(r,list,opening,{...table,x:1500,z:1300});
const raised=P.changePlacement(r,list,opening,{...table,h:950});
const rotated=P.rotationCandidate(r,list,opening,table,1);
const rotatedList=rotated&&P.changePlacement(r,list,opening,rotated);
const impossible=P.changePlacement(r,list,opening,{...table,w:700,d:400,x:4900});
const noSupport=P.freePosition(r,[],opening,rawLamp);
const ceiling=P.freePosition(r,[],opening,P.item("pendant",3));
const mirror=P.freePosition(r,[],opening,P.item("mirror",4));
const shower=P.freePosition(r,[],opening,P.item("cornerShower",5));
const shower2=shower&&P.rotationCandidate(r,[shower],opening,shower,1);
const lampFields=P.editorSchema(lamp);
return {lamp,top:P.topSurface(table),moved:moved?.[1],raised:raised?.[1],rotated:rotatedList?.[1],noSupport:noSupport===null,impossible:impossible===null,orphan:!P.inspect(r,[lamp],[]).ok,ceiling,mirror,shower,shower2,glass:shower&&P.model(shower,false,true).boxes.filter(b=>b.visualSurface==="glass").length,hidden:lampFields.hiddenDimensions,elevation:lampFields.elevation,lampBase:lampFields.lampBase,old:P.inspect(r,[table,rawLamp],[]).ok,valid:P.inspect(r,list,[]).ok};
})()
`,context);
assert.equal(result.noSupport,true);
assert.equal(result.lamp.supportId,1);
assert.equal(result.lamp.elev,result.top.y);
assert.equal(result.moved.x,result.lamp.x+500);
assert.equal(result.moved.z,result.lamp.z+300);
assert.equal(result.raised.elev,result.lamp.elev+200);
assert.equal(result.rotated.rot,1);
assert.equal(result.impossible,true);
assert.equal(result.orphan,true);
assert.equal(result.valid,true);
assert.equal(result.old,false);
assert.equal(result.ceiling.elev,2250);
assert.equal(result.mirror.z,0);
assert.equal(result.shower.x,0);assert.equal(result.shower.z,0);
assert.equal(result.shower2.rot,1);assert.equal(result.shower2.x,4100);
assert(result.glass>=2);
assert(result.hidden.includes("d"));assert.equal(result.elevation,false);assert.equal(result.lampBase,true);
console.log("PASS support placement, height, movement, rotation, orphan protection, ceiling, wall, corner shower and lamp schema");
