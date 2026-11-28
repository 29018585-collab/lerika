"""Read-only public QA showroom. No import of the production cabinet or database."""
import base64, hashlib, mimetypes, re
from pathlib import Path
from flask import Flask, abort, jsonify, redirect, send_file

app = Flask(__name__, static_folder="static")
ROOT = Path(__file__).resolve().parent.parent
# Run the exact release candidate tests in a separate process with NO inherited
# database configuration, tokens, credentials or production environment.
import os, subprocess, sys, threading
REGRESSION={"state":"pending","groups":{}}
def run_isolated_regression():
    env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"LANG":"C.UTF-8","PYTHONUNBUFFERED":"1"}
    groups=[
        ("telegram",["test_telegram_files_qa"]),
        ("link_http",["test_design_studio.StudioTests.test_telegram_web_link_http_owner_scope"]),
        ("cabinet",["test_design_studio"]),
    ]
    REGRESSION["state"]="running"
    for label,tests in groups:
        try:
            runner=subprocess.run([sys.executable,"-m","unittest","-v",*tests],cwd=ROOT/"cabinet",env=env,capture_output=True,text=True,timeout=240)
            log=runner.stdout+"\n"+runner.stderr
            match=re.search(r"Ran (\d+) tests?",log)
            result={"ok":runner.returncode==0,"tests":int(match.group(1)) if match else None,"exit":runner.returncode}
            print("LERIKA_V550_QA "+label+" "+str(result),flush=True)
            if runner.returncode!=0:
                print("LERIKA_V550_QA_FAILURE "+label+" "+log[-8000:],flush=True)
        except subprocess.TimeoutExpired as e:
            result={"ok":False,"error":"timeout"}
            print("LERIKA_V550_QA_TIMEOUT "+label,flush=True)
            if e.stderr:
                print("LERIKA_V550_QA_PARTIAL "+label+" "+str(e.stderr)[-2000:],flush=True)
        except Exception:
            result={"ok":False,"error":"runner"}
            print("LERIKA_V550_QA_RUNNER_ERROR "+label,flush=True)
        REGRESSION["groups"][label]=result
    REGRESSION["state"]="completed"
    REGRESSION["ok"]=all(r["ok"] for r in REGRESSION["groups"].values())
    print("LERIKA_V550_QA_COMPLETE "+str(REGRESSION),flush=True)
threading.Thread(target=run_isolated_regression,daemon=True,name="isolated-qa").start()


@app.after_request
def secure(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.get("/")
def index():
    return redirect("/showroom/")

@app.get("/health")
def health():
    return jsonify(ok=True, environment="three-qa", data="synthetic-only", regression=REGRESSION)

@app.get("/showroom/")
@app.get("/showroom/index.html")
def showroom():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    html = html.replace("https://lerika-cabinet.onrender.com", "")
    html = re.sub(r'(<meta name="lerika-portfolio-api" content=")[^"]*(")', r'\1/\2', html, count=1)
    html = html.replace("</head>", '<meta name="robots" content="noindex,nofollow"><style>.qa-banner{background:#9e3f24;color:white;text-align:center;padding:8px;font:600 13px system-ui}.qa-banner a{color:white}</style></head>', 1)
    html = re.sub(r"<body(?:\s[^>]*)?>", lambda m: m[0]+'<div class="qa-banner">ТЕСТОВАЯ ЛЕРИКА V5.50 QA · Three.js · заказы и кабинет отключены · только демонстрационные данные</div>', html, count=1)
    # Do not let this preview redirect to the live cabinet or another payment/account service.
    def hashes(tag):
        return " ".join("'sha256-"+base64.b64encode(hashlib.sha256(v.encode()).digest()).decode()+"'" for v in re.findall(r"<"+tag+r"\b[^>]*>([\s\S]*?)</"+tag+r">",html,re.I) if v)
    response = app.make_response((html, 200, {"Content-Type":"text/html; charset=utf-8"}))
    response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self' "+hashes("script")+"; style-src 'self' "+hashes("style")+"; img-src 'self' data: blob:; connect-src 'self'; worker-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response

@app.get("/showroom/<name>")
def asset(name):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}\.(?:png|jpg|jpeg|webp|gif|ico|css)",name,re.I) and name!="portfolio-api.js":
        abort(404)
    if name.startswith(".") or ".." in name:
        abort(404)
    path=ROOT/name
    if not path.is_file() or path.stat().st_size>8*1024*1024:
        abort(404)
    return send_file(path, mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream")

@app.get("/public/portfolio")
def portfolio():
    return jsonify(projects=[], covers={})

@app.get("/public/prices")
def prices():
    return jsonify(entries=[], updated=None)

@app.route("/api/<path:rest>", methods=["GET","POST","PUT","PATCH","DELETE"])
@app.route("/cabinet/<path:rest>", methods=["GET","POST","PUT","PATCH","DELETE"])
@app.route("/cabinet/", methods=["GET","POST"])
@app.route("/support/telegram")
def disabled(rest=""):
    return jsonify(error="Тестовая версия: кабинет, заявки и Telegram отключены."), 503
