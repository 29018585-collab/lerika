"""Disposable Render ingress probe. No database or production credentials."""
import os, ast, ipaddress, json
from pathlib import Path
from flask import Flask, request, jsonify, abort
app=Flask(__name__)
# Execute exactly the sender_address function from the V5.20 source.
tree=ast.parse(Path(__file__).with_name("app.py").read_text())
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="sender_address")
exec(compile(ast.Module(body=[node],type_ignores=[]),"<v520-sender-address>","exec"))
@app.get("/")
def health():
    return "LERIKA ingress QA — isolated"
@app.get("/probe")
def probe():
    marker=request.args.get("marker","")
    if marker not in ("baseline","spoof","second"):
        abort(404)
    peer=request.remote_addr or ""
    raw=request.headers.get("CF-Connecting-IP","")
    result=sender_address()
    try:
        private=ipaddress.ip_address(peer).is_private or ipaddress.ip_address(peer).is_loopback
    except ValueError:
        private=False
    # Never log or return actual public IP addresses.
    report={"marker":marker,"peer_private":private,"cf_present":bool(raw),
        "cf_spoof_preserved":raw=="192.0.2.123",
        "xff_spoof_preserved":request.headers.get("X-Forwarded-For","").startswith("198.51.100.123"),
        "sender_spoofed":result in ("192.0.2.123","198.51.100.123"),
        "sender_uses_edge":result!=peer and result!="unknown" and bool(raw)}
    print("LERIKA_INGRESS_QA "+json.dumps(report),flush=True)
    return jsonify(report)
