"""Opt-in stage notifications for the closed Telegram pilot and linked website orders."""
import re
import hmac
import hashlib
from telegram_intake import STAGE_LABELS

def preference(text,digest,db,lock):
    if text not in ("🔔 Включить уведомления","🔕 Выключить уведомления","/notify_on","/notify_off"):
        return None
    enabled=text in ("🔔 Включить уведомления","/notify_on")
    with db() as c:
        lock(c,82003)
        if enabled:
            c.execute("INSERT INTO telegram_test_subscriptions(chat_key) VALUES(?) ON CONFLICT(chat_key) DO NOTHING",(digest,))
        else:
            c.execute("DELETE FROM telegram_test_subscriptions WHERE chat_key=?",(digest,))
    return "Уведомления об этапах своих заявок (включая связанный кабинет) "+("включены." if enabled else "выключены.")

def event_for_edit(c,rid,old,stage,status):
    if not old or (old["stage"],old["status"])==(stage,status):
        return None
    row=c.execute("""SELECT o.chat_key,n.number FROM telegram_test_owners o
        JOIN telegram_test_subscriptions s ON s.chat_key=o.chat_key
        JOIN request_numbers n ON n.request_id=o.request_id
        JOIN projects p ON p.id=o.request_id
        WHERE o.request_id=? AND p.published=0""",(rid,)).fetchone()
    synthetic=bool(row)
    if not row:
        row=c.execute("""SELECT l.chat_key,n.number FROM client_requests cr
            JOIN telegram_web_links l ON l.client=cr.client
            JOIN telegram_pilot_clients t ON t.chat_key=l.chat_key
            JOIN telegram_test_subscriptions s ON s.chat_key=l.chat_key
            JOIN request_numbers n ON n.request_id=cr.project
            JOIN projects p ON p.id=cr.project
            WHERE cr.project=? AND p.published=0
              AND NOT EXISTS (SELECT 1 FROM telegram_test_owners o WHERE o.request_id=cr.project)""",(rid,)).fetchone()
    if not row:
        return None
    return (row["chat_key"],"L-"+str(row["number"]).zfill(6),stage,status,synthetic)

def deliver_event(event,key,chat_id,token,sender):
    if event is None or not re.fullmatch(r"[1-9][0-9]{0,15}",chat_id or ""):
        return False
    digest,number,stage,status,synthetic=event
    expected=hmac.new(key.encode(),chat_id.encode(),hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(digest,expected) or type(stage) is not int or not 1<=stage<=6 or status not in ("work","ready"):
        return False
    text="ЛериКа · "+("Тестовая заявка " if synthetic else "Заявка ")+number+"\nЭтап: "+STAGE_LABELS[stage-1]+"\nСтатус: "+("Готово" if status=="ready" else "В работе")+("\nЭто тестовая заявка." if synthetic else "")
    try:
        result=sender(token,"sendMessage",{"chat_id":int(chat_id),"text":text,"link_preview_options":{"is_disabled":True}})
        return isinstance(result,dict) and type(result.get("message_id")) is int
    except Exception:
        return False
