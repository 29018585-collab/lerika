"use strict";
(()=>{
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e};
 window.LerikaClientMessages={mount(root,order,call,status){
  const box=node("details"),summary=node("summary","Переписка с дизайнером"),list=node("div"),input=node("textarea"),send=node("button","Отправить сообщение"),refresh=node("button","Обновить переписку"),notice=node("p","");
  box.className="client-guide";input.maxLength=2000;input.rows=3;input.placeholder="Ваш вопрос или комментарий";input.setAttribute("aria-label","Сообщение дизайнеру");send.type=refresh.type="button";send.className=refresh.className="lab-btn secondary";notice.setAttribute("role","status");
  const path="orders/"+encodeURIComponent(order.id)+"/messages";let busy=false;
  async function load(body){if(busy)return;busy=true;send.disabled=refresh.disabled=true;notice.textContent="";try{const d=await call(path,body);if(!root.isConnected)return;list.replaceChildren();for(const m of d.messages){const item=node("div");item.className="project-item";const t=node("p",m.body);t.style.whiteSpace="pre-wrap";item.append(node("strong",(m.author==="designer"?"Дизайнер":"Вы")+" · "+new Date(m.created*1000).toLocaleString("ru-RU")),t);list.append(item)}if(!d.messages.length)list.append(node("p","Сообщений пока нет."));if(body){input.value="";notice.textContent="Сообщение отправлено."}}catch(e){if(root.isConnected){notice.textContent=e.message;status(e.message)}}finally{busy=false;send.disabled=refresh.disabled=false}}
  box.addEventListener("toggle",()=>{if(box.open)load()});refresh.onclick=()=>load();send.onclick=()=>{const text=input.value.trim();if(text)load({text});else notice.textContent="Введите сообщение."};box.append(summary,list,input,send,refresh,notice);root.append(box)
 }};
})();
