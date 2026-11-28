"""Administrator-only synthetic Telegram order pilot. No AI calls."""
import hashlib
import hmac
import re
import secrets
import time
from telegram_files import purge_expired, clear_files, usage, STORAGE_CAP


def order_id(key, digest, code):
    return hmac.new(key.encode(), ("tg-test-order:" + digest + ":" + code).encode(), hashlib.sha256).hexdigest()[:32]


STAGE_LABELS = ("Исходное помещение","Замеры и эскизы","3D-проект","Изготовление","Монтаж","Готовая мебель")

def status_text(c, digest, value=None):
    sql = """SELECT n.number,p.stage,p.status,d.created
             FROM telegram_test_owners o
             JOIN design_requests d ON d.id=o.request_id
             JOIN request_numbers n ON n.request_id=d.id
             JOIN projects p ON p.id=d.id
             WHERE o.chat_key=? AND p.published=0"""
    params = [digest]
    if value is not None:
        if not re.fullmatch(r"L-[0-9]{6,12}",value):
            return "Введите номер в формате /status L-000001."
        sql += " AND n.number=?"
        params.append(int(value[2:]))
    rows = c.execute(sql+" ORDER BY d.created DESC,n.number DESC LIMIT 10",tuple(params)).fetchall()
    if not rows:
        return "Заявка не найдена или недоступна." if value is not None else "У вас пока нет сохранённых тестовых заявок в новой системе истории."
    lines = ["ТЕСТОВЫЕ ЗАЯВКИ · последние 10" if value is None else "СТАТУС ТЕСТОВОЙ ЗАЯВКИ"]
    for row in rows:
        stage = row["stage"]
        label = STAGE_LABELS[stage-1] if type(stage) is int and 1<=stage<=6 else "Уточняется"
        number = "L-"+str(row["number"]).zfill(6)
        lines.append(number+" · "+label+" · "+("Готово" if row["status"]=="ready" else "В работе"))
    lines.append("Данные из закрытого кабинета. Это тестовые заявки, не производственные заказы.")
    return "\n\n".join(lines)

