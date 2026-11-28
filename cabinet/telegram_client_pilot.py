"""Closed, opt-in multi-user Telegram pilot. No website account linking."""
import hashlib
import hmac
import re
import time

JOIN = "📝 Зарегистрироваться в тесте"
LEAVE = "🚪 Выйти из теста"
CONSENT = "Согласен на тестовую регистрацию"
def valid_chat(cid):
    return type(cid) is int and 0 < cid < 2**53

def digest_for(key,cid):
    return hmac.new(key.encode(),str(cid).encode(),hashlib.sha256).hexdigest()[:32]

def allowed(cid,enabled,allowlist):
    if not valid_chat(cid) or enabled!="1" or not isinstance(allowlist,str):
        return False
    ids=allowlist.split(",")
    return len(ids)<=20 and str(cid) in {v.strip() for v in ids if re.fullmatch(r"[1-9][0-9]{0,15}",v.strip())}

def enrolled(c,digest):
    return c.execute("SELECT 1 FROM telegram_pilot_clients WHERE chat_key=?",(digest,)).fetchone() is not None

def registration(text,digest,db,lock,now=None):
    if text not in (JOIN,CONSENT,LEAVE):
        return None
    if text==JOIN:
        with db() as c:
            lock(c,82003)
            c.execute("INSERT INTO telegram_pilot_pending(chat_key,expires) VALUES(?,?) ON CONFLICT(chat_key) DO UPDATE SET expires=excluded.expires",(digest,(int(time.time()) if now is None else now)+900))
        return ("Закрытый тест ЛериКа. Сохраняются защищённый идентификатор Telegram, время регистрации, "
                "тестовые описания и вложения. Не отправляйте реальные адреса, контакты и документы. "
                "Заявки видит администратор. Уведомления включаются отдельно. "
                "Для выхода нажмите «Выйти из теста»; уже отправленные заявки остаются в закрытом кабинете.")
    with db() as c:
        lock(c,82003)
        if text==CONSENT:
            stamp=int(time.time()) if now is None else now
            pending=c.execute("SELECT expires FROM telegram_pilot_pending WHERE chat_key=?",(digest,)).fetchone()
            if not pending or pending["expires"]<=stamp:
                return "Сначала нажмите «Зарегистрироваться в тесте» и прочитайте условия."
            c.execute("DELETE FROM telegram_pilot_pending WHERE chat_key=?",(digest,))
            c.execute("INSERT INTO telegram_pilot_clients(chat_key,created) VALUES(?,?) ON CONFLICT(chat_key) DO NOTHING",(digest,int(time.time()) if now is None else now))
            return "Тестовая регистрация завершена. Можно создавать вымышленные заявки."
        c.execute("DELETE FROM telegram_test_subscriptions WHERE chat_key=?",(digest,))
        c.execute("DELETE FROM telegram_test_files WHERE chat_key=?",(digest,))
        c.execute("DELETE FROM telegram_test_drafts WHERE chat_key=?",(digest,))
        c.execute("DELETE FROM telegram_pilot_clients WHERE chat_key=?",(digest,))
        c.execute("DELETE FROM telegram_pilot_pending WHERE chat_key=?",(digest,))
        return "Вы вышли из теста. Черновик удалён, уведомления отключены. Отправленные заявки остаются в кабинете."

def registration_keyboard(show_consent=False):
    rows=[[{"text":JOIN}]]
    if show_consent:
        rows.append([{"text":CONSENT}])
    rows.append([{"text":"🌐 Инструменты сайта"}])
    return {"keyboard":rows,"resize_keyboard":True,"is_persistent":True}

def notification_chat(c,event,key,admin_chat,enabled,allowlist):
    if event is None:
        return ""
    digest=event[0]
    if re.fullmatch(r"[1-9][0-9]{0,15}",admin_chat or "") and hmac.compare_digest(digest,digest_for(key,admin_chat)):
        return admin_chat
    if not enrolled(c,digest):
        return ""
    for value in allowlist.split(",") if isinstance(allowlist,str) else []:
        value=value.strip()
        if re.fullmatch(r"[1-9][0-9]{0,15}",value) and allowed(int(value),enabled,allowlist) and hmac.compare_digest(digest,digest_for(key,value)):
            return value
    return ""
