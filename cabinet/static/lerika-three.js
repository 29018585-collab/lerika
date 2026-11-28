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
function disposeRenderer(){try{geometry?.dispose();for(const t of maps.values())t.dispose();maps.clear();renderer?.dispose()}catch(_){}geometry=null;renderer=null}
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
// Local procedural maps, no network requests or external image licenses.
const maps=new Map();
export function surfaceFor(b,decor){
 const t=b.texture||decor||"solid",col=String(b.color||"").toLowerCase();
 if(b.visualSurface)return b.visualSurface;
 if(col==="#a8c0c6")return "mirror";
 if(["wood","planks","tile","fabric","stone","marble","metal","wallpaper","plaster"].includes(t))return t;
 return "solid";
}
export function radiusFor(b,tex){
 const m=Math.min(b.a,b.b,b.c);
 if(tex==="fabric")return Math.min(24,m*.23);
 if(b.pickId!=null&&!b.smooth&&["wood","solid","stone","marble","metal"].includes(tex))return Math.min(2,m*.12);
 return 0;
}
function surfaceMap(kind){
 if(maps.has(kind))return maps.get(kind);
 if(!["wood","planks","tile","fabric","stone","marble","metal","wallpaper","plaster","mirror","screen"].includes(kind))return null;
 const n=128,canvas=document.createElement("canvas");canvas.width=canvas.height=n;const g=canvas.getContext("2d");if(!g)return null;
 const im=g.createImageData(n,n);
 for(let y=0;y<n;y++)for(let x=0;x<n;x++){
  const hash=((Math.imul(x+37,374761393)^Math.imul(y+71,668265263))>>>0);const noise=((Math.imul(hash^(hash>>>13),1274126177)>>>0)%1024)/1023-.5;
  let v=240;
  if(kind==="wood"||kind==="planks"){const q=x+3*Math.sin(y*.049)+1.4*Math.sin(y*.098+x*.06);v=232+12*Math.sin(q*.44)+6*Math.sin(q*1.52)+noise*8;if(kind==="planks"&&(x%32===0||((y+(Math.floor(x/32)%2)*64)%128===0)))v=158}
  else if(kind==="fabric")v=229+7*Math.cos(x*Math.PI)+7*Math.cos(y*Math.PI)+noise*10;
  else if(kind==="tile")v=(x<2||y<2)?172:248+noise*5;
  else if(kind==="stone"||kind==="plaster")v=239+noise*24+5*Math.sin(x*.31)*Math.sin(y*.23);
  else if(kind==="marble"){const vein=Math.abs(Math.sin((x+y*.6+9*Math.sin(y*.08))*.13));v=249-45*Math.pow(1-vein,12)+noise*5}
  else if(kind==="metal")v=237+9*Math.sin(y*1.7)+noise*5;
  else if(kind==="wallpaper")v=240+9*Math.cos(x*Math.PI/16)+noise*3;
  else if(kind==="mirror"||kind==="screen")v=kind==="mirror"?192+55*y/n+15*Math.sin((x+y)*.035):205+35*y/n+7*Math.sin((x+y)*.06);
  const i=(y*n+x)*4;im.data[i]=im.data[i+1]=im.data[i+2]=Math.max(0,Math.min(255,v));im.data[i+3]=255;
 }
 g.putImageData(im,0,0);const tex=new THREE.CanvasTexture(canvas);tex.colorSpace=THREE.SRGBColorSpace;tex.wrapS=tex.wrapT=THREE.RepeatWrapping;tex.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());maps.set(kind,tex);return tex;
}
function shapedGeometry(a,h,d,r,tex){
 const g=new THREE.BoxGeometry(a,h,d,r>0?6:1,r>0?6:1,r>0?6:1);
 const pos=g.attributes.position,normal=g.attributes.normal,uv=g.attributes.uv;
 if(r>0){
  // Move face subdivisions toward the physical corner radius, then project
  // onto the rounded cuboid. The external envelope stays exactly a × h × d.
  const half=[a/2,h/2,d/2],inner=half.map(v=>v-r);
  for(let i=0;i<pos.count;i++){
   const p=[pos.getX(i),pos.getY(i),pos.getZ(i)].map((v,j)=>{const u=v/half[j];if(Math.abs(u)>.999999)return Math.sign(u)*half[j];if(Math.abs(u)<.000001)return 0;return Math.sign(u)*(inner[j]+r*(Math.abs(u)>.5?.5:0))});
   const q=p.map((v,j)=>Math.max(-inner[j],Math.min(inner[j],v))),n=p.map((v,j)=>v-q[j]),len=Math.hypot(...n);
   if(len>0){pos.setXYZ(i,...q.map((v,j)=>v+n[j]*r/len));normal.setXYZ(i,...n.map(v=>v/len))}
  }
 }
 const tile=({wood:450,planks:720,tile:500,fabric:90,stone:300,marble:650,metal:250,wallpaper:350,plaster:350})[tex];
 if(tile){const faceCount=pos.count/6;for(let i=0;i<uv.count;i++){const face=Math.floor(i/faceCount),dims=face<2?[d,h]:face<4?[a,d]:[a,h];uv.setXY(i,uv.getX(i)*Math.max(.15,dims[0]/tile),uv.getY(i)*Math.max(.15,dims[1]/tile))}}
 pos.needsUpdate=normal.needsUpdate=uv.needsUpdate=true;g.computeBoundingBox();g.computeBoundingSphere();return g;
}
function render(ctx,canvas,boxes,view,selected){
 if(mode==="software"){last="software";reason="Выбран резервный движок";return null}
 const W=canvas.width,H=canvas.height,frame=frameFor(boxes,W,H,view);
 if(!frame){last="software";reason="Сцена вне лимитов экспериментального движка";return null}
 const engine=ensureRenderer();if(!engine){last="software";return null}
 const materials=[],meshes=[],shapes=new Map(),scene=new THREE.Scene();
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
   const col=typeof b.color==="string"&&/^#[a-f0-9]{6}$/i.test(b.color)?b.color:"#c6b7a3",tex=surfaceFor(b,window.LerikaDecors?.find(col)?.texture),picked=selected!=null&&b.pickId===selected;
   const detail=mode!=="economy"&&boxes.length<=1800,rad=detail?radiusFor(b,tex):0;
   const shaped=detail&&(rad>0||["wood","planks","tile","fabric","stone","marble","metal","wallpaper","plaster"].includes(tex));
   let shape=shaped?[b.a,b.b,b.c,rad,tex].join("|"):"";
   if(shape&&!shapes.has(shape)){if(shapes.size>=100)shape="";else shapes.set(shape,shapedGeometry(b.a,b.b,b.c,rad,tex))}
   const k=[col,tex,picked,shape].join("|");if(!groups.has(k))groups.set(k,{col,tex,picked,shape,boxes:[]});groups.get(k).boxes.push(b)
  }
  const dummy=new THREE.Object3D();
  for(const group of groups.values()){
   const color=new THREE.Color(group.col);if(group.picked)color.lerp(new THREE.Color("#d9a24d"),.23);
   const rough=group.tex==="mirror"?.18:group.tex==="screen"?.23:group.tex==="metal"?.36:group.tex==="fabric"?.96:group.tex==="stone"?.79:group.tex==="marble"?.42:.72;
   const map=mode==="economy"?null:surfaceMap(group.tex);
   const mat=new THREE.MeshStandardMaterial({color,map,roughness:rough,metalness:group.tex==="metal"?.18:group.tex==="mirror"?.12:0,transparent:group.tex==="glass",opacity:group.tex==="glass"?.28:1,depthWrite:group.tex!=="glass"});materials.push(mat);
   const mesh=new THREE.InstancedMesh(shapes.get(group.shape)||geometry,mat,group.boxes.length);meshes.push(mesh);
   for(const [i,b] of group.boxes.entries()){
    const p=turned(b,[b.x+b.a/2,b.y+b.b/2,b.z+b.c/2]);dummy.position.set(...p);dummy.rotation.set(0,b.hinge?-b.angle:0,0);dummy.scale.set(...(group.shape?[1,1,1]:[b.a,b.b,b.c]));dummy.updateMatrix();mesh.setMatrixAt(i,dummy.matrix)
   }
   mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();mesh.castShadow=engine.shadowMap.enabled&&group.tex!=="glass";mesh.receiveShadow=engine.shadowMap.enabled&&group.tex!=="glass";scene.add(mesh)
  }
  engine.render(scene,c);
  if(engine.getContext().isContextLost())throw Error("context lost");
  ctx.save();try{ctx.setTransform(1,0,0,1,0,0);ctx.drawImage(engine.domElement,0,0,W,H)}finally{ctx.restore()}last="webgl";reason="";
  return {scale:frame.scale,floor:frame.floor,plane:frame.plane,hit:(x,y)=>hitFrame(frame,boxes,x,y),engine:"webgl"};
 }catch(_){failed=true;last="software";reason="Ошибка WebGL — включена резервная отрисовка";disposeRenderer();return null}
 finally{for(const m of meshes)m.dispose();for(const m of materials)m.dispose();for(const g of shapes.values())g.dispose();for(const light of scene.children)if(light.shadow?.map)light.shadow.map.dispose()}
}
window.LerikaGraphics={render,setMode,status};
window.dispatchEvent(new Event("lerika-graphics-ready"));
