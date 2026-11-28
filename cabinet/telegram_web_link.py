"""Two-channel account linking for the closed Telegram pilot. No ownership transfers."""
import hashlib
import hmac
import re
import secrets
import time

def mac(key,kind,value):
    return hmac.new(key.encode(),(kind+":"+value).encode(),hashlib.sha256).hexdigest()

def issue(c,client,key,now):
    if c.execute("SELECT 1 FROM telegram_web_links WHERE client=?",(client,)).fetchone():
        return None
    c.execute("DELETE FROM telegram_web_pending WHERE expires<=? OR client=?",(now,client))
    token=secrets.token_hex(16)
    c.execute("INSERT INTO telegram_web_pending(client,token_hash,expires,chat_key,proof_hash) VALUES(?,?,?,NULL,NULL)",(client,mac(key,"link",token),now+600))
    return token

def claim(c,digest,key,token,now):
    if not re.fullmatch(r"[a-f0-9]{32}",token or ""):
        return None
    if not c.execute("SELECT 1 FROM telegram_pilot_clients WHERE chat_key=?",(digest,)).fetchone() or c.execute("SELECT 1 FROM telegram_web_links WHERE chat_key=?",(digest,)).fetchone():
        return None
    row=c.execute("SELECT client,chat_key FROM telegram_web_pending WHERE token_hash=? AND expires>?",(mac(key,"link",token),now)).fetchone()
    if not row or row["chat_key"] is not None:
        return None
    proof=secrets.token_hex(8)
    c.execute("UPDATE telegram_web_pending SET chat_key=?,proof_hash=? WHERE client=?",(digest,mac(key,"proof",proof),row["client"]))
    return proof

def confirm(c,client,key,proof,now,allowed_digests):
    if not re.fullmatch(r"[a-f0-9]{16}",proof or ""):
        return False
    row=c.execute("SELECT chat_key,proof_hash FROM telegram_web_pending WHERE client=? AND expires>?",(client,now)).fetchone()
    if not row or not row["chat_key"] or not row["proof_hash"] or row["chat_key"] not in allowed_digests or not hmac.compare_digest(row["proof_hash"],mac(key,"proof",proof)):
        return False
    if not c.execute("SELECT 1 FROM telegram_pilot_clients WHERE chat_key=?",(row["chat_key"],)).fetchone():
        return False
    if c.execute("SELECT 1 FROM telegram_web_links WHERE client=? OR chat_key=?",(client,row["chat_key"])).fetchone():
        return False
    c.execute("INSERT INTO telegram_web_links(client,chat_key,created) VALUES(?,?,?)",(client,row["chat_key"],now))
    c.execute("DELETE FROM telegram_web_pending WHERE client=? OR chat_key=?",(client,row["chat_key"]))
    return True

def unlink(c,client):
    c.execute("DELETE FROM client_file_shares WHERE client=? AND file IN (SELECT f.id FROM files f JOIN telegram_test_owners o ON o.request_id=f.project WHERE NOT EXISTS (SELECT 1 FROM client_requests cr WHERE cr.project=f.project))",(client,))
    c.execute("DELETE FROM telegram_web_pending WHERE client=?",(client,))
    c.execute("DELETE FROM telegram_web_links WHERE client=?",(client,))

def unlink_chat(c,digest):
    row=c.execute("SELECT client FROM telegram_web_links WHERE chat_key=?",(digest,)).fetchone()
    if row: unlink(c,row["client"])
    c.execute("DELETE FROM telegram_web_pending WHERE chat_key=?",(digest,))
    c.execute("DELETE FROM telegram_web_links WHERE chat_key=?",(digest,))

def active_digests(key,enabled,allowlist):
    from telegram_client_pilot import allowed,digest_for
    if enabled!="1" or not isinstance(allowlist,str):
        return set()
    return {digest_for(key,int(v.strip())) for v in allowlist.split(",") if re.fullmatch(r"[1-9][0-9]{0,15}",v.strip()) and allowed(int(v.strip()),enabled,allowlist)}
