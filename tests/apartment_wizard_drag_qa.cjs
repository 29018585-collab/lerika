const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){if(!/\bsrc=/.test(m[1])&&!/type="(?:application\/json|importmap)"/.test(m[1]))new vm.Script(m[2]);}
const slice=(a,b)=>{const i=html.indexOf(a),j=html.indexOf(b,i);assert(i>=0&&j>i,a);return html.slice(i,j)};
const context=vm.createContext({window:{LerikaFurniture:{presets:{}}}});
vm.runInContext(slice('window.LerikaRoomPlanner=(()=>{','</script>'),context);
vm.runInContext('const P=window.LerikaRoomPlanner;\n'+slice('function apartmentOverlap(a,b)','function updateRoomGeometry')+slice('function buildApartmentDraft(spec)','function applyApartmentDraft(spec,layout,doorOffsets)')+slice('function sharedWall(a,b)','function connectRooms('),context);
const result=vm.runInContext(String.raw`
(()=>{
 const spec={height:2700,partition:160,corridorDepth:1500,corridorLength:0,doorWidth:900,rooms:[{name:"Комната 1",w:4000,d:3500,side:"auto"},{name:"Комната 2",w:3500,d:3000,side:"auto"},{name:"Кухня",w:3500,d:3000,side:"auto"},{name:"Ванная",w:2400,d:2200,side:"auto"}]};
 const auto=buildApartmentDraft(spec),layout=auto.rooms.map(r=>({id:r.id,x:r.x,z:r.z,rot:false}));
 const manual=manualApartmentDraft(spec,layout),hall=manual.rooms.find(r=>r.id===1);
 const bath=manual.rooms.find(r=>r.id===5),moved=layout.map(r=>r.id===5?{...r,x:r.x+200}:r);
 const movedDraft=manualApartmentDraft(spec,moved),rotated=manualApartmentDraft(spec,layout.map(r=>r.id===5?{...r,rot:true,z:r.z+2400-2200-400}:r));
 const bad=manualApartmentDraft(spec,layout.map(r=>r.id===5?{...r,x:layout[1].x,z:layout[1].z}:r));
 const disconnected=manualApartmentDraft(spec,layout.map(r=>r.id===5?{...r,x:50000,z:50000}:r));
 const link=manual.links.find(l=>l.a==="Коридор"||l.b==="Коридор");
 const changed=manualApartmentDraft(spec,layout,{[link.key]:0});
 const openingsMatch=draft=>draft.rooms.every(a=>a.plan.openings.every(o=>draft.rooms.some(b=>a!==b&&sharedWall(a,b).some(p=>p.aw===o.wall&&b.plan.openings.some(v=>v.wall===p.bw&&o.offset+p.ao===v.offset+p.bo&&o.w===v.w)))));
 return {autoArea:auto.area,manualArea:manual.area,connected:manual.connected,links:manual.links.length,movedConnected:movedDraft.connected,movedX:movedDraft.rooms?.find(r=>r.id===5)?.x,expectedX:bath.x+200,movedArea:movedDraft.area,rotatedArea:rotated.area,rotatedDims:rotated.rooms?.find(r=>r.id===5)?.plan.r,overlapRejected:!!bad.error,disconnected:!!disconnected.warning,doorOffset:changed.links?.find(l=>l.key===link.key)?.offset,paired:openingsMatch(manual)&&openingsMatch(movedDraft)&&openingsMatch(changed)};
})()
`,context);
assert.equal(result.autoArea,result.manualArea);
assert.equal(result.connected,true);
assert.equal(result.links,4);
assert.equal(result.movedConnected,true);
assert.equal(result.movedX,result.expectedX);
assert.equal(result.movedArea,result.autoArea);
assert.equal(result.rotatedArea,result.autoArea);
assert.equal(result.rotatedDims.w,2200);
assert.equal(result.rotatedDims.d,2400);
assert.equal(result.overlapRejected,true);
assert.equal(result.disconnected,true);
assert.equal(result.doorOffset,0);
assert.equal(result.paired,true);
console.log('PASS: syntax, area, movement, rotation, wall collision, disconnected rooms, paired doors',JSON.stringify(result));
