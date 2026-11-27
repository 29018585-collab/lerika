"use strict";
// Never cache authenticated HTML, session responses, uploaded files or API data.
self.addEventListener("install",event=>event.waitUntil(self.skipWaiting()));
self.addEventListener("activate",event=>event.waitUntil(self.clients.claim()));
self.addEventListener("fetch",event=>{
  const r=event.request;
  if(r.method!=="GET"||r.mode!=="navigate"||new URL(r.url).origin!==self.location.origin)return;
  event.respondWith(fetch(r).catch(()=>new Response('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ЛериКа — нет сети</title><h1>Нет подключения к интернету</h1><p>Для безопасной работы с проектами необходимо подключение к сети. Проверьте интернет и откройте приложение снова.</p></html>',{status:503,headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"}})));
});
