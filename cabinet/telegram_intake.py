"""Administrator-only synthetic Telegram order pilot. No AI calls."""
import hashlib
import hmac
import re
import secrets
import time
from telegram_files import purge_expired, clear_files, usage, STORAGE_CAP


def order_id(key, digest, code):
    return hmac.new(key.encode(), ("tg-test-order:" + digest + ":" + code).encode(), hashlib.sha256).hexdigest()[:32]


def handle_test_order(text, digest, key, db, lock, allocate_number, existing_number, reserve_limits, notify, now=None):
    if not isinstance(text, str):
        return None
    now = int(time.time()) if now is None else now
    text = text.strip()
    if text == "➕ Новая тестовая заявка":
        text = "/begin_test"
    elif text == "📋 Черновик":
        text = "/draft"
    elif text.startswith("✅ Отправить "):
        text = "/confirm " + text[len("✅ Отправить "):]
    elif text.startswith("❌ Отменить "):
        text = "/cancel " + text[len("❌ Отменить "):]
    command, _, value = text.partition(" ")
    value = value.strip()
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
        reserve_limits([("lerika-tg-test-order-day", 5, 86400)])
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
            brief = "Источник заявки: Telegram\nРежим: ТЕСТ — не производственный заказ\nКонтакт: администратор (тест)\n\n" + row["brief"]
            c.execute("INSERT INTO projects(category,title,description,stage,status,published,updated,id) VALUES(?,?,?,?,?,?,?,?)", (8, "ТЕСТ · Telegram", "Тестовая заявка ЛериКа из Telegram", 1, "work", 0, now, rid))
            c.execute("INSERT INTO design_briefs VALUES(?,?)", (rid, brief))
            for f in attachments:
                c.execute("INSERT INTO files VALUES(?,?,?,?,?,?,0,?)",(secrets.token_hex(16),rid,1,f["name"],"application/octet-stream",0,f["data"]))
            c.execute("INSERT INTO design_requests VALUES(?,?)", (rid, now))
            number = allocate_number(c, rid)
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