def handle_test_order(text, digest, key, db, lock, allocate_number, existing_number, reserve_limits, notify, now=None):
    if not isinstance(text, str):
        return None
    now = int(time.time()) if now is None else now
    text = text.strip()
    if text == "➕ Новая тестовая заявка":
        text = "/begin_test"
    elif text == "📋 Черновик":
        text = "/draft"
    elif text == "📦 Мои заявки":
        text = "/orders"
    elif text.startswith("✅ Отправить "):
        text = "/confirm " + text[len("✅ Отправить "):]
    elif text.startswith("❌ Отменить "):
        text = "/cancel " + text[len("❌ Отменить "):]
    command, _, value = text.partition(" ")
    value = value.strip()
    if command in ("/orders", "/status"):
        with db() as c:
            lock(c,82003)
            return status_text(c,digest,value if command=="/status" else None)
    if command not in ("/order_test", "/begin_test", "/draft", "/confirm", "/cancel"):
        if not text or text.startswith("/") or text == "🌐 Инструменты сайта":
            return None
        with db() as c:
            lock(c, 82003)
            purge_expired(c, now)
            row = c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
            if not row or row["brief"]:
                return None
            if not 5 <= len(text) <= 1200:
                return "Введите вымышленное описание длиной 5–1200 символов."
            c.execute("UPDATE telegram_test_drafts SET brief=?,expires=? WHERE chat_key=? AND code=?", (text,now+900,digest,row["code"]))
            return "Описание сохранено. Прикрепите до 10 файлов (12 МБ суммарно) или нажмите «Отправить». Черновик действует 15 минут."
    if command == "/order_test" and not 5 <= len(value) <= 1200:
        return "Тестовая заявка: /order_test Вымышленное описание мебели (5–1200 символов). Не вводите реальные контакты и адреса."
    if command == "/confirm" and not re.fullmatch(r"[a-f0-9]{12}", value):
        return "Для подтверждения отправьте команду /confirm с кодом из предварительного просмотра."
    if command in ("/order_test", "/begin_test"):
        reserve_limits([("lerika-tg-test-order-day", 30, 86400),("lerika-tg-test-order-owner-"+digest, 5, 86400)])
    fresh = False
    number = None
    attachment_count = 0
    with db() as c:
        lock(c, 82003)
        purge_expired(c, now)
        if command == "/draft":
            row=c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
            if not row:
                return "Активного черновика нет."
            u=usage(c,digest,row["code"])
            return "ТЕСТОВЫЙ ЧЕРНОВИК\n\n"+(row["brief"] or "Описание ещё не введено.")+"\n\nВложений: "+str(u["n"])+" / 10. Черновик ещё не отправлен."
        if command == "/begin_test":
            row=c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
            if row:
                return "У вас уже есть черновик. Продолжите его или отмените перед созданием нового."
            c.execute("INSERT INTO telegram_test_drafts(chat_key,code,brief,expires) VALUES(?,?,?,?)",(digest,secrets.token_hex(6),"",now+900))
            return "ТЕСТОВАЯ ЗАЯВКА. Напишите вымышленное описание мебели одним сообщением. Не отправляйте реальные контакты и адреса."
        if command == "/cancel":
            if value:
                row=c.execute("SELECT code FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
                if not row or not hmac.compare_digest(row["code"],value):
                    return "Эта кнопка относится к старому черновику. Откройте текущий черновик."
            clear_files(c, digest)
            c.execute("DELETE FROM telegram_test_drafts WHERE chat_key=?", (digest,))
            return "Тестовый черновик отменён. Отправленные заявки не изменены."
        if command == "/order_test":
            clear_files(c, digest)
            code = secrets.token_hex(6)
            c.execute("INSERT INTO telegram_test_drafts(chat_key,code,brief,expires) VALUES(?,?,?,?) ON CONFLICT(chat_key) DO UPDATE SET code=excluded.code,brief=excluded.brief,expires=excluded.expires", (digest, code, value, now+900))
            return ("ТЕСТОВЫЙ ЧЕРНОВИК (ещё не отправлен)\n\n" + value + "\n\nПодтвердите отправку в кабинет: /confirm " + code + "\nОтменить: /cancel\nДо подтверждения можно отправить до 10 файлов (12 МБ суммарно).\nКод действует 15 минут.")
        rid = order_id(key, digest, value)
        number = existing_number(c, rid)
        if not number:
            row = c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
            if not row or not hmac.compare_digest(row["code"], value):
                return "Код не подходит или черновик истёк. Создайте новый: /order_test описание."
            if not row["brief"]:
                return "Сначала введите описание заявки."
            attachments = c.execute("SELECT name,data FROM telegram_test_files WHERE chat_key=? AND code=? ORDER BY checksum",(digest,value)).fetchall()
            used = c.execute("SELECT COALESCE(SUM(length(data)),0) AS size FROM files").fetchone()["size"]
            if used+sum(len(f["data"]) for f in attachments)>STORAGE_CAP:
                return "Хранилище заполнено. Черновик сохранён, заявка не отправлена."
            attachment_count = len(attachments)
            brief = "Источник заявки: Telegram\nРежим: ТЕСТ — не производственный заказ\nКонтакт: владелец Telegram-заявки (тест)\n\n" + row["brief"]
            c.execute("INSERT INTO projects(category,title,description,stage,status,published,updated,id) VALUES(?,?,?,?,?,?,?,?)", (8, "ТЕСТ · Telegram", "Тестовая заявка ЛериКа из Telegram", 1, "work", 0, now, rid))
            c.execute("INSERT INTO design_briefs VALUES(?,?)", (rid, brief))
            for f in attachments:
                c.execute("INSERT INTO files VALUES(?,?,?,?,?,?,0,?)",(secrets.token_hex(16),rid,1,f["name"],"application/octet-stream",0,f["data"]))
            c.execute("INSERT INTO design_requests VALUES(?,?)", (rid, now))
            number = allocate_number(c, rid)
            c.execute("INSERT INTO telegram_test_owners(request_id,chat_key) VALUES(?,?)",(rid,digest))
            c.execute("UPDATE projects SET title=? WHERE id=?", ("ТЕСТ · Telegram · "+number, rid))
            c.execute("DELETE FROM telegram_test_drafts WHERE chat_key=?", (digest,))
            clear_files(c, digest)
            fresh = True
    if fresh:
        try:
            notify(number, "telegram", "Другое", attachment_count)
        except Exception:
            pass
    return "Тестовая заявка " + number + " сохранена в закрытом кабинете. Это не производственный заказ." + (" Вложений: "+str(attachment_count)+"." if fresh else "")


def pilot_keyboard(digest,db,lock,now=None,client=False):
    now=int(time.time()) if now is None else now
    with db() as c:
        lock(c,82003)
        purge_expired(c,now)
        row=c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?",(digest,)).fetchone()
        subscribed=c.execute("SELECT 1 FROM telegram_test_subscriptions WHERE chat_key=?",(digest,)).fetchone() is not None
    if row:
        keyboard=[[{"text":"📋 Черновик"}]]
        if row["brief"]:
            keyboard.append([{"text":"✅ Отправить "+row["code"]}])
        keyboard.append([{"text":"❌ Отменить "+row["code"]}])
    else:
        keyboard=[[{"text":"➕ Новая тестовая заявка"}]]
    keyboard.append([{"text":"📦 Мои заявки"},{"text":"🌐 Инструменты сайта"}])
    keyboard.append([{"text":"🔕 Выключить уведомления" if subscribed else "🔔 Включить уведомления"}])
    if client:
        keyboard.append([{"text":"🚪 Выйти из теста"}])
    return {"keyboard":keyboard,"resize_keyboard":True,"is_persistent":True}
