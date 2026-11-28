"""Administrator-only synthetic Telegram order pilot. No file downloads or AI calls."""
import hashlib
import hmac
import re
import secrets
import time


def order_id(key, digest, code):
    return hmac.new(key.encode(), ("tg-test-order:" + digest + ":" + code).encode(), hashlib.sha256).hexdigest()[:32]


def handle_test_order(text, digest, key, db, lock, allocate_number, existing_number, reserve_limits, notify, now=None):
    if not isinstance(text, str):
        return None
    command, _, value = text.partition(" ")
    if command not in ("/order_test", "/confirm", "/cancel"):
        return None
    now = int(time.time()) if now is None else now
    value = value.strip()
    if command == "/order_test" and not 5 <= len(value) <= 1200:
        return "Тестовая заявка: /order_test Вымышленное описание мебели (5–1200 символов). Не вводите реальные контакты и адреса."
    if command == "/confirm" and not re.fullmatch(r"[a-f0-9]{12}", value):
        return "Для подтверждения отправьте команду /confirm с кодом из предварительного просмотра."
    if command == "/order_test":
        reserve_limits([("lerika-tg-test-order-day", 5, 86400)])
    fresh = False
    number = None
    with db() as c:
        lock(c, 82003)
        c.execute("DELETE FROM telegram_test_drafts WHERE expires<=?", (now,))
        if command == "/cancel":
            c.execute("DELETE FROM telegram_test_drafts WHERE chat_key=?", (digest,))
            return "Тестовый черновик отменён. Отправленные заявки не изменены."
        if command == "/order_test":
            code = secrets.token_hex(6)
            c.execute("INSERT INTO telegram_test_drafts(chat_key,code,brief,expires) VALUES(?,?,?,?) ON CONFLICT(chat_key) DO UPDATE SET code=excluded.code,brief=excluded.brief,expires=excluded.expires", (digest, code, value, now+900))
            return ("ТЕСТОВЫЙ ЧЕРНОВИК (ещё не отправлен)\n\n" + value + "\n\nПодтвердите отправку в кабинет: /confirm " + code + "\nОтменить: /cancel\nКод действует 15 минут.")
        rid = order_id(key, digest, value)
        number = existing_number(c, rid)
        if not number:
            row = c.execute("SELECT code,brief FROM telegram_test_drafts WHERE chat_key=?", (digest,)).fetchone()
            if not row or not hmac.compare_digest(row["code"], value):
                return "Код не подходит или черновик истёк. Создайте новый: /order_test описание."
            brief = "Источник заявки: Telegram\nРежим: ТЕСТ — не производственный заказ\nКонтакт: администратор (тест)\n\n" + row["brief"]
            c.execute("INSERT INTO projects(category,title,description,stage,status,published,updated,id) VALUES(?,?,?,?,?,?,?,?)", (8, "ТЕСТ · Telegram", "Тестовая заявка ЛериКа из Telegram", 1, "work", 0, now, rid))
            c.execute("INSERT INTO design_briefs VALUES(?,?)", (rid, brief))
            c.execute("INSERT INTO design_requests VALUES(?,?)", (rid, now))
            number = allocate_number(c, rid)
            c.execute("UPDATE projects SET title=? WHERE id=?", ("ТЕСТ · Telegram · "+number, rid))
            c.execute("DELETE FROM telegram_test_drafts WHERE chat_key=?", (digest,))
            fresh = True
    if fresh:
        try:
            notify(number, "telegram", "Другое", 0)
        except Exception:
            pass
    return "Тестовая заявка " + number + " сохранена в закрытом кабинете. Это не производственный заказ."
