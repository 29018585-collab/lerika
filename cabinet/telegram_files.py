"""Private Telegram file intake for the administrator-only order pilot."""
import hashlib
import json
import re
import time
import unicodedata
from pathlib import PurePosixPath
from urllib.request import Request, build_opener, HTTPRedirectHandler

MAX_BYTES = 12 * 1024 * 1024
MAX_FILES = 10
STORAGE_CAP = 350 * 1024 * 1024
ALLOWED = frozenset(".jpg .jpeg .png .webp .pdf .zip .rar .7z .doc .docx .xls .xlsx .xlsm .csv .txt .dxf .dwg .sto .skp .heic .heif .tif .tiff".split())

class IntakeError(ValueError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def attachment_from_message(message):
    doc = message.get("document")
    photos = message.get("photo")
    if isinstance(doc, dict):
        item = doc
        name = item.get("file_name")
        if not isinstance(name, str):
            raise IntakeError("У файла нет имени. Отправьте его как документ.")
        name = PurePosixPath(name.replace(chr(92), "/")).name
        name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C"))
        if len(name) > 160 or PurePosixPath(name).suffix.lower() not in ALLOWED:
            raise IntakeError("Этот формат не поддерживается.")
    elif isinstance(photos, list) and photos:
        choices = [p for p in photos if isinstance(p, dict) and type(p.get("file_size")) is int and 0 < p["file_size"] <= MAX_BYTES]
        if not choices:
            raise IntakeError("Фото слишком большое или размер неизвестен.")
        item = max(choices, key=lambda p: p["file_size"])
        name = "photo-" + hashlib.sha256(str(item.get("file_unique_id","")).encode()).hexdigest()[:12] + ".jpg"
    else:
        return None
    size = item.get("file_size")
    fid = item.get("file_id")
    if type(size) is not int or not 0 < size <= MAX_BYTES:
        raise IntakeError("Размер файла должен быть известен и не превышать 12 МБ.")
    if not isinstance(fid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", fid):
        raise IntakeError("Некорректный идентификатор файла.")
    return name, fid, size

def validate_bytes(name, raw):
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in ALLOWED or not raw or len(raw)>MAX_BYTES:
        raise IntakeError("Формат или размер файла не поддерживается.")
    signatures = {".pdf": (b"%PDF-",), ".zip": (b"PK\x03\x04",b"PK\x05\x06"),
                  ".rar": (b"Rar!\x1a\x07",), ".7z": (b"7z\xbc\xaf\x27\x1c",),
                  ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
                  ".png": (b"\x89PNG\r\n\x1a\n",)}
    for ext in (".docx", ".xlsx", ".xlsm"):
        signatures[ext] = signatures[".zip"]
    for ext in (".doc", ".xls"):
        signatures[ext] = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
    if suffix in signatures and not raw.startswith(signatures[suffix]):
        raise IntakeError("Содержимое не соответствует расширению файла.")
    if suffix == ".webp" and not (raw.startswith(b"RIFF") and raw[8:12]==b"WEBP"):
        raise IntakeError("Некорректный WEBP.")
    # All originals remain opaque private downloads; no extraction or execution.

def download_file(token, fid, size, opener=None):
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", token or ""):
        raise IntakeError("Загрузка файлов Telegram не настроена.")
    opener = opener or build_opener(NoRedirect()).open
    try:
        req = Request("https://api.telegram.org/bot"+token+"/getFile",
                      data=json.dumps({"file_id":fid}).encode(),
                      headers={"Content-Type":"application/json"},method="POST")
        with opener(req,timeout=8) as response:
            meta = json.loads(response.read(65537))
        if not isinstance(meta,dict) or meta.get("ok") is not True:
            raise ValueError()
        result = meta["result"]
        path = result["file_path"]
        if not isinstance(path,str) or len(path)>512 or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",path) or any(p in (".","..") for p in path.split("/")):
            raise ValueError()
        if result.get("file_size") != size:
            raise ValueError()
        with opener(Request("https://api.telegram.org/file/bot"+token+"/"+path),timeout=10) as response:
            raw = response.read(size+1)
        if len(raw)!=size:
            raise ValueError()
        return raw
    except Exception:
        # Never log exceptions containing a bot token or a private file path.
        raise IntakeError("Не удалось безопасно загрузить файл. Отправьте его повторно.") from None

def purge_expired(c, now):
    c.execute("DELETE FROM telegram_test_files WHERE chat_key IN (SELECT chat_key FROM telegram_test_drafts WHERE expires<=?)",(now,))
    c.execute("DELETE FROM telegram_test_drafts WHERE expires<=?",(now,))

def clear_files(c, digest):
    c.execute("DELETE FROM telegram_test_files WHERE chat_key=?",(digest,))

def usage(c,digest,code):
    return c.execute("SELECT COUNT(*) AS n, COALESCE(SUM(length(data)),0) AS size FROM telegram_test_files WHERE chat_key=? AND code=?",(digest,code)).fetchone()

def receive_attachment(message,digest,token,db,lock,now=None,downloader=download_file):
    now = int(time.time()) if now is None else now
    try:
        spec = attachment_from_message(message)
        if spec is None:
            return None
        name,fid,size = spec
        with db() as c:
            lock(c,82003)
            purge_expired(c,now)
            row=c.execute("SELECT code FROM telegram_test_drafts WHERE chat_key=?",(digest,)).fetchone()
            if not row:
                return "Сначала создайте тестовый черновик: /order_test описание. Затем отправляйте файлы."
            code=row["code"]
            u=usage(c,digest,code)
            if u["n"]>=MAX_FILES or u["size"]+size>MAX_BYTES:
                return "Лимит черновика: 10 файлов и 12 МБ суммарно."
        raw=downloader(token,fid,size)
        if len(raw)!=size:
            raise IntakeError("Размер загруженного файла не совпадает.")
        validate_bytes(name,raw)
        checksum=hashlib.sha256(raw).hexdigest()
        with db() as c:
            lock(c,82003)
            purge_expired(c,max(now,int(time.time())))
            row=c.execute("SELECT code FROM telegram_test_drafts WHERE chat_key=?",(digest,)).fetchone()
            if not row or row["code"]!=code:
                return "Черновик изменился или истёк. Файл не сохранён."
            if c.execute("SELECT 1 FROM telegram_test_files WHERE chat_key=? AND code=? AND checksum=?",(digest,code,checksum)).fetchone():
                return "Этот файл уже прикреплён к черновику."
            u=usage(c,digest,code)
            if u["n"]>=MAX_FILES or u["size"]+size>MAX_BYTES:
                return "Лимит черновика: 10 файлов и 12 МБ суммарно."
            stored=c.execute("SELECT COALESCE(SUM(length(data)),0) AS size FROM files").fetchone()["size"]
            staged=c.execute("SELECT COALESCE(SUM(length(data)),0) AS size FROM telegram_test_files").fetchone()["size"]
            if stored+staged+size>STORAGE_CAP:
                return "Хранилище заполнено. Файл не сохранён."
            c.execute("INSERT INTO telegram_test_files(chat_key,code,checksum,name,data) VALUES(?,?,?,?,?)",(digest,code,checksum,name,raw))
        return "Файл прикреплён: "+name+"\nВ черновике: "+str(u["n"]+1)+" из 10. Отправьте ещё файл или /confirm "+code+"."
    except IntakeError as exc:
        return str(exc)
