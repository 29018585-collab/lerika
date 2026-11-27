(()=>{"use strict";
const meta=document.querySelector('meta[name="lerika-portfolio-api"]');
if(!meta||!meta.content)return;
let base;try{const u=new URL(meta.content);if(u.protocol!=="https:")return;base=u.origin}catch{return}
const stages=["Исходное помещение","Замеры и эскизы","3D-проект","Изготовление","Монтаж","Готовая мебель"];
const el=(tag,txt,cls)=>{const a=document.createElement(tag);if(txt!==undefined)a.textContent=txt;if(cls)a.className=cls;return a};
const photo=f=>{if(!/^[a-f0-9]{32}$/.test(f.id))return null;const img=el("img");img.src=base+"/public/photos/"+f.id;img.alt="Фото проекта";img.loading="lazy";img.decoding="async";return img};
fetch(base+"/public/portfolio",{credentials:"omit",cache:"no-store"}).then(r=>{if(!r.ok)throw Error("Unavailable");return r.json()}).then(data=>{
 for(const [category,id] of Object.entries(data.covers||{})){
  if(!/^[1-8]$/.test(category)||!/^[a-f0-9]{32}$/.test(id))continue;
  const a=document.querySelector("#project-"+category+" .project-photo"),img=a?.querySelector("img");if(!img)continue;
  const p=new Image();p.onload=()=>{img.src=p.src;img.alt="Фото проекта ЛериКа";img.removeAttribute("width");img.removeAttribute("height");a.classList.add("live-cover");a.querySelector(".demo-label")?.remove()};p.src=base+"/public/photos/"+id;
 }
 for(const p of data.projects||[]){
  if(!Number.isInteger(p.category)||p.category<1||p.category>8||!["ready","work"].includes(p.status))continue;
  const panel=document.querySelector("#portfolio-"+p.category+' [data-panel="'+p.status+'"]');if(!panel)continue;
  const card=el("article",undefined,"case-card live-case");card.append(el("p",p.status==="ready"?"ГОТОВЫЙ ПРОЕКТ":"В РАБОТЕ","project-number"),el("h3",p.title),el("p",p.description));
  const timeline=el("ol",undefined,"case-timeline");
  stages.forEach((s,i)=>{const li=el("li"),inside=el("div");li.append(el("span","0"+(i+1),"stage-index"),inside);inside.append(el("h4",s));const photos=(p.photos||[]).filter(f=>f.stage===i+1);for(const f of photos){const img=photo(f);if(img){const d=el("div",undefined,"live-photo");d.append(img);inside.append(d);li.classList.add("has-material")}}if(!photos.length)inside.append(el("p","Материалы этапа пока не опубликованы.","case-note"));timeline.append(li)});
  card.append(timeline);panel.querySelector(".case-empty")?.remove();panel.append(card);
 }
}).catch(()=>{/* Keep existing catalogue available when API is offline. */});
})();