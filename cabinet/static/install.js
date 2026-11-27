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
