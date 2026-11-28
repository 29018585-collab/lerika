/* Perspective walk renderer: clipped triangles, reciprocal-depth buffer, stable local UV.
   Separate from the orthographic engineering renderer and collision geometry. */
const tiles=new Map(),clamp=v=>Math.max(0,Math.min(255,v));
function tile(kind){
 if(!kind||kind==="solid"||kind==="paint")return null;
 if(tiles.has(kind))return tiles.get(kind);
 const t=new Int8Array(65536);let seed=17;const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296};
 for(let y=0;y<256;y++)for(let x=0;x<256;x++){let v=0;
 switch(kind){
 case "wood":v=12*Math.sin(x*.31+1.6*Math.sin(y*.025))+5*Math.sin(x*1.1+Math.sin(y*.052))+4*(rand()-.5);break;
 case "marble":v=16*Math.pow(Math.sin(x*.043+y*.081+1.5*Math.sin(y*.025)),13);break;
 case "stone":v=22*(rand()-.5);break;
 case "fabric":v=(x%4===0||y%4===0?-8:3)+4*(rand()-.5);break;
 case "metal":v=10*Math.sin(x*.026);break;
 case "tile":v=x%128<2||y%128<2?-35:3*(rand()-.5);break;
 case "planks":v=x%64<2||y%256<2?-25:10*Math.sin(x*.4+1.5*Math.sin(y*.025));break;
 case "wallpaper":v=9*Math.sin(x*.11)+4*Math.sin(x*.23+y*.06);break;
 case "plaster":v=12*(rand()-.5)+4*Math.sin(x*.15+y*.12);break;
 }t[y*256+x]=Math.round(v)}tiles.set(kind,t);return t
}
const faces=[[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]],shade=[.87,.93,.74,1,.83,.91];
export function drawWalk(canvas,scene,cam){
 const W=canvas.width,H=canvas.height,g=canvas.getContext("2d");if(!cam)return;
 const img=g.createImageData(W,H),pix=img.data,depth=new Float32Array(W*H);
 for(let i=0;i<pix.length;i+=4){pix[i]=42;pix[i+1]=39;pix[i+2]=36;pix[i+3]=255}
 const cs=Math.cos(cam.yaw),sn=Math.sin(cam.yaw),cp=Math.cos(cam.pitch||0),sp=Math.sin(cam.pitch||0),f=Math.min(W*.69,H*.99),near=25,eye=1600;
 const transform=(x,y,z)=>{const a=x-cam.x,b=z-cam.z,h=y-eye,d=a*sn+b*cs;return [a*cs-b*sn,h*cp-d*sp,d*cp+h*sp]};
 function clip(ps){const out=[];for(let i=0;i<ps.length;i++){const a=ps[i],b=ps[(i+1)%ps.length],ia=a[2]>=near,ib=b[2]>=near;if(ia)out.push(a);if(ia!==ib){const t=(near-a[2])/(b[2]-a[2]);out.push(a.map((v,k)=>v+(b[k]-v)*t))}}return out}
 const project=p=>{const q=1/p[2];return [W/2+p[0]*q*f,H/2-p[1]*q*f,q,p[3]*q,p[4]*q]};
 function tri(a,b,c,base,tex){
  const den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(Math.abs(den)<1e-8)return;
  const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(W-1,Math.ceil(Math.max(a[0],b[0],c[0]))),y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(H-1,Math.ceil(Math.max(a[1],b[1],c[1])));
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){const px=x+.5,py=y+.5,t=((b[1]-c[1])*(px-c[0])+(c[0]-b[0])*(py-c[1]))/den,u=((c[1]-a[1])*(px-c[0])+(a[0]-c[0])*(py-c[1]))/den,v=1-t-u;if(t< -1e-8||u< -1e-8||v< -1e-8)continue;const q=t*a[2]+u*b[2]+v*c[2],i=y*W+x;if(q<=depth[i])continue;depth[i]=q;let shift=0;if(tex){const U=(t*a[3]+u*b[3]+v*c[3])/q,V=(t*a[4]+u*b[4]+v*c[4])/q;shift=tex[((Math.floor(V/3)&255)<<8)+(Math.floor(U/3)&255)]}const j=i*4;pix[j]=clamp(base[0]+shift);pix[j+1]=clamp(base[1]+shift);pix[j+2]=clamp(base[2]+shift)}
 }
 for(const b of scene.renderBoxes||scene.boxes){
  const {x,y,z,a,b:h,c:d}=b;if(![x,y,z,a,h,d].every(Number.isFinite)||Math.min(a,h,d)<=0)continue;
  const local=[[0,0,0],[a,0,0],[a,h,0],[0,h,0],[0,0,d],[a,0,d],[a,h,d],[0,h,d]];
  const ps=local.map(([dx,dy,dz])=>{let X=x+dx,Z=z+dz;if(b.hinge){const [hx,hz]=b.hinge,s=Math.sin(b.angle||0),c=Math.cos(b.angle||0),xx=X-hx,zz=Z-hz;X=hx+xx*c-zz*s;Z=hz+xx*s+zz*c}return transform(X,y+dy,Z)});
  const col=/^#[0-9a-f]{6}$/i.test(b.color)?parseInt(b.color.slice(1),16):0xc6b7a3,tex=tile(b.texture||globalThis.LerikaDecors?.find(b.color)?.texture);
  for(let j=0;j<6;j++){const p=clip(faces[j].map(k=>{const [dx,dy,dz]=local[k],rot=b.textureRotation||0,U=rot===0?dx:rot===1?dz:rot===2?a-dx:d-dz,V=rot===0?dz:rot===1?a-dx:rot===2?d-dz:dx;return [...ps[k],j===2||j===3?U+ x:U+V+x+z,j===2||j===3?V+z:dy+y]})).map(project);if(p.length<3)continue;
   const base=[col>>16&255,col>>8&255,col&255].map(v=>Math.round(v*shade[j]));for(let k=1;k+1<p.length;k++)tri(p[0],p[k],p[k+1],base,tex)
  }
 }
 g.putImageData(img,0,0);g.fillStyle="rgba(25,20,16,.65)";g.fillRect(8,8,194,20);g.fillStyle="#fff";g.font="bold 12px system-ui";g.fillText("ЛЕРИКА / ВИД ИЗНУТРИ",15,22);
}
