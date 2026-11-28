/* LERIKA V5.37 — experimental WebGL adapter. All dimensions in millimetres.
   Three.js r180 is vendored locally under MIT. This file never changes the
   production model, item IDs, export records, geometry or local projects. */
import * as THREE from "./vendor/three-r180/three.module.min.js";

const KEY="lerika-graphics-v537";
const modes=["auto","economy","high","software"];
let mode="auto",renderer=null,geometry=null,failed=false,last="software",reason="";
try{const saved=localStorage.getItem(KEY);if(modes.includes(saved))mode=saved}catch(_){}
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const add=(a,b,s=1)=>a.map((v,i)=>v+b[i]*s);
function turned(b,p,inverse=false){
 if(!b.hinge)return p.slice();
 const [x,z]=b.hinge,angle=(b.angle||0)*(inverse?-1:1),c=Math.cos(angle),s=Math.sin(angle),dx=p[0]-x,dz=p[2]-z;
 return [x+dx*c-dz*s,p[1],z+dx*s+dz*c];
}
export function frameFor(boxes,W,H,view={}){
 if(!Array.isArray(boxes)||!boxes.length||boxes.length>6000||!(W>0&&H>0))return null;
 const yaw=view.yaw??.56,pitch=view.pitch??.30,zoom=view.zoom??1;
 if(![yaw,pitch,zoom].every(Number.isFinite)||zoom<=0||Math.abs(Math.sin(pitch))<.01)return null;
 const sy=Math.sin(yaw),cy=Math.cos(yaw),sp=Math.sin(pitch),cp=Math.cos(pitch);
 const right=[cy,0,-sy],up=[-sy*sp,cp,-cy*sp],dir=[sy*cp,sp,cy*cp];
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(const b of boxes){
  if(![b.x,b.y,b.z,b.a,b.b,b.c].every(Number.isFinite)||Math.min(b.a,b.b,b.c)<=0||b.hinge&&(!Array.isArray(b.hinge)||b.hinge.length!==2||!b.hinge.every(Number.isFinite)||!Number.isFinite(b.angle)))return null;
  for(const x of [b.x,b.x+b.a])for(const y of [b.y,b.y+b.b])for(const z of [b.z,b.z+b.c]){
   const p=turned(b,[x,y,z]),q=[dot(p,right),dot(p,up),dot(p,dir)];
   for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],q[j]);hi[j]=Math.max(hi[j],q[j])}
  }
 }
 const scale=Math.min(W*.79/Math.max(1,hi[0]-lo[0]),H*.73/Math.max(1,hi[1]-lo[1]))*zoom;
 if(!Number.isFinite(scale)||scale<=0)return null;
 const u=(lo[0]+hi[0])/2,v=(lo[1]+hi[1])/2+H*.03/scale,dep=(lo[2]+hi[2])/2;
 const center=add(add(right.map(x=>x*u),up,v),dir,dep);
 const span=Math.max(1000,hi[2]-lo[2],hi[0]-lo[0],hi[1]-lo[1]);
 const distance=span*2+1000,eye=add(center,dir,distance);
 return {W,H,right,up,dir,center,eye,span,distance,scale,sy,cy,sp,cp,
  floor(dx,dy){const u=dx/scale,v=dy/(scale*sp);return [u*cy+v*sy,-u*sy+v*cy]},
  plane(dx,dy){const u=dx/scale,v=dy/scale;return [u*cy+v*sy*sp,-v*cp,-u*sy+v*cy*sp]}
 };
}
// Ray/box intersection in the original local coordinate system; walls
// occlude furniture, and a rotated open door remains attached to its hinge.
export function hitFrame(frame,boxes,x,y){
 if(!frame||x<0||y<0||x>=frame.W||y>=frame.H)return null;
 const origin=add(add(frame.eye,frame.right,(x+.5-frame.W/2)/frame.scale),frame.up,(frame.H/2-y-.5)/frame.scale);
 const ray=frame.dir.map(v=>-v);let nearest=Infinity,owner=null;
 for(const b of boxes){
  const o=turned(b,origin,true),r=b.hinge?add(turned(b,add(origin,ray),true),o,-1):ray;
  let t0=0,t1=Infinity;const p=[b.x,b.y,b.z],q=[b.x+b.a,b.y+b.b,b.z+b.c];
  for(let i=0;i<3;i++){
   if(Math.abs(r[i])<1e-10){if(o[i]<p[i]||o[i]>q[i]){t0=Infinity;break}continue}
   let a=(p[i]-o[i])/r[i],c=(q[i]-o[i])/r[i];if(a>c)[a,c]=[c,a];
   t0=Math.max(t0,a);t1=Math.min(t1,c);if(t0>t1)break;
  }
  if(Number.isFinite(t0)&&t0<=t1&&t0<nearest){nearest=t0;owner=Number.isInteger(b.pickId)&&b.pickId>0?b.pickId:null}
 }
 return owner;
}
function setMode(next){if(!modes.includes(next))return false;mode=next;try{localStorage.setItem(KEY,next)}catch(_){}return true}
function status(){return {mode,last,reason,revision:THREE.REVISION,failed}}
function disposeRenderer(){try{geometry?.dispose();renderer?.dispose()}catch(_){}geometry=null;renderer=null}
function ensureRenderer(){
 if(failed)return null;if(renderer)return renderer;
 try{
  const c=document.createElement("canvas"),gl=c.getContext("webgl2",{alpha:true,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:true,powerPreference:"default"});
  if(!gl){failed=true;reason="WebGL 2 недоступен";return null}
  renderer=new THREE.WebGLRenderer({canvas:c,context:gl,alpha:true,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:true});
  renderer.setPixelRatio(1);renderer.setClearColor(0x000000,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.NoToneMapping;geometry=new THREE.BoxGeometry(1,1,1);
  c.addEventListener("webglcontextlost",e=>{e.preventDefault();failed=true;reason="Потерян контекст WebGL";last="software"});
  return renderer;
 }catch(_){failed=true;reason="Не удалось запустить WebGL";disposeRenderer();return null}
}
function render(ctx,canvas,boxes,view,selected){
 if(mode==="software"){last="software";reason="Выбран резервный движок";return null}
 const W=canvas.width,H=canvas.height,frame=frameFor(boxes,W,H,view);
 if(!frame){last="software";reason="Сцена вне лимитов экспериментального движка";return null}
 const engine=ensureRenderer();if(!engine){last="software";return null}
 const materials=[],meshes=[],scene=new THREE.Scene();
 try{
  const cap=mode==="economy"?720:mode==="high"?1600:1100,ratio=Math.min(1,cap/Math.max(W,H));
  engine.setSize(Math.max(1,Math.round(W*ratio)),Math.max(1,Math.round(H*ratio)),false);
  const c=new THREE.OrthographicCamera(-W/2/frame.scale,W/2/frame.scale,H/2/frame.scale,-H/2/frame.scale,1,frame.distance+frame.span*3);
  c.position.set(...frame.eye);c.up.set(0,1,0);c.lookAt(...frame.center);c.updateProjectionMatrix();c.updateMatrixWorld(true);
  scene.add(new THREE.HemisphereLight(0xfff6e8,0x897d71,1.3));
  const key=new THREE.DirectionalLight(0xfff4e3,2.0);key.position.set(...add(frame.center,[.55,1,.65],frame.span));scene.add(key,key.target);key.target.position.set(...frame.center);
  const fill=new THREE.DirectionalLight(0xdce9ff,.65);fill.position.set(...add(frame.center,[-1,.55,-.4],frame.span));scene.add(fill);
  engine.shadowMap.enabled=mode==="high"&&boxes.length<=2500;
  if(engine.shadowMap.enabled){engine.shadowMap.type=THREE.PCFSoftShadowMap;key.castShadow=true;key.shadow.mapSize.set(1024,1024);const span=frame.span*1.25;Object.assign(key.shadow.camera,{left:-span,right:span,top:span,bottom:-span,near:1,far:frame.span*5});key.shadow.camera.updateProjectionMatrix();key.shadow.bias=-.00015;key.shadow.normalBias=3}
  const groups=new Map();
  for(const b of boxes){
   const col=typeof b.color==="string"&&/^#[a-f0-9]{6}$/i.test(b.color)?b.color:"#c6b7a3",tex=b.texture||window.LerikaDecors?.find(col)?.texture||"solid",picked=selected!=null&&b.pickId===selected;
   const k=[col,tex,picked].join("|");if(!groups.has(k))groups.set(k,{col,tex,picked,boxes:[]});groups.get(k).boxes.push(b)
  }
  const dummy=new THREE.Object3D();
  for(const group of groups.values()){
   const color=new THREE.Color(group.col);if(group.picked)color.lerp(new THREE.Color("#d9a24d"),.23);
   const rough=group.tex==="metal"?.36:group.tex==="fabric"?.96:group.tex==="stone"?.79:group.tex==="marble"?.42:.72;
   const mat=new THREE.MeshStandardMaterial({color,roughness:rough,metalness:group.tex==="metal"?.18:0});materials.push(mat);
   const mesh=new THREE.InstancedMesh(geometry,mat,group.boxes.length);meshes.push(mesh);
   for(const [i,b] of group.boxes.entries()){
    const p=turned(b,[b.x+b.a/2,b.y+b.b/2,b.z+b.c/2]);dummy.position.set(...p);dummy.rotation.set(0,b.hinge?-b.angle:0,0);dummy.scale.set(b.a,b.b,b.c);dummy.updateMatrix();mesh.setMatrixAt(i,dummy.matrix)
   }
   mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();mesh.castShadow=engine.shadowMap.enabled;mesh.receiveShadow=engine.shadowMap.enabled;scene.add(mesh)
  }
  engine.render(scene,c);
  if(engine.getContext().isContextLost())throw Error("context lost");
  ctx.drawImage(engine.domElement,0,0,W,H);last="webgl";reason="";
  return {scale:frame.scale,floor:frame.floor,plane:frame.plane,hit:(x,y)=>hitFrame(frame,boxes,x,y),engine:"webgl"};
 }catch(_){failed=true;last="software";reason="Ошибка WebGL — включена резервная отрисовка";disposeRenderer();return null}
 finally{for(const m of meshes)m.dispose();for(const m of materials)m.dispose();for(const light of scene.children)if(light.shadow?.map)light.shadow.map.dispose()}
}
window.LerikaGraphics={render,setMode,status};
window.dispatchEvent(new Event("lerika-graphics-ready"));
