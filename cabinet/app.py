import os, sqlite3, secrets, time, io, json, re, hashlib, base64, mimetypes, csv, zipfile, hmac, ipaddress
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.request import urlopen, Request
from urllib.parse import quote, urlsplit
from threading import Lock
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
from flask import Flask, request, session, abort, jsonify, render_template, send_file, redirect
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, ImageOps

DATABASE_URL=os.environ.get("DATABASE_URL","")
SETUP_REQUIRED=bool(os.environ.get("RENDER")) and (not DATABASE_URL or not os.environ.get("SESSION_SECRET") or not (os.environ.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD_HASH")))


ROOT=Path(os.environ.get("DATA_DIR","/data"))
if not DATABASE_URL and not SETUP_REQUIRED:
    ROOT.mkdir(parents=True,exist_ok=True)
DB=ROOT/"portfolio.sqlite3"
KEY=os.environ.get("SESSION_SECRET","")
PASSWORD=os.environ.get("ADMIN_PASSWORD_HASH","")
# Optional password configured directly in the private hosting dashboard.
# Never put this value in GitHub or client-side code.
if os.environ.get("ADMIN_PASSWORD"):
    if len(os.environ["ADMIN_PASSWORD"])<14:
        raise RuntimeError("ADMIN_PASSWORD must contain at least 14 characters")
    PASSWORD=generate_password_hash(os.environ["ADMIN_PASSWORD"])
if not SETUP_REQUIRED and (len(KEY)<32 or not PASSWORD.startswith(("scrypt:","pbkdf2:"))):
    raise RuntimeError("Set SESSION_SECRET (32+ random characters) and ADMIN_PASSWORD_HASH")
app=Flask(__name__)
app.config.update(SECRET_KEY=KEY if not SETUP_REQUIRED else None,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SECURE=True,SESSION_COOKIE_SAMESITE="Strict",MAX_CONTENT_LENGTH=16*1024*1024)
REQUEST_SOURCES={"project":"Коллекция изделий","3d":"3D-конструктор","ai":"Дизайн-студия","config":"Конфигуратор","plan":"Планировщик помещения","engineering":"Инженерная лаборатория","order":"Прямой заказ","legacy":"Источник не указан","support":"Поддержка","partner":"Сотрудничество","telegram":"Telegram"}
CATEGORIES=["Кухни","Шкафы","Прихожие","Спальни","Детские","Гостиные","Гардеробные","Нестандартные системы хранения"]
STAGES=["Исходное помещение","Замеры и эскизы","3D-проект","Изготовление","Монтаж","Готовая мебель"]
ORIGIN="https://29018585-collab.github.io"
DEFAULT_PUBLIC_ORIGIN="https://lerika-cabinet.onrender.com"
def checked_origin(value):
    value=value.strip().rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?",value):
        raise RuntimeError("PUBLIC_ORIGIN/ALLOWED_ORIGINS must contain HTTPS origins only")
    u=urlsplit(value)
    if not u.hostname or u.port is not None and not 1<=u.port<=65535:
        raise RuntimeError("Invalid public origin")
    return "https://"+u.netloc.lower()
PUBLIC_ORIGIN=checked_origin(os.environ.get("PUBLIC_ORIGIN",DEFAULT_PUBLIC_ORIGIN))
ALLOWED_ORIGINS={PUBLIC_ORIGIN,DEFAULT_PUBLIC_ORIGIN}|{checked_origin(v) for v in os.environ.get("ALLOWED_ORIGINS","").split(",") if v.strip()}
def current_public_origin():
    # Match configured origins only, never reflect an arbitrary Host header.
    return next((v for v in sorted(ALLOWED_ORIGINS) if urlsplit(v).netloc==request.host.lower()),PUBLIC_ORIGIN)
def valid_public_origin():
    origin=request.headers.get("Origin")
    return origin in ALLOWED_ORIGINS and urlsplit(origin).netloc==request.host.lower()

Image.MAX_IMAGE_PIXELS=25000000

class PostgresDB:
    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=15)
    def __enter__(self):
        self.conn.__enter__()
        return self
    def __exit__(self,*args):
        return self.conn.__exit__(*args)
    def execute(self,sql,params=()):
        return self.conn.execute(sql.replace("?", "%s"),params)
    def executescript(self,sql):
        for statement in sql.replace("BLOB","BYTEA").split(";"):
            if statement.strip(): self.conn.execute(statement)
    def commit(self):
        self.conn.commit()

@contextmanager
def db():
    if DATABASE_URL:
        with PostgresDB() as c:
            yield c
        return
    c=sqlite3.connect(DB,timeout=10)
    try:
        c.row_factory=sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        with c:
            yield c
    finally:
        c.close()
def lock(c,key):
    if DATABASE_URL:
        c.execute("SELECT pg_advisory_xact_lock(?)",(key,))
    else:
        c.execute("BEGIN IMMEDIATE")

def request_number(n):
    return "L-"+str(n).zfill(6)
def existing_number(c,rid):
    row=c.execute("SELECT number FROM request_numbers WHERE request_id=?",(rid,)).fetchone()
    return request_number(row["number"]) if row else None
def allocate_number(c,rid):
    # Call only while holding intake/migration lock 82003. Counter never decreases.
    old=existing_number(c,rid)
    if old: return old
    c.execute("UPDATE request_sequence SET last_number=last_number+1 WHERE id=1")
    n=c.execute("SELECT last_number FROM request_sequence WHERE id=1").fetchone()["last_number"]
    c.execute("INSERT INTO request_numbers(number,request_id) VALUES(?,?)",(n,rid))
    return request_number(n)
def migrate_request_numbers(c):
    for row in c.execute("SELECT d.id FROM design_requests d LEFT JOIN request_numbers n ON n.request_id=d.id WHERE n.request_id IS NULL ORDER BY d.created,d.id").fetchall():
        allocate_number(c,row["id"])

if not SETUP_REQUIRED:
  with db() as c:
    lock(c,82001)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, category INTEGER NOT NULL CHECK(category BETWEEN 1 AND 8), title TEXT NOT NULL, description TEXT NOT NULL, stage INTEGER NOT NULL CHECK(stage BETWEEN 1 AND 6), status TEXT NOT NULL CHECK(status IN ('work','ready')), published INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), stage INTEGER NOT NULL CHECK(stage BETWEEN 1 AND 6), name TEXT NOT NULL, mime TEXT NOT NULL, image INTEGER NOT NULL, public INTEGER NOT NULL DEFAULT 0, data BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS covers(category INTEGER PRIMARY KEY CHECK(category BETWEEN 1 AND 8), file TEXT NOT NULL REFERENCES files(id));
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY CHECK(id=1), count INTEGER NOT NULL, since INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS design_requests(id TEXT PRIMARY KEY, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS telegram_test_drafts(chat_key TEXT PRIMARY KEY, code TEXT NOT NULL, brief TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS telegram_test_files(chat_key TEXT NOT NULL REFERENCES telegram_test_drafts(chat_key) ON DELETE CASCADE, code TEXT NOT NULL, checksum TEXT NOT NULL, name TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY(chat_key,code,checksum));
    CREATE TABLE IF NOT EXISTS request_numbers(number INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES design_requests(id));
    CREATE TABLE IF NOT EXISTS telegram_test_owners(request_id TEXT PRIMARY KEY REFERENCES design_requests(id) ON DELETE CASCADE, chat_key TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS telegram_test_owners_chat ON telegram_test_owners(chat_key);
    CREATE TABLE IF NOT EXISTS telegram_test_subscriptions(chat_key TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS telegram_pilot_clients(chat_key TEXT PRIMARY KEY, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS request_sequence(id INTEGER PRIMARY KEY CHECK(id=1), last_number INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS design_briefs(project TEXT PRIMARY KEY REFERENCES projects(id), brief TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS client_requests(project TEXT PRIMARY KEY REFERENCES projects(id), client TEXT NOT NULL REFERENCES clients(id));
    CREATE TABLE IF NOT EXISTS client_limits(action TEXT PRIMARY KEY, count INTEGER NOT NULL, since INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS price_catalog(id INTEGER PRIMARY KEY CHECK(id=1), entries TEXT NOT NULL, updated INTEGER NOT NULL);
    """)
    # Migrate only the initial V5.6 intake records, if any. Preserve the client
    # brief privately and remove it from the public-facing project metadata.
    lock(c,82003)
    c.execute("INSERT INTO request_sequence VALUES(1,0) ON CONFLICT(id) DO NOTHING")
    migrate_request_numbers(c)
    legacy=list(c.execute("SELECT p.id,p.title,p.description FROM projects p JOIN design_requests r ON r.id=p.id LEFT JOIN design_briefs b ON b.project=p.id WHERE b.project IS NULL AND p.description LIKE ?",("Заявка из дизайн-студии Lab V5.6\\nКонтакт:%".replace("\\n","\n"),)))
    for p in legacy:
        c.execute("INSERT INTO design_briefs VALUES(?,?)",(p["id"],"Название: "+p["title"]+"\n"+p["description"]))
        c.execute("UPDATE projects SET title=?,description=?,published=0 WHERE id=?",("Заявка · "+p["id"][:6],"Заявка из дизайн-студии ЛериКа",p["id"]))
        c.execute("DELETE FROM covers WHERE file IN (SELECT id FROM files WHERE project=?)",(p["id"],))
    # Intake records and their attachments must never be public.
    c.execute("UPDATE projects SET published=0 WHERE id IN (SELECT id FROM design_requests)")
    c.execute("UPDATE files SET public=0 WHERE project IN (SELECT id FROM design_requests)")
    c.execute("DELETE FROM covers WHERE file IN (SELECT id FROM files WHERE project IN (SELECT id FROM design_requests))")


@app.before_request
def configuration_guard():
    if not SETUP_REQUIRED:
        return None
    if request.path=="/" and request.method in ("GET","HEAD"):
        return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ЛериКа · Настройка</title><h1>ЛериКа — личный кабинет</h1><p>Кабинет ожидает завершения защищённой настройки администратором. Вход и загрузка файлов пока недоступны.</p></html>',503,{"Content-Type":"text/html; charset=utf-8"})
    return jsonify(error="Service not configured"),503

def immutable_asset(name):
    return bool(re.fullmatch(r"(?:scene-(?:lit|unlit)|public-[a-z0-9-]+)-[a-f0-9]{16}\.webp",name))

@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"]="nosniff"
    r.headers["Referrer-Policy"]="no-referrer"
    r.headers["X-Frame-Options"]="DENY"
    r.headers.setdefault("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; manifest-src 'self'; worker-src 'self'")
    if not (request.path.startswith("/showroom/") and immutable_asset(request.path.removeprefix("/showroom/")) and r.status_code in (200,304)):
        r.headers["Cache-Control"]="no-store"
    if request.path.startswith("/public/"):
        origin=request.headers.get("Origin")
        if origin in ALLOWED_ORIGINS or origin==ORIGIN:
            r.headers["Access-Control-Allow-Origin"]=origin
            r.vary.add("Origin")
        else:
            r.headers["Access-Control-Allow-Origin"]=ORIGIN
            r.vary.add("Origin")
    return r

def admin(f):
    @wraps(f)
    def inner(*a,**kw):
        if not session.get("admin") or time.time()-session.get("login",0)>43200:
            abort(401)
        if request.method not in ("GET","HEAD"):
            supplied=request.headers.get("X-CSRF","")
            if request.path=="/cabinet/ai-test" and request.method=="POST" and request.mimetype=="application/x-www-form-urlencoded" and valid_public_origin():
                supplied=request.form.get("csrf","")
            if not secrets.compare_digest(supplied,session.get("csrf","!")):
                abort(403)
        return f(*a,**kw)
    return inner

@app.get("/")
def home():
    return redirect("/showroom/",code=302)

def notify_telegram_order(number,source,room,attachment_count):
    """Send only a minimal alert after the private request has been committed."""
    token=os.environ.get("LERIKA_TELEGRAM_BOT_TOKEN","").strip()
    chat_id=os.environ.get("LERIKA_TELEGRAM_ADMIN_CHAT_ID","").strip()
    if not token or not chat_id:
        return False
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}",token) or not re.fullmatch(r"-?[0-9]{1,20}",chat_id):
        app.logger.warning("Telegram notification configuration is invalid")
        return False
    message="ЛериКа · Новая заявка "+number+"\nИсточник: "+REQUEST_SOURCES[source]+"\nПомещение: "+room+"\nВложений: "+str(attachment_count)+"\nОткрыть закрытый кабинет: "+PUBLIC_ORIGIN+"/cabinet/"
    body=json.dumps({"chat_id":chat_id,"text":message,"link_preview_options":{"is_disabled":True}},ensure_ascii=False).encode("utf-8")
    try:
        req=Request("https://api.telegram.org/bot"+token+"/sendMessage",data=body,headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=4) as response:
            result=json.loads(response.read(65536))
        if not isinstance(result,dict) or result.get("ok") is not True:
            app.logger.warning("Telegram notification was not accepted")
            return False
        return True
    except Exception:
        # Never log the exception or request URL: they may contain the bot token.
        app.logger.warning("Telegram notification failed; the order remains in the cabinet")
        return False


LERIKA_AI_MODEL="qwen/qwen3.8-27b"

def groq_diagnostic_error(exc):
    # Map only known provider codes to fixed strings; never return raw error data.
    status=exc.code
    code=None
    kind=None
    try:
        payload=json.loads(exc.read(8192))
        err=payload.get("error")
        if isinstance(err,dict):
            code=err.get("code")
            kind=err.get("type")
    except Exception:
        pass
    prefix="Groq HTTP "+str(status)+". "
    if status==403:
        if code=="model_permission_blocked_org":
            return prefix+"Модель запрещена на уровне организации Groq (model_permission_blocked_org)."
        if code=="model_permission_blocked_project":
            return prefix+"Модель запрещена на уровне проекта Groq (model_permission_blocked_project)."
        if kind=="permissions_error":
            return prefix+"Groq сообщает об ограничении разрешений."
        if code=="unsupported_country_region_territory":
            return prefix+"Groq сообщает об ограничении региона."
        return prefix+"Причина не распознана. Проверьте разрешения модели и доступ к API в Groq."
    if status==401:
        return prefix+"Ключ не принят сервисом."
    if status==429:
        return prefix+"Достигнут лимит Groq."
    if status==404:
        return prefix+"Модель или ресурс недоступны."
    if status==400:
        return prefix+"Groq отклонил параметры запроса."
    return prefix+"Запрос не выполнен."

def qwen_connection_test():
    from urllib.error import HTTPError
    key=os.environ.get("LERIKA_GROQ_API_KEY","").strip()
    if not key:
        return False,"Ключ Groq не настроен."
    payload={"model":LERIKA_AI_MODEL,"messages":[{"role":"user","content":"Reply with exactly LERIKA_OK, no other text."}],"max_completion_tokens":64}
    try:
        req=Request("https://api.groq.com/openai/v1/chat/completions",data=json.dumps(payload).encode("utf-8"),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","Accept":"application/json","User-Agent":"LERIKA-Groq-Diagnostic/1.0"},method="POST")
        with urlopen(req,timeout=12) as res:
            data=json.loads(res.read(65536))
        answer=data["choices"][0]["message"]["content"]
        if isinstance(answer,str) and answer.strip()=="LERIKA_OK":
            return True,"PASS: Qwen ответил LERIKA_OK."
        return False,"Ответ от API получен, но контрольная фраза не совпала."
    except HTTPError as exc:
        content_type=exc.headers.get("Content-Type","").lower() if exc.headers else ""
        message=groq_diagnostic_error(exc)
        if "text/html" in content_type:
            message+=" Ответ HTML, а не стандартный JSON API."
        return False,message
    except Exception:
        return False,"Не удалось получить корректный ответ от Groq."

@app.get("/api/admin/ai")
@admin
def ai_admin_status():
    return jsonify(model=LERIKA_AI_MODEL,configured=bool(os.environ.get("LERIKA_GROQ_API_KEY","").strip()),telegram_configured=bool(os.environ.get("LERIKA_TELEGRAM_BOT_TOKEN","").strip() and os.environ.get("LERIKA_TELEGRAM_ADMIN_CHAT_ID","").strip()),rag=False,memory=False,core_version="1.0")

@app.post("/api/admin/telegram/webhook")
@admin
def telegram_admin_webhook():
    from telegram_core import PATH,bot_call,secret_for
    if not valid_public_origin():
        abort(403)
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or body.get("action") not in ("status","activate","disable"):
        abort(400)
    token=os.environ.get("LERIKA_TELEGRAM_BOT_TOKEN","").strip()
    if not token or len(KEY)<32:
        return jsonify(ok=False,message="Настройки Telegram неполные.")
    reserve_limits([("lerika-tg-config-minute",3,60)])
    target=PUBLIC_ORIGIN+PATH
    info=bot_call(token,"getWebhookInfo")
    if not isinstance(info,dict):
        return jsonify(ok=False,message="Не удалось проверить Telegram API.")
    current=info.get("url","")
    if current and current!=target:
        return jsonify(ok=False,message="У бота уже настроен другой webhook. Изменения не внесены.")
    if body["action"]=="activate":
        ok=bot_call(token,"setWebhook",{"url":target,"secret_token":secret_for(KEY),"allowed_updates":["message"],"max_connections":1,"drop_pending_updates":False})
        if ok is not True:
            return jsonify(ok=False,message="Telegram не подтвердил активацию.")
    elif body["action"]=="disable" and current==target:
        if bot_call(token,"deleteWebhook",{"drop_pending_updates":False}) is not True:
            return jsonify(ok=False,message="Telegram не подтвердил отключение.")
    info=bot_call(token,"getWebhookInfo")
    if not isinstance(info,dict):
        return jsonify(ok=False,message="Действие отправлено, итоговый статус не подтверждён.")
    active=info.get("url")==target
    pending=info.get("pending_update_count",0)
    return jsonify(ok=True,active=active,message=("Webhook подключён." if active else "Webhook отключён.")+" В очереди: "+str(pending if type(pending) is int else 0)+".",delivery_warning=bool(info.get("last_error_date")))

@app.post("/api/telegram/webhook")
def telegram_webhook():
    from telegram_core import secret_for,parse_update,answer_message
    from werkzeug.exceptions import TooManyRequests
    supplied=request.headers.get("X-Telegram-Bot-Api-Secret-Token","")
    if len(KEY)<32 or not secrets.compare_digest(supplied,secret_for(KEY)):
        abort(403)
    if not request.is_json or request.content_length is None or request.content_length>65536:
        abort(400)
    parsed=parse_update(request.get_json(silent=True))
    if parsed is None:
        return jsonify(ok=True)
    uid,cid,text=parsed
    # Ignore stale deliveries rather than reply to an old conversation.
    message=request.get_json()["message"]
    stamp=message.get("date")
    if type(stamp) is not int or not 0<=int(time.time())-stamp<=900:
        return jsonify(ok=True)
    # Store only hashed chat identifiers and update IDs in the existing rate-limit table.
    # A Telegram retry is acknowledged without a repeated reply.
    digest=hmac.new(KEY.encode(),str(cid).encode(),hashlib.sha256).hexdigest()[:32]
    is_admin=str(cid)==os.environ.get("LERIKA_TELEGRAM_ADMIN_CHAT_ID","").strip()
    from telegram_client_pilot import allowed,enrolled,registration,registration_keyboard,JOIN,LEAVE
    is_invited=not is_admin and allowed(cid,os.environ.get("LERIKA_TG_CLIENT_PILOT",""),os.environ.get("LERIKA_TG_PILOT_CHAT_IDS",""))
    try:
        # A ten-photo album produces ten individual Telegram updates.
        reserve_limits([("lerika-tg-update-"+str(uid),1,86400),("lerika-tg-global-minute",30,60),("lerika-tg-chat-"+digest,16 if is_admin or is_invited else 6,60)])
    except TooManyRequests:
        return jsonify(ok=True)
    def classify_preview(query):
        from ai_core import classify,fallback
        key=os.environ.get("LERIKA_GROQ_API_KEY","").strip()
        if not key:
            return fallback()
        try:
            reserve_limits([("lerika-tg-ai-day",10,86400),("lerika-tg-ai-minute",1,60)])
        except TooManyRequests:
            return fallback()
        return classify(query,key,LERIKA_AI_MODEL)
    pilot=None
    registered=False
    registration_reply=None
    if is_invited:
        try:
            registration_reply=registration(text,digest,db,lock)
            with db() as c:
                registered=enrolled(c,digest)
        except Exception:
            app.logger.warning("Telegram client pilot registration unavailable")
            return jsonify(method="sendMessage",chat_id=cid,text="Тестовая регистрация временно недоступна.")
        if registration_reply is not None or not registered:
            from telegram_intake import pilot_keyboard
            markup=pilot_keyboard(digest,db,lock,client=True) if registered else registration_keyboard(show_consent=text==JOIN)
            return jsonify(method="sendMessage",chat_id=cid,text=registration_reply or "Закрытый тест ЛериКа. Для доступа зарегистрируйтесь.",reply_markup=markup)
    if is_admin or registered:
        from telegram_intake import handle_test_order,pilot_keyboard
        from telegram_files import receive_attachment
        from telegram_stage_notifications import preference
        try:
            pilot=preference(text,digest,db,lock)
            if pilot is None:
                pilot=receive_attachment(message,digest,os.environ.get("LERIKA_TELEGRAM_BOT_TOKEN","").strip(),db,lock)
            if pilot is None:
                pilot=handle_test_order(text,digest,KEY,db,lock,allocate_number,existing_number,reserve_limits,notify_telegram_order)
        except TooManyRequests:
            pilot="Достигнут лимит тестовых заявок. Попробуйте позже."
        except Exception:
            app.logger.warning("Telegram test order could not be completed")
            pilot="Не удалось завершить действие. Проверьте кабинет; при необходимости повторите команду подтверждения."
    if pilot is not None:
        answer,markup=pilot,None
    else:
        answer,markup=answer_message(text,PUBLIC_ORIGIN,is_admin,classify_preview if is_admin else None)
    if (is_admin or registered) and text != "🌐 Инструменты сайта" and (pilot is not None or not (is_admin and isinstance(text,str) and text.startswith("/ai "))):
        try:
            markup=pilot_keyboard(digest,db,lock,client=registered)
            if pilot is None:
                answer="ЛериКа · Закрытый тест. Используйте кнопки для создания и отправки вымышленных заявок. Реальные клиентские данные пока не принимаются."
        except Exception:
            app.logger.warning("Telegram pilot keyboard unavailable")
    # Telegram can execute a Bot API method from the webhook response.
    # This avoids another outbound request and never exposes the bot token.
    result={"method":"sendMessage","chat_id":cid,"text":answer,"link_preview_options":{"is_disabled":True}}
    if markup:
        result["reply_markup"]=markup
    return jsonify(result)

@app.post("/api/admin/ai/assistant")
@admin
def ai_admin_assistant():
    from ai_core import classify
    if not valid_public_origin():
        abort(403)
    if not request.is_json:
        abort(415)
    if request.content_length is None or request.content_length>8192:
        abort(413)
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={"text","synthetic"} or body.get("synthetic") is not True:
        abort(400)
    query=body.get("text")
    if not isinstance(query,str) or not 1<=len(query.strip())<=800:
        abort(400)
    key=os.environ.get("LERIKA_GROQ_API_KEY","").strip()
    if not key:
        return jsonify(ok=False,message="Ключ Groq не настроен.")
    reserve_limits([("lerika-ai-core-day",15,86400),("lerika-ai-core-minute",2,60)])
    return jsonify(classify(query,key,LERIKA_AI_MODEL))

@app.post("/api/admin/ai/access")
@admin
def ai_admin_access():
    from urllib.error import HTTPError
    if not valid_public_origin():
        abort(403)
    key=os.environ.get("LERIKA_GROQ_API_KEY","").strip()
    if not key:
        return jsonify(ok=False,message="Ключ Groq не настроен.")
    reserve_limits([("lerika-ai-access-day",5,86400),("lerika-ai-access-minute",1,60)])
    try:
        req=Request("https://api.groq.com/openai/v1/models",headers={"Authorization":"Bearer "+key,"Accept":"application/json","User-Agent":"LERIKA-Groq-Diagnostic/1.0"},method="GET")
        with urlopen(req,timeout=10) as res:
            data=json.loads(res.read(262144))
        models=data.get("data")
        if not isinstance(models,list):
            return jsonify(ok=False,message="Groq вернул неожиданный формат списка моделей.")
        available=any(isinstance(m,dict) and m.get("id")==LERIKA_AI_MODEL for m in models)
        return jsonify(ok=available,message="API Groq доступен. "+("Qwen присутствует в списке моделей." if available else "Qwen отсутствует в списке моделей."))
    except HTTPError as exc:
        content_type=exc.headers.get("Content-Type","").lower() if exc.headers else ""
        edge=bool(exc.headers and exc.headers.get("cf-ray"))
        result=groq_diagnostic_error(exc)
        if "text/html" in content_type:
            result+=" Ответ HTML, а не стандартный JSON API."
        if edge:
            result+=" Присутствует заголовок Cloudflare (сам по себе не доказывает блокировку)."
        return jsonify(ok=False,message="Список моделей: "+result)
    except Exception:
        return jsonify(ok=False,message="Не удалось получить список моделей Groq.")

@app.post("/api/admin/ai/test")
@admin
def ai_admin_test():
    if not valid_public_origin():
        abort(403)
    if not os.environ.get("LERIKA_GROQ_API_KEY","").strip():
        return jsonify(ok=False,message="Ключ Groq не настроен.")
    reserve_limits([("lerika-ai-test-global-day",3,86400),("lerika-ai-test-global-minute",1,60)])
    ok,message=qwen_connection_test()
    return jsonify(ok=ok,message=message)

@app.route("/cabinet/ai-test",methods=["GET","POST"])
@admin
def ai_test_page():
    from html import escape
    result="Тест ещё не запускался."
    configured=bool(os.environ.get("LERIKA_GROQ_API_KEY","").strip())
    if request.method=="POST":
        if not valid_public_origin():
            abort(403)
        if configured:
            reserve_limits([("lerika-ai-test-global-day",3,86400),("lerika-ai-test-global-minute",1,60)])
            ok,result=qwen_connection_test()
        else:
            result="Ключ Groq не настроен."
    token=escape(str(session.get("csrf","")),quote=True)
    state="Ключ настроен." if configured else "Ключ не настроен."
    disabled="" if configured else " disabled"
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ЛериКа · Диагностика ИИ</title><link rel="stylesheet" href="/static/admin.css"></head><body><main><p><a href="/cabinet/">← В кабинет</a></p><section><h1>Диагностика Qwen</h1><p>Модель: '+LERIKA_AI_MODEL+'</p><p>'+state+'</p><p>Только контрольная фраза, без данных клиентов. До трёх запросов в сутки и одного в минуту. Запускайте только при активном бесплатном тарифе Groq.</p><form method="post" action="/cabinet/ai-test"><input type="hidden" name="csrf" value="'+token+'"><button class="primary" type="submit"'+disabled+'>Проверить Qwen</button></form><p role="status">'+escape(result)+'</p></section></main></body></html>')

@app.get("/support/telegram")
def support_telegram():
    username=os.environ.get("LERIKA_SUPPORT_BOT_USERNAME","").strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,28}bot",username,re.I) and 5<=len(username)<=32:
        return redirect("https://t.me/"+username,code=302)
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ЛериКа · Telegram</title><h1>Telegram-поддержка пока не подключена</h1><p>Вы можете отправить вопрос через форму поддержки ЛериКа.</p><p><a href="/showroom/#support">Вернуться к форме поддержки</a></p></html>',503,{"Content-Type":"text/html; charset=utf-8"})

@app.get("/cabinet/")
def index():
    return render_template("admin.html")



# Public showroom is served on the same origin as the installed app.
# Only the fixed, public LERIKA website is fetched. No session cookies or secrets
# are forwarded. The checked-in public snapshot is the offline-upstream fallback.
SITE_ROOT=Path(app.root_path).parent
SITE_URL="https://29018585-collab.github.io/lerika/"
_site_cache={}
_site_lock=Lock()

def site_asset(name, limit):
    if not (name in ("index.html","portfolio-api.js") or re.fullmatch(r"[A-Za-z0-9_.-]{1,160}\.(?:png|jpg|jpeg|webp|svg|gif|ico|css)",name,re.I)):
        abort(404)
    if name.startswith(".") or ".." in name:
        abort(404)
    if name=="portfolio-api.js" or immutable_asset(name):
        local=SITE_ROOT/name
        if not local.is_file() or local.stat().st_size>limit: abort(404)
        return local.read_bytes()
    with _site_lock:
        cached=_site_cache.get(name)
        if cached and time.monotonic()-cached[0]<60:
            return cached[1]
    url=SITE_URL+quote(name)
    try:
        with urlopen(Request(url,headers={"User-Agent":"LERIKA-showroom/1.1","Accept-Encoding":"identity"}),timeout=4) as r:
            if r.geturl()!=url or r.status!=200: raise ValueError("Unexpected upstream")
            raw=r.read(limit+1)
        if not raw or len(raw)>limit: raise ValueError("Invalid upstream asset")
        if name=="index.html" and (b'id="kitchen"' not in raw or b'id="portfolio-8"' not in raw):
            raise ValueError("Unexpected public page")
        with _site_lock:
            if len(_site_cache)>=24: _site_cache.clear()
            _site_cache[name]=(time.monotonic(),raw)
        return raw
    except Exception:
        if cached: return cached[1]
        local=SITE_ROOT/name
        if not local.is_file() or local.stat().st_size>limit: abort(404)
        return local.read_bytes()

@app.get("/showroom/")
def showroom():
    # Keep the deployed studio UI and its submission API in the same revision.
    local=SITE_ROOT/"index.html"
    raw=local.read_bytes() if local.is_file() and local.stat().st_size<=4*1024*1024 else b""
    html=(raw if b'id="lab-ai-panel"' in raw and b'id="estimate-panel"' in raw else site_asset("index.html",4*1024*1024)).decode("utf-8")
    html=html.replace('href="https://lerika-cabinet.onrender.com"','href="/cabinet/"')
    html=html.replace('href="https://lerika-cabinet.onrender.com/"','href="/cabinet/"')
    html=html.replace('href="https://lerika-cabinet.onrender.com/cabinet/"','href="/cabinet/"')
    origin=current_public_origin()
    html=html.replace(DEFAULT_PUBLIC_ORIGIN,origin)
    html=re.sub(r'(<meta name="lerika-portfolio-api" content=")[^"]*(")',lambda m:m[1]+"/"+m[2],html,count=1)
    html=html.replace("</head>",'<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/app-icon/192.png"><script defer src="/static/install.js"></script></head>',1)
    # Exact CSP hashes permit only the inline CSS/JS in this trusted public page.
    def hashes(tag):
        return " ".join("'sha256-"+base64.b64encode(hashlib.sha256(m.encode("utf-8")).digest()).decode("ascii")+"'" for m in re.findall(r"<"+tag+r"\b[^>]*>([\s\S]*?)</"+tag+r">",html,re.I) if m)
    response=app.make_response((html,200,{"Content-Type":"text/html; charset=utf-8"}))
    response.headers["Content-Security-Policy"]="default-src 'none'; script-src 'self' "+hashes("script")+"; style-src 'self' "+hashes("style")+"; img-src 'self' data: blob:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response

@app.get("/showroom/<name>")
def showroom_asset(name):
    if name=="index.html": return showroom()
    raw=site_asset(name,8*1024*1024)
    mime=mimetypes.guess_type(name)[0] or "application/octet-stream"
    # SVG is not a trusted inline document: no SVG uploads are exposed here.
    if name.lower().endswith(".svg"): abort(404)
    response=send_file(io.BytesIO(raw),mimetype=mime)
    if immutable_asset(name):
        response.headers["Cache-Control"]="public, max-age=31536000, immutable"
    return response

@app.get("/manifest.webmanifest")
def manifest():
    return send_file(Path(app.static_folder)/"manifest.webmanifest", mimetype="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return send_file(Path(app.static_folder)/"sw.js", mimetype="application/javascript")

@app.get("/app-icon/<name>.png")
def application_icon(name):
    if name not in ("192","512","512-maskable"):
        abort(404)
    size=192 if name=="192" else 512
    logo=Path(app.root_path).parent/"file_000000009ab0820ab36b48bd9c6cebc7.png"
    # Same approved brand asset as the public website.
    with Image.open(logo) as source:
        im=source.convert("RGBA")
        im.thumbnail((int(size*.72),int(size*.72)),Image.Resampling.LANCZOS)
        canvas=Image.new("RGBA",(size,size),"#211914")
        canvas.alpha_composite(im,((size-im.width)//2,(size-im.height)//2))
        out=io.BytesIO()
        canvas.convert("RGB").save(out,format="PNG")
        out.seek(0)
    return send_file(out,mimetype="image/png")

@app.get("/health")
def health():
    return jsonify(ok=True)

@app.post("/login")
def login():
    if not request.is_json: abort(415)
    password=str((request.json or {}).get("password",""))
    if len(password)>512: abort(400)
    now=int(time.time())
    key=limit_key("admin-login")
    reserve_limits([(key,8,900)])
    if not check_password_hash(PASSWORD,password):
        abort(401)
    clear_limit(key)
    session.update(admin=True,csrf=secrets.token_urlsafe(32),login=now)
    return jsonify(csrf=session["csrf"])

@app.get("/session")
@admin
def get_session():
    return jsonify(csrf=session["csrf"])

@app.post("/logout")
@admin
def logout():
    for key in ("admin","csrf","login"): session.pop(key,None)
    return jsonify(ok=True)


def client_origin():
    if not valid_public_origin() or request.headers.get("X-Lerika-Client")!="1":
        abort(403)

def sender_address():
    # Trust a configured edge header only from an internal proxy peer.
    # On a direct deployment, ignore caller-supplied forwarding headers.
    peer=request.remote_addr or ""
    try: address=ipaddress.ip_address(peer)
    except ValueError: return "unknown"
    header=os.environ.get("LERIKA_TRUSTED_CLIENT_IP_HEADER","CF-Connecting-IP" if os.environ.get("RENDER") else "")
    if header and (address.is_private or address.is_loopback):
        forwarded=request.headers.get(header,"")
        if forwarded:
            try: address=ipaddress.ip_address(forwarded.strip())
            except ValueError: pass
    if isinstance(address,ipaddress.IPv6Address) and address.ipv4_mapped:
        address=address.ipv4_mapped
    if isinstance(address,ipaddress.IPv6Address):
        return str(ipaddress.ip_network(str(address)+"/64",strict=False))
    return str(address)

def limit_key(action,identity=""):
    digest=hmac.new(KEY.encode(),(sender_address()+"\x00"+identity).encode(),hashlib.sha256).hexdigest()
    return action+":"+digest

def reserve_limits(rules):
    now=int(time.time())
    with db() as c:
        lock(c,82005)
        c.execute("DELETE FROM client_limits WHERE since<?",(now-86400,))
        pending=[]
        for key,maximum,period in rules:
            row=c.execute("SELECT count,since FROM client_limits WHERE action=?",(key,)).fetchone()
            count=row["count"] if row and now-row["since"]<period else 0
            since=row["since"] if count else now
            if count>=maximum: abort(429)
            pending.append((key,count+1,since))
        for rec in pending:
            c.execute("INSERT INTO client_limits VALUES(?,?,?) ON CONFLICT(action) DO UPDATE SET count=excluded.count,since=excluded.since",rec)

def clear_limit(key):
    with db() as c:
        lock(c,82005)
        c.execute("DELETE FROM client_limits WHERE action=?",(key,))

def client_limit(action,maximum,period):
    reserve_limits([(limit_key(action),maximum,period)])

def client_id():
    return session.get("client") if time.time()-session.get("client_login",0)<43200 else None

@app.post("/api/client/register")
def client_register():
    client_origin()
    if not request.is_json: abort(415)
    d=request.get_json()
    if not isinstance(d,dict) or not all(isinstance(d.get(k),str) for k in ("name","email","password")) or d.get("consent") is not True: abort(400)
    name=d["name"].strip();email=d["email"].strip().lower();password=d["password"]
    if not (1<=len(name)<=100 and len(email)<=150 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email) and 12<=len(password)<=128): abort(400)
    client_limit("register",20,3600)
    cid=secrets.token_hex(16)
    hashed=generate_password_hash(password)
    with db() as c:
        lock(c,82006)
        if c.execute("SELECT id FROM clients WHERE email=?",(email,)).fetchone(): abort(409)
        c.execute("INSERT INTO clients VALUES(?,?,?,?,?)",(cid,email,name,hashed,int(time.time())))
    session.update(client=cid,client_login=int(time.time()))
    return jsonify(ok=True),201

@app.post("/api/client/login")
def client_login():
    client_origin()
    if not request.is_json: abort(415)
    d=request.get_json()
    if not isinstance(d,dict) or not all(isinstance(d.get(k),str) for k in ("email","password")): abort(400)
    email=d["email"].strip().lower();password=d["password"]
    if not (1<=len(email)<=150 and 1<=len(password)<=128): abort(400)
    key=limit_key("client-login-account",email)
    reserve_limits([(limit_key("client-login"),50,900),(key,8,900)])
    with db() as c: row=c.execute("SELECT id,password_hash FROM clients WHERE email=?",(email,)).fetchone()
    valid=check_password_hash(row["password_hash"] if row else PASSWORD,password)
    if not row or not valid: abort(401)
    clear_limit(key)
    session.update(client=row["id"],client_login=int(time.time()))
    return jsonify(ok=True)

@app.post("/api/client/logout")
def client_logout():
    client_origin()
    session.pop("client",None);session.pop("client_login",None)
    return jsonify(ok=True)

@app.get("/api/client/session")
def client_session():
    cid=client_id()
    if not cid: abort(401)
    with db() as c:
        row=c.execute("SELECT name,email FROM clients WHERE id=?",(cid,)).fetchone()
        if not row: abort(401)
        orders=[dict(x) for x in c.execute("SELECT p.id,p.title,p.stage,p.status,r.created,n.number FROM client_requests cr JOIN projects p ON p.id=cr.project JOIN design_requests r ON r.id=p.id LEFT JOIN request_numbers n ON n.request_id=r.id WHERE cr.client=? ORDER BY r.created DESC",(cid,))]
    for order in orders:
        order["number"]=request_number(order["number"]) if order["number"] is not None else order["id"][:12]
    return jsonify(name=row["name"],email=row["email"],orders=orders)

@app.get("/api/clients")
@admin
def clients_list():
    with db() as c:
        rows=[dict(x) for x in c.execute("SELECT id,name,email,created FROM clients ORDER BY created DESC")]
    return jsonify(clients=rows)

PRICE_MATERIALS={
    "корпус":["ЛДСП","МДФ","Фанера","Мебельный щит","Массив дерева"],
    "фасады":["ЛДСП","МДФ плёнка ПВХ","МДФ эмаль","МДФ акрил","МДФ пластик HPL","МДФ шпон","Фанера","Массив дерева","Стекло (визуальный аналог)"]
}
class PriceImportError(ValueError):
    def __init__(self,row,message):
        super().__init__(message)
        self.row=row

def price_rows(file):
    raw=file.read(2*1024*1024+1)
    if not raw or len(raw)>2*1024*1024: abort(413)
    name=(file.filename or "").lower()
    formulas=set()
    if name.endswith(".csv"):
        try: content=raw.decode("utf-8-sig")
        except UnicodeDecodeError: content=raw.decode("cp1251")
        if not content.strip(): raise PriceImportError(1,"Пустой файл")
        delimiter=";" if ";" in content.splitlines()[0] else ","
        rows=list(csv.reader(io.StringIO(content),delimiter=delimiter))
    elif name.endswith(".xlsx"):
        from openpyxl import load_workbook
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist())>100 or sum(x.file_size for x in z.infolist())>20*1024*1024: abort(413)
            if any(x.flag_bits&1 for x in z.infolist()): abort(400)
        wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True,keep_links=False)
        try:
            ws=wb["Прайс"] if "Прайс" in wb.sheetnames else wb.active
            if (ws.max_row and ws.max_row>200) or (ws.max_column and ws.max_column>50):
                raise PriceImportError(1,"Допустимо до 200 строк и 50 столбцов")
            # Bound actual iteration even if worksheet dimension metadata is absent.
            rows=list(ws.iter_rows(min_row=1,max_row=201,max_col=51,values_only=True))
            if (len(rows)>200 and any(x is not None for x in rows[200])) or any(len(row)>50 and row[50] is not None for row in rows):
                raise PriceImportError(1,"Допустимо до 200 строк и 50 столбцов")
            rows=[row[:50] for row in rows[:200]]
            # Cached Excel values are read without executing formulas. A missing
            # cache must not be mistaken for an intentionally blank price.
            source=load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
            try:
                for ri,row in enumerate(source[ws.title].iter_rows(min_row=1,max_row=200,max_col=50),1):
                    for ci,cell in enumerate(row):
                        if cell.data_type=="f": formulas.add((ri,ci))
            finally: source.close()
        finally: wb.close()
    else: abort(415)
    if not rows or len(rows)>200 or any(len(row)>50 for row in rows):
        raise PriceImportError(1,"Допустимо до 200 строк и 50 столбцов")
    def norm(value):
        return " ".join(str(value if value is not None else "").split())
    header=[norm(x).casefold() for x in rows[0]]
    required=("группа","материал","цена")
    if any(header.count(k)!=1 for k in required):
        raise PriceImportError(1,"Нужны уникальные столбцы «Группа», «Материал», «Цена»")
    gi,mi,vi=(header.index(k) for k in required)
    entries=[];seen=set()
    for ri,row in enumerate(rows[1:],2):
        def at(i): return row[i] if i<len(row) else None
        group,material,value=norm(at(gi)).casefold(),norm(at(mi)),at(vi)
        if not norm(value):
            if (ri,vi) in formulas:
                raise PriceImportError(ri,"Формула цены не имеет сохранённого результата. Пересчитайте и сохраните файл в Excel")
            continue
        match=next((x for x in PRICE_MATERIALS.get(group,[]) if x.casefold()==material.casefold()),None)
        if not match: raise PriceImportError(ri,"Неизвестная группа или материал")
        if (group,match) in seen: raise PriceImportError(ri,"Повторяющаяся ставка")
        try:
            if isinstance(value,bool): raise InvalidOperation
            cleaned="".join(str(value).split()).replace(",",".")
            if len(cleaned)>50: raise InvalidOperation
            price=Decimal(cleaned)
            if not price.is_finite() or not (0<price<=1000000): raise InvalidOperation
            price=price.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            if price<=0: raise InvalidOperation
        except InvalidOperation:
            raise PriceImportError(ri,"Цена должна быть положительным числом до 1 000 000 ₽")
        entries.append(dict(group=group,material=match,price=float(price)))
        seen.add((group,match))
    if not entries: raise PriceImportError(1,"Нет заполненных ставок")
    return entries

@app.get("/public/prices")
def public_prices():
    with db() as c: row=c.execute("SELECT entries,updated FROM price_catalog WHERE id=1").fetchone()
    return jsonify(entries=json.loads(row["entries"]) if row else [],updated=row["updated"] if row else None)

@app.post("/api/prices")
@admin
def upload_prices():
    f=request.files.get("file")
    if not f: abort(400)
    try: entries=price_rows(f)
    except PriceImportError as e: return jsonify(error="Строка "+str(e.row)+": "+str(e),row=e.row),400
    except (ValueError,TypeError,IndexError,KeyError,zipfile.BadZipFile,UnicodeError): return jsonify(error="Не удалось прочитать прайс. Проверьте формат CSV/XLSX"),400
    now=int(time.time())
    with db() as c:
        lock(c,82007)
        c.execute("INSERT INTO price_catalog VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET entries=excluded.entries,updated=excluded.updated",(json.dumps(entries,ensure_ascii=False),now))
    return jsonify(entries=entries,updated=now)

def project_record(p):
    data=request.get_json()
    if not isinstance(data,dict): abort(400)
    try:
        cat=int(data["category"]); stage=int(data["stage"])
        title=data["title"].strip(); desc=data["description"].strip()
        status=data["status"]; published=data["published"]
    except (KeyError,ValueError,TypeError,AttributeError): abort(400)
    if not (1<=cat<=8 and 1<=stage<=6 and 1<=len(title)<=150 and len(desc)<=5000 and status in ("work","ready") and type(published) is bool): abort(400)
    if status=="ready" and stage!=6: abort(400)
    return (cat,title,desc,stage,status,int(published),int(time.time()),p)

# Public intake accepts only new private drafts, never changes existing projects.
@app.post("/api/design-requests")
@app.post("/api/order-requests")
def design_request():
    order=request.path=="/api/order-requests"
    source=request.form.get("source","order" if order else "ai")
    if source not in (("order","project","3d","config","plan","engineering","support","partner") if order else ("ai",)):
        abort(400)
    if not valid_public_origin() or request.headers.get("X-Lerika-Studio")!=("5.8" if order else "5.6"):
        abort(403)
    if request.mimetype!="multipart/form-data":
        abort(415)
    rid=request.form.get("request_id","")
    title=request.form.get("title","").strip()
    contact=request.form.get("contact","").strip()
    brief=request.form.get("brief","").strip()
    room=request.form.get("room","")
    categories={"Кухня":1,"Прихожая":3,"Спальня":4,"Гостиная":6,"Детская":5,"Гардеробная":7,"Другое":8}
    if not (request.form.get("consent")=="yes" and re.fullmatch(r"[a-f0-9]{32}",rid) and 1<=len(title)<=100 and 1<=len(contact)<=150 and 1<=len(brief)<=4500 and room in categories):
        abort(400)
    # A random request ID makes network retries idempotent.
    with db() as c:
        if c.execute("SELECT id FROM design_requests WHERE id=?",(rid,)).fetchone():
            return jsonify(id=rid,number=existing_number(c,rid)),200
    reserve_limits([(limit_key("intake-hour"),12,3600),(limit_key("intake-day"),40,86400)])
    files=request.files.getlist("files")
    collages=request.files.getlist("collage")
    if len(files)>(10 if order else 6) or len(collages)>(0 if order else 1) or any(k not in ("files","collage") for k in request.files):
        abort(400)
    if not order and not files and not collages and "Пожелания: не указаны" in brief:
        abort(400)
    attachments=[]
    total=0
    for f in files+collages:
        is_collage=bool(collages and f is collages[0])
        name=Path((f.filename or "").replace(chr(92),"/")).name[:160]
        suffix=Path(name).suffix.lower()
        allowed=(".jpg",".jpeg",".png",".webp",".pdf",".zip",".rar",".7z",".doc",".docx",".xls",".xlsx",".xlsm",".csv",".txt",".dxf",".dwg",".sto",".skp",".heic",".heif",".tif",".tiff") if order else (".jpg",".jpeg",".png",".webp",".pdf")
        if suffix not in allowed or (is_collage and suffix!=".png"):
            abort(415)
        limit=(12 if order else 2 if is_collage else 8)*1024*1024
        raw=f.read(limit+1)
        if not raw or len(raw)>limit: abort(413)
        if not is_collage:
            total+=len(raw)
            if total>12*1024*1024: abort(413)
        if order:
            # Original files only; never extract archives, run macros, or expose inline.
            if suffix==".pdf" and not raw.startswith(b"%PDF-"): abort(415)
            if suffix in (".zip",".docx",".xlsx",".xlsm") and not raw.startswith((b"PK\x03\x04",b"PK\x05\x06")): abort(415)
            if suffix==".rar" and not raw.startswith(b"Rar!\x1a\x07"): abort(415)
            if suffix==".7z" and not raw.startswith(b"7z\xbc\xaf\x27\x1c"): abort(415)
            mime="application/octet-stream"; image=0
        elif suffix==".pdf":
            if not raw.startswith(b"%PDF-"): abort(415)
            mime="application/octet-stream"; image=0
        else:
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in ("JPEG","PNG","WEBP") or im.width*im.height>25000000:
                        abort(415)
                    if is_collage and im.format!="PNG": abort(415)
                    im=ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((1800,1800))
                    out=io.BytesIO()
                    if is_collage:
                        im.save(out,"PNG",optimize=True)
                        mime="image/png"
                    else:
                        im.save(out,"JPEG",quality=86,optimize=True)
                        mime="image/jpeg"
                    raw=out.getvalue(); image=1
            except Exception:
                abort(415)
            if not is_collage:
                name=Path(name).stem[:150]+".jpg"
        attachments.append((name,mime,image,raw))
    now=int(time.time())
    private_brief="Источник заявки: "+REQUEST_SOURCES[source]+"\nНазвание: "+title+"\nКонтакт: "+contact+"\n\n"+brief
    with db() as c:
        lock(c,82003)
        if c.execute("SELECT id FROM design_requests WHERE id=?",(rid,)).fetchone():
            return jsonify(id=rid,number=existing_number(c,rid)),200
        # Sender limits were reserved before attachment processing; retain the storage cap.
        used=c.execute("SELECT COALESCE(SUM(length(data)),0) AS bytes_used FROM files").fetchone()["bytes_used"]
        if used+sum(len(v[3]) for v in attachments)>350*1024*1024: abort(413)
        c.execute("INSERT INTO projects(category,title,description,stage,status,published,updated,id) VALUES(?,?,?,?,?,?,?,?)",(categories[room],("Заказ" if order else "Заявка")+" · "+room+" · "+rid[:6],"Заявка на заказ ЛериКа" if order else "Заявка из дизайн-студии ЛериКа",1,"work",0,now,rid))
        c.execute("INSERT INTO design_briefs VALUES(?,?)",(rid,private_brief))
        for name,mime,image,raw in attachments:
            # Attachments (including the collage) are private by default.
            c.execute("INSERT INTO files VALUES(?,?,?,?,?,?,0,?)",(secrets.token_hex(16),rid,1,name,mime,image,raw))
        c.execute("INSERT INTO design_requests VALUES(?,?)",(rid,now))
        number=allocate_number(c,rid)
        c.execute("UPDATE projects SET title=? WHERE id=?",(("Заказ" if order else "Заявка")+" · "+room+" · "+number,rid))
        cid=client_id()
        if cid and c.execute("SELECT id FROM clients WHERE id=?",(cid,)).fetchone():
            c.execute("INSERT INTO client_requests VALUES(?,?)",(rid,cid))
    # The database transaction has ended. A Telegram error must not roll back intake.
    notify_telegram_order(number,source,room,len(attachments))
    return jsonify(id=rid,number=number),201

@app.get("/api/projects")
@admin
def projects():
    with db() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM projects ORDER BY updated DESC")]
        for p in rows:
            private=c.execute("SELECT brief FROM design_briefs WHERE project=?",(p["id"],)).fetchone()
            if private: p["private_brief"]=private["brief"]
            intake=c.execute("SELECT created FROM design_requests WHERE id=?",(p["id"],)).fetchone()
            if intake:
                first=(private["brief"].split("\n",1)[0] if private else "")
                matched=next((k for k,v in REQUEST_SOURCES.items() if first=="Источник заявки: "+v),None)
                if not matched:
                    matched="ai" if private and "ЛЕРИКА LAB V5.6 / Задание дизайнеру" in private["brief"] else "legacy"
                p["request_source"]=matched
                p["request_created"]=intake["created"]
                p["request_number"]=existing_number(c,p["id"]) or p["id"][:12]
            p["files"]=[dict(f) for f in c.execute("SELECT id,stage,name,mime,image,public FROM files WHERE project=? ORDER BY stage,id",(p["id"],))]
        covers=[dict(x) for x in c.execute("SELECT * FROM covers")]
    return jsonify(projects=rows,covers=covers,categories=CATEGORIES,stages=STAGES)

@app.post("/api/projects")
@admin
def create_project():
    p=secrets.token_hex(16)
    rec=project_record(p)
    # New projects are always drafts, independent of client input.
    rec=(*rec[:5],0,*rec[6:])
    with db() as c:
        c.execute("INSERT INTO projects(category,title,description,stage,status,published,updated,id) VALUES(?,?,?,?,?,?,?,?)",rec)
    return jsonify(id=p),201

@app.put("/api/projects/<p>")
@admin
def edit_project(p):
    from telegram_stage_notifications import event_for_edit,deliver_event
    from telegram_client_pilot import notification_chat
    from telegram_core import bot_call
    rec=project_record(p)
    event=None
    recipient=""
    with db() as c:
        lock(c,82003)
        if rec[5] and c.execute("SELECT id FROM design_requests WHERE id=?",(p,)).fetchone(): abort(403)
        old=c.execute("SELECT stage,status FROM projects WHERE id=?",(p,)).fetchone()
        if not c.execute("UPDATE projects SET category=?,title=?,description=?,stage=?,status=?,published=?,updated=? WHERE id=?",rec).rowcount: abort(404)
        c.execute("DELETE FROM covers WHERE file IN (SELECT id FROM files WHERE project=?) AND category<>?",(p,rec[0]))
        event=event_for_edit(c,p,old,rec[3],rec[4])
        recipient=notification_chat(c,event,KEY,os.environ.get("LERIKA_TELEGRAM_ADMIN_CHAT_ID","").strip(),os.environ.get("LERIKA_TG_CLIENT_PILOT",""),os.environ.get("LERIKA_TG_PILOT_CHAT_IDS",""))
    if event is not None and recipient:
        try:
            if not deliver_event(event,KEY,recipient,os.environ.get("LERIKA_TELEGRAM_BOT_TOKEN","").strip(),bot_call):
                app.logger.warning("Telegram test stage notification not delivered")
        except Exception:
            app.logger.warning("Telegram test stage notification failed")
    return jsonify(ok=True)

@app.post("/api/projects/<p>/files")
@admin
def upload(p):
    f=request.files.get("file")
    try: stage=int(request.form.get("stage","0"))
    except ValueError: abort(400)
    if not f or not 1<=stage<=6: abort(400)
    name=Path(f.filename or "file").name[:160]
    raw=f.read(12*1024*1024+1)
    if not raw or len(raw)>12*1024*1024: abort(413)
    is_image=0; mime="application/octet-stream"
    # Only decoded, re-encoded raster photos may ever be made public.
    if Path(name).suffix.lower() in (".jpg",".jpeg",".png",".webp"):
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im=ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1800,1800))
                buf=io.BytesIO(); im.save(buf,"JPEG",quality=86,optimize=True)
                raw=buf.getvalue(); is_image=1; mime="image/jpeg"
        except Exception: abort(415)
    with db() as c:
        lock(c,82003)
        if not c.execute("SELECT 1 FROM projects WHERE id=?",(p,)).fetchone(): abort(404)
        if c.execute("SELECT COALESCE(SUM(length(data)),0) AS bytes_used FROM files").fetchone()["bytes_used"]+len(raw)>350*1024*1024: abort(413)
        fid=secrets.token_hex(16)
        c.execute("INSERT INTO files VALUES(?,?,?,?,?,?,0,?)",(fid,p,stage,name,mime,is_image,raw))
    return jsonify(id=fid),201

@app.put("/api/files/<fid>")
@admin
def file_visibility(fid):
    data=request.get_json()
    if not isinstance(data,dict) or type(data.get("public")) is not bool: abort(400)
    with db() as c:
        lock(c,82003)
        f=c.execute("SELECT image,project FROM files WHERE id=?",(fid,)).fetchone()
        if not f: abort(404)
        if data["public"] and not f["image"]: abort(400)
        if data["public"] and c.execute("SELECT id FROM design_requests WHERE id=?",(f["project"],)).fetchone(): abort(403)
        c.execute("UPDATE files SET public=? WHERE id=?",(int(data["public"]),fid))
        if not data["public"]: c.execute("DELETE FROM covers WHERE file=?",(fid,))
    return jsonify(ok=True)

@app.put("/api/covers/<int:cat>")
@admin
def set_cover(cat):
    data=request.get_json()
    if not isinstance(data,dict) or not isinstance(data.get("file"),str) or not 1<=cat<=8: abort(400)
    with db() as c:
        f=c.execute("SELECT f.id FROM files f JOIN projects p ON p.id=f.project WHERE f.id=? AND f.image=1 AND f.public=1 AND p.published=1 AND NOT EXISTS (SELECT 1 FROM design_requests dr WHERE dr.id=p.id) AND p.category=?",(data["file"],cat)).fetchone()
        if not f: abort(400)
        c.execute("INSERT INTO covers VALUES(?,?) ON CONFLICT(category) DO UPDATE SET file=excluded.file",(cat,f["id"]))
    return jsonify(ok=True)

@app.get("/api/files/<fid>")
@admin
def private_file(fid):
    with db() as c: f=c.execute("SELECT * FROM files WHERE id=?",(fid,)).fetchone()
    if not f: abort(404)
    return send_file(io.BytesIO(f["data"]),mimetype=f["mime"],as_attachment=not f["image"],download_name=f["name"])

def delete_project_rows(c,p):
    c.execute("DELETE FROM covers WHERE file IN (SELECT id FROM files WHERE project=?)",(p,))
    c.execute("DELETE FROM files WHERE project=?",(p,))
    c.execute("DELETE FROM client_requests WHERE project=?",(p,))
    c.execute("DELETE FROM design_briefs WHERE project=?",(p,))
    c.execute("DELETE FROM request_numbers WHERE request_id=?",(p,))
    c.execute("DELETE FROM design_requests WHERE id=?",(p,))
    c.execute("DELETE FROM projects WHERE id=?",(p,))

def confirm_delete():
    if not request.is_json or not isinstance(request.json,dict) or request.json.get("confirm") is not True:
        abort(400)

@app.delete("/api/files/<fid>")
@admin
def delete_file(fid):
    confirm_delete()
    with db() as c:
        lock(c,82003)
        if not c.execute("SELECT id FROM files WHERE id=?",(fid,)).fetchone(): abort(404)
        c.execute("DELETE FROM covers WHERE file=?",(fid,))
        c.execute("DELETE FROM files WHERE id=?",(fid,))
    return jsonify(ok=True)

@app.delete("/api/projects/<p>")
@admin
def delete_project(p):
    confirm_delete()
    with db() as c:
        lock(c,82003)
        if not c.execute("SELECT id FROM projects WHERE id=?",(p,)).fetchone(): abort(404)
        delete_project_rows(c,p)
    return jsonify(ok=True)

@app.delete("/api/clients/<cid>")
@admin
def delete_client(cid):
    confirm_delete()
    with db() as c:
        lock(c,82003)
        if not c.execute("SELECT id FROM clients WHERE id=?",(cid,)).fetchone(): abort(404)
        projects=list(c.execute("SELECT project FROM client_requests WHERE client=?",(cid,)))
        for p in projects: delete_project_rows(c,p["project"])
        c.execute("DELETE FROM clients WHERE id=?",(cid,))
    return jsonify(ok=True,deleted_requests=len(projects))

@app.get("/public/portfolio")
def public_portfolio():
    with db() as c:
        # Drafts and private attachments never leave authenticated endpoints.
        rows=[dict(p) for p in c.execute("SELECT id,category,title,description,stage,status FROM projects WHERE published=1 AND NOT EXISTS (SELECT 1 FROM design_requests dr WHERE dr.id=projects.id) ORDER BY updated DESC")]
        for p in rows:
            p["photos"]=[dict(f) for f in c.execute("SELECT id,stage FROM files WHERE project=? AND image=1 AND public=1 ORDER BY stage,id",(p["id"],))]
        covers={str(f["category"]):f["file"] for f in c.execute("SELECT c.* FROM covers c JOIN files f ON f.id=c.file JOIN projects p ON p.id=f.project WHERE f.public=1 AND f.image=1 AND p.published=1 AND NOT EXISTS (SELECT 1 FROM design_requests dr WHERE dr.id=p.id) AND p.category=c.category")}
    return jsonify(projects=rows,covers=covers)

@app.get("/public/photos/<fid>")
def public_photo(fid):
    with db() as c:
        f=c.execute("SELECT f.data,f.mime FROM files f JOIN projects p ON p.id=f.project WHERE f.id=? AND f.image=1 AND f.public=1 AND p.published=1 AND NOT EXISTS (SELECT 1 FROM design_requests dr WHERE dr.id=p.id)",(fid,)).fetchone()
    if not f: abort(404)
    return send_file(io.BytesIO(f["data"]),mimetype=f["mime"])
