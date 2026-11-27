"use strict";
(()=>{
const button=document.getElementById("installApp"),help=document.getElementById("installHelp"),note=document.getElementById("installNote");
let pending=null;
const standalone=()=>window.matchMedia("(display-mode: standalone)").matches||navigator.standalone===true;
function update(){if(button)button.hidden=standalone();if(standalone()&&help)help.hidden=true}
if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js",{scope:"/"}).catch(()=>{});
window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();pending=event;update()});
window.addEventListener("appinstalled",()=>{pending=null;if(button)button.hidden=true;if(help)help.hidden=true});
if(button)button.addEventListener("click",async()=>{
 if(pending){const p=pending;pending=null;try{await p.prompt();await p.userChoice;update()}catch{if(help)help.hidden=false}return}
 if(help){help.hidden=!help.hidden;if(note)note.textContent=/iPhone|iPad|iPod/i.test(navigator.userAgent)?"Откройте эту страницу в Safari, нажмите «Поделиться», затем «На экран Домой».":"Откройте эту страницу в Chrome или Samsung Internet, затем меню ⋮ → «Установить приложение» или «Добавить на главный экран»."}
});
update();
})();

if(document.getElementById('loginForm')){

(()=>{"use strict";
const button=document.getElementById("lerika-share"),panel=document.getElementById("lerika-share-panel"),field=document.getElementById("lerika-share-url"),status=document.getElementById("lerika-share-status"),copy=document.getElementById("lerika-share-copy"),close=document.getElementById("lerika-share-close");
if(!button||!panel||!field||!status||!copy||!close)return;
const url="https://lerika-cabinet.onrender.com/showroom/";
field.value=url;
function show(){panel.hidden=false;button.setAttribute("aria-expanded","true");status.textContent="";field.focus();field.select()}
function hide(){panel.hidden=true;button.setAttribute("aria-expanded","false");button.focus()}
button.addEventListener("click",async()=>{if(!panel.hidden){hide();return}if(typeof navigator.share==="function"){try{await navigator.share({title:"ЛериКа — мебель на заказ",text:"Каталог, мебель и лаборатория дизайна ЛериКа",url});return}catch(e){if(e&&e.name==="AbortError")return}}show()});
copy.addEventListener("click",async()=>{try{if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(url);status.textContent="Ссылка скопирована.";return}}catch(e){}field.focus();field.select();let ok=false;try{ok=document.execCommand("copy")}catch(e){}status.textContent=ok?"Ссылка скопирована.":"Ссылка выделена. Скопируйте её вручную."});
close.addEventListener("click",hide);panel.addEventListener("keydown",e=>{if(e.key==="Escape")hide()});
})();
}
