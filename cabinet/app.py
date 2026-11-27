import os, sqlite3, secrets, time, io, json, re, hashlib, base64, mimetypes
from urllib.request import urlopen, Request
from urllib.parse import quote
from threading import Lock
from pathlib import Path
from functools import wraps
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
CATEGORIES=["Кухни","Шкафы","Прихожие","Спальни","Детские","Гостиные","Гардеробные","Нестандартные системы хранения"]
STAGES=["Исходное помещение","Замеры и эскизы","3D-проект","Изготовление","Монтаж","Готовая мебель"]
ORIGIN="https://29018585-collab.github.io"
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

def db():
    if DATABASE_URL:
        return PostgresDB()
    c=sqlite3.connect(DB,timeout=10)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c
def lock(c,key):
    if DATABASE_URL:
        c.execute("SELECT pg_advisory_xact_lock(?)",(key,))
    else:
        c.execute("BEGIN IMMEDIATE")

if not SETUP_REQUIRED:
  with db() as c:
    lock(c,82001)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, category INTEGER NOT NULL CHECK(category BETWEEN 1 AND 8), title TEXT NOT NULL, description TEXT NOT NULL, stage INTEGER NOT NULL CHECK(stage BETWEEN 1 AND 6), status TEXT NOT NULL CHECK(status IN ('work','ready')), published INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), stage INTEGER NOT NULL CHECK(stage BETWEEN 1 AND 6), name TEXT NOT NULL, mime TEXT NOT NULL, image INTEGER NOT NULL, public INTEGER NOT NULL DEFAULT 0, data BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS covers(category INTEGER PRIMARY KEY CHECK(category BETWEEN 1 AND 8), file TEXT NOT NULL REFERENCES files(id));
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY CHECK(id=1), count INTEGER NOT NULL, since INTEGER NOT NULL);
    """)


@app.before_request
def configuration_guard():
    if not SETUP_REQUIRED:
        return None
    if request.path=="/" and request.method in ("GET","HEAD"):
        return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ЛериКа · Настройка</title><h1>ЛериКа — личный кабинет</h1><p>Кабинет ожидает завершения защищённой настройки администратором. Вход и загрузка файлов пока недоступны.</p></html>',503,{"Content-Type":"text/html; charset=utf-8"})
    return jsonify(error="Service not configured"),503

@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"]="nosniff"
    r.headers["Referrer-Policy"]="no-referrer"
    r.headers["X-Frame-Options"]="DENY"
    r.headers.setdefault("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; manifest-src 'self'; worker-src 'self'")
    r.headers["Cache-Control"]="no-store"
    if request.path.startswith("/public/"):
        r.headers["Access-Control-Allow-Origin"]=ORIGIN
    return r

def admin(f):
    @wraps(f)
    def inner(*a,**kw):
        if not session.get("admin") or time.time()-session.get("login",0)>43200:
            abort(401)
        if request.method not in ("GET","HEAD"):
            if not secrets.compare_digest(request.headers.get("X-CSRF",""),session.get("csrf","!")):
                abort(403)
        return f(*a,**kw)
    return inner

@app.get("/")
def home():
    return redirect("/showroom/",code=302)

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
    html=site_asset("index.html",4*1024*1024).decode("utf-8")
    html=html.replace('href="https://lerika-cabinet.onrender.com"','href="/cabinet/"')
    html=html.replace('href="https://lerika-cabinet.onrender.com/"','href="/cabinet/"')
    html=html.replace('href="https://lerika-cabinet.onrender.com/cabinet/"','href="/cabinet/"')
    html=re.sub(r'(<meta name="lerika-portfolio-api" content=")[^"]*(")',lambda m:m[1]+"https://lerika-cabinet.onrender.com"+m[2],html,count=1)
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
    return send_file(io.BytesIO(raw),mimetype=mime)

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
    with db() as c:
        lock(c,82002)
        row=c.execute("SELECT count,since FROM attempts WHERE id=1").fetchone()
        count=row["count"] if row and now-row["since"]<900 else 0
        since=row["since"] if count else now
        if count>=8: abort(429)
        if not check_password_hash(PASSWORD,password):
            c.execute("INSERT INTO attempts VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET count=excluded.count,since=excluded.since",(count+1,since))
            c.commit()
            abort(401)
        c.execute("DELETE FROM attempts WHERE id=1")
    session.clear()
    session.update(admin=True,csrf=secrets.token_urlsafe(32),login=now)
    return jsonify(csrf=session["csrf"])

@app.get("/session")
@admin
def get_session():
    return jsonify(csrf=session["csrf"])

@app.post("/logout")
@admin
def logout():
    session.clear()
    return jsonify(ok=True)

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

@app.get("/api/projects")
@admin
def projects():
    with db() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM projects ORDER BY updated DESC")]
        for p in rows:
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
    rec=project_record(p)
    with db() as c:
        if not c.execute("UPDATE projects SET category=?,title=?,description=?,stage=?,status=?,published=?,updated=? WHERE id=?",rec).rowcount: abort(404)
        c.execute("DELETE FROM covers WHERE file IN (SELECT id FROM files WHERE project=?) AND category<>?",(p,rec[0]))
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
        f=c.execute("SELECT image FROM files WHERE id=?",(fid,)).fetchone()
        if not f: abort(404)
        if data["public"] and not f["image"]: abort(400)
        c.execute("UPDATE files SET public=? WHERE id=?",(int(data["public"]),fid))
        if not data["public"]: c.execute("DELETE FROM covers WHERE file=?",(fid,))
    return jsonify(ok=True)

@app.put("/api/covers/<int:cat>")
@admin
def set_cover(cat):
    data=request.get_json()
    if not isinstance(data,dict) or not isinstance(data.get("file"),str) or not 1<=cat<=8: abort(400)
    with db() as c:
        f=c.execute("SELECT f.id FROM files f JOIN projects p ON p.id=f.project WHERE f.id=? AND f.image=1 AND f.public=1 AND p.published=1 AND p.category=?",(data["file"],cat)).fetchone()
        if not f: abort(400)
        c.execute("INSERT INTO covers VALUES(?,?) ON CONFLICT(category) DO UPDATE SET file=excluded.file",(cat,f["id"]))
    return jsonify(ok=True)

@app.get("/api/files/<fid>")
@admin
def private_file(fid):
    with db() as c: f=c.execute("SELECT * FROM files WHERE id=?",(fid,)).fetchone()
    if not f: abort(404)
    return send_file(io.BytesIO(f["data"]),mimetype=f["mime"],as_attachment=not f["image"],download_name=f["name"])

@app.get("/public/portfolio")
def public_portfolio():
    with db() as c:
        # Drafts and private attachments never leave authenticated endpoints.
        rows=[dict(p) for p in c.execute("SELECT id,category,title,description,stage,status FROM projects WHERE published=1 ORDER BY updated DESC")]
        for p in rows:
            p["photos"]=[dict(f) for f in c.execute("SELECT id,stage FROM files WHERE project=? AND image=1 AND public=1 ORDER BY stage,id",(p["id"],))]
        covers={str(f["category"]):f["file"] for f in c.execute("SELECT c.* FROM covers c JOIN files f ON f.id=c.file JOIN projects p ON p.id=f.project WHERE f.public=1 AND f.image=1 AND p.published=1 AND p.category=c.category")}
    return jsonify(projects=rows,covers=covers)

@app.get("/public/photos/<fid>")
def public_photo(fid):
    with db() as c:
        f=c.execute("SELECT f.data FROM files f JOIN projects p ON p.id=f.project WHERE f.id=? AND f.image=1 AND f.public=1 AND p.published=1",(fid,)).fetchone()
    if not f: abort(404)
    return send_file(io.BytesIO(f["data"]),mimetype="image/jpeg")
