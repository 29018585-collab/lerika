"""Telegram menu and private synthetic assistant preview; no client intake yet."""
import json, re, hmac, hashlib
from urllib.request import Request, urlopen

PATH="/api/telegram/webhook"
def secret_for(key):
    return hmac.new(key.encode(),b"lerika-telegram-webhook-v1",hashlib.sha256).hexdigest()

def bot_call(token,method,payload=None,opener=urlopen):
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}",token or "") or method not in {"getWebhookInfo","setWebhook","deleteWebhook","sendMessage","getMe"}:
        return None
    try:
        req=Request("https://api.telegram.org/bot"+token+"/"+method,data=json.dumps(payload or {},ensure_ascii=False).encode(),headers={"Content-Type":"application/json","User-Agent":"LERIKA-Telegram/1.0"},method="POST")
        with opener(req,timeout=8) as res:
            obj=json.loads(res.read(131072))
        return obj.get("result") if isinstance(obj,dict) and obj.get("ok") is True else None
    except Exception:
        return None

def parse_update(obj):
    if not isinstance(obj,dict) or type(obj.get("update_id")) is not int or not 0<=obj["update_id"]<2**53:
        return None
    m=obj.get("message")
    if not isinstance(m,dict):
        return None
    chat=m.get("chat")
    sender=m.get("from")
    if not isinstance(chat,dict) or not isinstance(sender,dict) or chat.get("type")!="private" or sender.get("is_bot") is not False:
        return None
    cid=chat.get("id")
    if type(cid) is not int or not 0<cid<2**53 or sender.get("id")!=cid:
        return None
    text=m.get("text")
    return obj["update_id"],cid,text.strip() if isinstance(text,str) else None

def menu(origin,admin=False):
    base=origin+"/showroom/"
    buttons=[[{"text":"Спроектировать квартиру","url":base+"#design-lab/plan"}],
             [{"text":"Создать мебель","url":base+"#design-lab/3d"},{"text":"Дизайн-студия","url":base+"#design-lab/ai"}],
             [{"text":"Смета","url":base+"#design-lab/estimate"},{"text":"Отправить заказ","url":base+"#design-lab/order"}],
             [{"text":"Поддержка","url":base+"#support"}]]
    text="Здравствуйте! Это помощник мебельной студии ЛериКа. Выберите нужный инструмент. Заказы, документы и контакты пока принимаем через защищённые формы сайта."
    if admin:
        text+="\n\nТест ИИ только для администратора: /ai вымышленный вопрос. Текст будет отправлен в Groq. Не используйте личные данные."
    return text,{"inline_keyboard":buttons}

def answer_message(text,origin,is_admin,classifier=None):
    if text is None:
        return "Файлы в этом чате пока не сохраняются. Передайте фото и чертежи через форму заказа на сайте.",{"inline_keyboard":[[{"text":"Форма заказа","url":origin+"/showroom/#design-lab/order"}]]}
    if is_admin and text.startswith("/ai "):
        query=text[4:].strip()
        if not query or len(query)>800:
            return "Введите вымышленный тестовый вопрос длиной до 800 символов.",None
        if classifier is None:
            return "Тест ИИ недоступен или достигнут лимит.",None
        result=classifier(query)
        answer=result["answer"]+"\n\n"+result["question"]+"\n\nКонтроль формата: "+result["guard"]
        route=result.get("route")
        markup={"inline_keyboard":[[{"text":"Открыть инструмент","url":origin+"/showroom/#design-lab/"+route}]]} if route in {"plan","3d","ai","engineering","estimate","order"} else None
        return answer,markup
    return menu(origin,is_admin)
