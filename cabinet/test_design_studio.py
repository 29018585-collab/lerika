"""Isolated Lab V5.6 acceptance tests; no production DB or credentials."""
import os, tempfile, unittest, io, secrets
from pathlib import Path
from PIL import Image
tmp=tempfile.TemporaryDirectory()
os.environ.pop("RENDER",None)
# The QA PostgreSQL target is intentionally fixed to a disposable local CI service.
# Never accept a production DATABASE_URL in this destructive test suite.
QA_POSTGRES=os.environ.get("LERIKA_QA_POSTGRES")=="1"
os.environ["DATABASE_URL"]="postgresql://lerika_qa:lerika_qa@127.0.0.1:5432/lerika_qa" if QA_POSTGRES else ""
os.environ["DATA_DIR"]=tmp.name
os.environ["SESSION_SECRET"]="local-test-secret-not-for-production-12345"
os.environ["ADMIN_PASSWORD"]="local-test-password-only"
from app import app, db

ORIGIN="https://lerika-cabinet.onrender.com"
HEADERS={"Origin":ORIGIN,"X-Lerika-Studio":"5.6"}
def png():
    buf=io.BytesIO()
    Image.new("RGB",(32,32),"#c9b392").save(buf,"PNG")
    return buf.getvalue()

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()
        with db() as c:
            for table in ("telegram_web_pending","telegram_web_links","telegram_test_subscriptions","telegram_test_files","telegram_test_drafts","telegram_pilot_pending","telegram_pilot_clients","telegram_test_owners","client_requests","clients","client_limits","price_catalog","covers","files","design_briefs","request_numbers","design_requests","projects","attempts"):
                c.execute("DELETE FROM "+table)
    def data(self,rid=None):
        return dict(request_id=rid or secrets.token_hex(16),consent="yes",title="Тест кухни",room="Кухня",contact="test@example.invalid",brief="Пожелания: тест")
    def submit(self,data,headers=HEADERS,ip="198.51.100.1"):
        return self.client.post("/api/design-requests",data=data,headers=headers,base_url=ORIGIN,content_type="multipart/form-data",environ_overrides={"REMOTE_ADDR":ip})
    def test_submit_with_files_collage_and_privacy(self):
        d=self.data()
        d["files"]=[(io.BytesIO(png()),"photo.png"),(io.BytesIO(b"%PDF-1.4\n%%EOF"),"drawing.pdf")]
        d["collage"]=(io.BytesIO(png()),"LERIKA-Materials.png")
        r=self.submit(d)
        self.assertEqual(r.status_code,201)
        rid=r.json["id"]
        self.assertEqual(self.client.get("/public/portfolio").json["projects"],[])
        self.assertEqual(self.client.get("/api/projects",base_url=ORIGIN).status_code,401)
        with db() as c:
            p=c.execute("SELECT * FROM projects WHERE id=?",(rid,)).fetchone()
            rows=list(c.execute("SELECT * FROM files WHERE project=?",(rid,)))
            self.assertEqual((p["category"],p["published"],p["status"]),(1,0,"work"))
            self.assertEqual(len(rows),3)
            self.assertTrue(all(f["public"]==0 for f in rows))
            self.assertEqual({f["mime"] for f in rows},{"image/jpeg","image/png","application/octet-stream"})
            for f in rows:
                self.assertEqual(self.client.get("/public/photos/"+f["id"]).status_code,404)
                self.assertEqual(self.client.get("/api/files/"+f["id"],base_url=ORIGIN).status_code,401)
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        self.assertEqual(login.status_code,200)
        projects=self.client.get("/api/projects",base_url=ORIGIN).json["projects"]
        self.assertEqual(projects[0]["id"],rid)
        self.assertEqual(len(projects[0]["files"]),3)
        self.assertIn("test@example.invalid",projects[0]["private_brief"])
        self.assertNotIn("test@example.invalid",projects[0]["description"])
        self.assertNotIn("Тест кухни",projects[0]["title"])
        for f in projects[0]["files"]:
            self.assertEqual(self.client.get("/api/files/"+f["id"],base_url=ORIGIN).status_code,200)
    def test_private_brief_never_in_public_portfolio(self):
        rid=self.submit(self.data()).json["id"]
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        csrf=login.json["csrf"]
        p=self.client.get("/api/projects",base_url=ORIGIN).json["projects"][0]
        self.assertIn("test@example.invalid",p["private_brief"])
        self.assertEqual(self.client.put("/api/projects/"+rid,base_url=ORIGIN,headers={"X-CSRF":csrf},json={**p,"published":True}).status_code,403)
        self.assertEqual(self.client.get("/public/portfolio").json["projects"],[])
    def test_universal_order_originals_and_privacy(self):
        import zipfile
        z=io.BytesIO()
        with zipfile.ZipFile(z,"w") as archive: archive.writestr("design.txt","original")
        archive=z.getvalue()
        photo=png()
        d=self.data()
        d["files"]=[(io.BytesIO(archive),"project.zip"),(io.BytesIO(photo),"photo.png"),(io.BytesIO(b"%PDF-1.4\n%%EOF"),"drawing.pdf"),(io.BytesIO(b"part;size"),"parts.csv")]
        headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"}
        r=self.client.post("/api/order-requests",data=d,headers=headers,base_url=ORIGIN,content_type="multipart/form-data")
        self.assertEqual(r.status_code,201)
        rid=r.json["id"]
        with db() as c:
            files={f["name"]:f for f in c.execute("SELECT * FROM files WHERE project=?",(rid,))}
            self.assertEqual(len(files),4)
            self.assertEqual(bytes(files["project.zip"]["data"]),archive)
            self.assertEqual(bytes(files["photo.png"]["data"]),photo)
            self.assertTrue(all(f["image"]==0 and f["public"]==0 for f in files.values()))
            self.assertTrue(c.execute("SELECT title FROM projects WHERE id=?",(rid,)).fetchone()["title"].startswith("Заказ"))
        self.assertEqual(self.client.get("/public/portfolio").json["projects"],[])
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        csrf=login.json["csrf"]
        for f in files.values():
            download=self.client.get("/api/files/"+f["id"],base_url=ORIGIN)
            self.assertEqual(download.status_code,200)
            self.assertIn("attachment",download.headers["Content-Disposition"])
            self.assertEqual(self.client.put("/api/files/"+f["id"],json={"public":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,400)
    def test_v560_apartment_bundle_private_designer_download(self):
        import json
        headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"}
        client_headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        owner={"name":"Apartment QA","email":"apartment@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=owner,headers=client_headers,base_url=ORIGIN).status_code,201)
        snapshot={"version":1,"source":"apartment","room":{"version":2,"activeRoom":1,"rooms":[{"id":1,"name":"Коридор"},{"id":2,"name":"Кухня"}]},"items":[{"id":1,"estimateRoomId":2,"type":"wardrobe"}]}
        originals={
            "LERIKA-Project.txt":json.dumps(snapshot,ensure_ascii=False).encode(),
            "LERIKA-Estimate.csv":'Изделие;Группа;Стоимость\nКухня;корпус;1000'.encode("utf-8-sig"),
            "LERIKA-Apartment-Plan.png":png(),
            "LERIKA-Apartment-3D.png":png(),
        }
        def order():
            return dict(self.data(request_id),source="plan",files=[(io.BytesIO(data),name) for name,data in originals.items()])
        request_id=secrets.token_hex(16)
        response=self.client.post("/api/order-requests",data=order(),headers=headers,base_url=ORIGIN,content_type="multipart/form-data")
        self.assertEqual(response.status_code,201)
        rid=response.json["id"]
        retry=self.client.post("/api/order-requests",data=order(),headers=headers,base_url=ORIGIN,content_type="multipart/form-data")
        self.assertEqual(retry.status_code,200)
        self.assertEqual(retry.json["id"],rid)
        self.assertEqual([x["id"] for x in self.client.get("/api/client/session",base_url=ORIGIN).json["orders"]],[rid])
        other=app.test_client()
        self.assertEqual(other.post("/api/client/register",json={**owner,"email":"other@example.invalid"},headers=client_headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get("/api/client/session",base_url=ORIGIN).json["orders"],[])
        self.assertEqual(other.get("/api/projects",base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client.get("/public/portfolio").json["projects"],[])
        admin=app.test_client()
        self.assertEqual(admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN).status_code,200)
        projects=admin.get("/api/projects",base_url=ORIGIN).json["projects"]
        self.assertEqual(len(projects),1)
        project=projects[0]
        self.assertEqual(project["id"],rid)
        self.assertEqual({f["name"] for f in project["files"]},set(originals))
        for f in project["files"]:
            self.assertEqual(other.get("/api/files/"+f["id"],base_url=ORIGIN).status_code,401)
            self.assertEqual(other.get("/public/photos/"+f["id"],base_url=ORIGIN).status_code,404)
            downloaded=admin.get("/api/files/"+f["id"],base_url=ORIGIN)
            self.assertEqual(downloaded.status_code,200)
            self.assertEqual(downloaded.data,originals[f["name"]])
            self.assertIn("attachment",downloaded.headers["Content-Disposition"])

    def test_v566_private_order_conversation(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        owner={"name":"Message QA","email":"thread@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=owner,headers=headers,base_url=ORIGIN).status_code,201)
        rid=self.submit(self.data()).json["id"]
        url="/api/client/orders/"+rid+"/messages"
        admin_url="/api/projects/"+rid+"/messages"
        other=app.test_client()
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,401)
        self.assertEqual(other.post("/api/client/register",json={**owner,"email":"other-thread@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,404)
        self.assertEqual(other.post(url,json={"text":"forbidden"},headers=headers,base_url=ORIGIN).status_code,404)
        self.assertEqual(self.client.get(admin_url,base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client.post(url,json={"text":"test"},base_url=ORIGIN).status_code,403)
        self.assertEqual(self.client.post(url,json={"text":" "},headers=headers,base_url=ORIGIN).status_code,400)
        self.assertEqual(self.client.post(url,json={"text":"x"*2001},headers=headers,base_url=ORIGIN).status_code,400)
        text="<script>QA</script> Уточните фасады."
        r=self.client.post(url,json={"text":text,"author":"designer"},headers=headers,base_url=ORIGIN)
        self.assertEqual(r.status_code,201)
        self.assertEqual(r.json["messages"][0]["author"],"client")
        admin=app.test_client()
        h={"X-CSRF":admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN).json["csrf"]}
        self.assertEqual(admin.get(admin_url,base_url=ORIGIN).json["messages"][0]["body"],text)
        self.assertEqual(admin.post(admin_url,json={"text":"Ответ"},base_url=ORIGIN).status_code,403)
        self.assertEqual(admin.post(admin_url,json={"text":"Ответ"},headers=h,base_url=ORIGIN).status_code,201)
        messages=self.client.get(url,base_url=ORIGIN).json["messages"]
        self.assertEqual({m["author"]:m["body"] for m in messages},{"client":text,"designer":"Ответ"})
        self.assertNotIn(text,self.client.get("/public/portfolio").get_data(as_text=True))
        self.assertEqual(admin.delete("/api/projects/"+rid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM client_order_messages").fetchone()["n"],0)
        self.assertEqual(self.client.get(url,base_url=ORIGIN).status_code,404)

    def test_v570_order_history_and_private_stage_photos(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        owner={"name":"History QA","email":"history@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=owner,headers=headers,base_url=ORIGIN).status_code,201)
        rid=self.submit(self.data()).json["id"]
        url="/api/client/orders/"+rid+"/history"
        admin_url="/api/projects/"+rid+"/history"
        admin=app.test_client()
        h={"X-CSRF":admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN).json["csrf"]}
        old=self.client.get(url,base_url=ORIGIN).json
        self.assertGreater(old["created"],0)
        self.assertEqual(old["changes"],[])
        self.assertEqual(old["stage"],1)
        project=next(p for p in admin.get("/api/projects",base_url=ORIGIN).json["projects"] if p["id"]==rid)
        def stage(n,status="work"):
            return admin.put("/api/projects/"+rid,json={**project,"stage":n,"status":status,"published":False},headers=h,base_url=ORIGIN)
        for n,status in [(2,"work"),(2,"work"),(4,"work"),(3,"work"),(6,"ready")]:
            self.assertEqual(stage(n,status).status_code,200)
        d=self.client.get(url,base_url=ORIGIN).json
        self.assertEqual([(x["from_stage"],x["stage"]) for x in d["changes"]],[(1,2),(2,4),(4,3),(3,6)])
        self.assertEqual([x["seq"] for x in d["changes"]],[1,2,3,4])
        self.assertTrue(all(x["created"]>=old["created"] for x in d["changes"]))
        self.assertEqual(d["status"],"ready")
        self.assertEqual(d["changes"],admin.get(admin_url,base_url=ORIGIN).json["changes"])
        picture=io.BytesIO()
        from PIL import Image
        Image.new("RGB",(32,24),(120,80,40)).save(picture,"PNG")
        picture.seek(0)
        photo=admin.post("/api/projects/"+rid+"/files",data={"stage":"4","file":(picture,"process.png")},headers=h,base_url=ORIGIN,content_type="multipart/form-data")
        self.assertEqual(photo.status_code,201)
        fid=photo.json["id"]
        preview="/api/client/files/"+fid+"?preview=1"
        share="/api/files/"+fid+"/client-share"
        self.assertEqual(self.client.get(url,base_url=ORIGIN).json["photos"],[])
        self.assertEqual(admin.get(admin_url,base_url=ORIGIN).json["photos"][0]["id"],fid)
        self.assertEqual(self.client.get(preview,base_url=ORIGIN).status_code,404)
        self.assertEqual(admin.put(share,json={"shared":True},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get(url,base_url=ORIGIN).json["photos"],[{"id":fid,"name":"process.png","stage":4}])
        r=self.client.get(preview,base_url=ORIGIN)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.mimetype,"image/jpeg")
        self.assertIn("no-store",r.headers["Cache-Control"])
        self.assertEqual(Image.open(io.BytesIO(r.data)).size,(32,24))
        other=app.test_client()
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,401)
        self.assertEqual(other.post("/api/client/register",json={**owner,"email":"other-history@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,404)
        self.assertEqual(other.get(preview,base_url=ORIGIN).status_code,404)
        self.assertEqual(other.get(admin_url,base_url=ORIGIN).status_code,401)
        self.assertEqual(admin.put(share,json={"shared":False},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get(preview,base_url=ORIGIN).status_code,404)
        self.assertEqual(self.client.get(url,base_url=ORIGIN).json["photos"],[])
        self.assertEqual(admin.delete("/api/projects/"+rid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM order_stage_history").fetchone()["n"],0)
        self.assertEqual(self.client.get(url,base_url=ORIGIN).status_code,404)

    def test_v568_revision_bound_client_approval(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        owner={"name":"Approval QA","email":"approval@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=owner,headers=headers,base_url=ORIGIN).status_code,201)
        rid=self.submit(self.data()).json["id"]
        url="/api/client/orders/"+rid+"/approval"
        admin_url="/api/projects/"+rid+"/approval"
        admin=app.test_client()
        h={"X-CSRF":admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN).json["csrf"]}
        def issue(ids):
            return admin.post(admin_url,json={"note":"Проверьте проект","file_ids":sorted(ids)},headers=h,base_url=ORIGIN)
        def upload(name):
            r=admin.post("/api/projects/"+rid+"/files",data={"stage":"3","file":(io.BytesIO(b"%PDF-1.4\nQA\n%%EOF"),name)},headers=h,base_url=ORIGIN,content_type="multipart/form-data")
            self.assertEqual(r.status_code,201)
            return r.json["id"]
        def share(fid,yes=True):
            self.assertEqual(admin.put("/api/files/"+fid+"/client-share",json={"shared":yes},headers=h,base_url=ORIGIN).status_code,200)
        def decide(rev,decision,comment=""):
            return self.client.post(url,json={"revision":rev,"decision":decision,"comment":comment},headers=headers,base_url=ORIGIN)
        self.assertEqual(issue([]).status_code,409)
        f1=upload("version1.pdf");share(f1)
        self.assertEqual(issue([]).status_code,409)
        r=issue([f1]);self.assertEqual(r.status_code,201)
        self.assertEqual(r.json["approvals"][0]["revision"],1)
        self.assertEqual(r.json["approvals"][0]["files"],[{"id":f1,"name":"version1.pdf"}])
        other=app.test_client()
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,401)
        self.assertEqual(other.post("/api/client/register",json={**owner,"email":"other-approval@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,404)
        self.assertEqual(other.post(url,json={"revision":1,"decision":"approved"},headers=headers,base_url=ORIGIN).status_code,404)
        self.assertEqual(self.client.post(url,json={"revision":1,"decision":"approved"},base_url=ORIGIN).status_code,403)
        self.assertEqual(decide(1,"changes").status_code,400)
        self.assertEqual(decide(1,"changes","Изменить фасад").status_code,201)
        self.assertEqual(decide(1,"approved").status_code,409)
        f2=upload("version2.pdf");share(f1,False);share(f2)
        self.assertEqual(issue([f2]).status_code,201)
        f3=upload("extra.pdf");share(f3)
        self.assertEqual(decide(2,"approved").status_code,409)
        self.assertEqual(issue([f2,f3]).status_code,201)
        self.assertEqual(decide(2,"approved").status_code,409)
        self.assertEqual(decide(3,"approved").status_code,201)
        rows=admin.get(admin_url,base_url=ORIGIN).json["approvals"]
        self.assertEqual([r["state"] for r in rows],["approved","superseded","changes"])
        self.assertEqual(rows[2]["comment"],"Изменить фасад")
        self.assertIsNotNone(rows[0]["decided"])
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).json["orders"][0]["stage"],1)
        self.assertEqual(admin.delete("/api/projects/"+rid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM client_project_approvals").fetchone()["n"],0)

    def test_v564_client_document_explicit_share_and_revoke(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        owner={"name":"Client QA","email":"share@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=owner,headers=headers,base_url=ORIGIN).status_code,201)
        original=b"%PDF-1.4\nQA shared document\n%%EOF"
        d=self.data();d["files"]=[(io.BytesIO(original),"plan.pdf")]
        r=self.client.post("/api/order-requests",data=d,headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"},base_url=ORIGIN,content_type="multipart/form-data")
        self.assertEqual(r.status_code,201)
        rid=r.json["id"]
        admin=app.test_client()
        h={"X-CSRF":admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN).json["csrf"]}
        project=next(p for p in admin.get("/api/projects",base_url=ORIGIN).json["projects"] if p["id"]==rid)
        self.assertTrue(project["client_share_available"])
        fid=project["files"][0]["id"]
        url="/api/client/files/"+fid
        def orders():
            return self.client.get("/api/client/session",base_url=ORIGIN).json["orders"]
        self.assertEqual(orders()[0]["files"],[])
        self.assertEqual(self.client.get(url,base_url=ORIGIN).status_code,404)
        self.assertEqual(admin.put("/api/files/"+fid+"/client-share",json={"shared":True},base_url=ORIGIN).status_code,403)
        self.assertEqual(admin.put("/api/files/"+fid+"/client-share",json={"shared":True},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(orders()[0]["files"][0]["id"],fid)
        download=self.client.get(url,base_url=ORIGIN)
        self.assertEqual(download.status_code,200)
        self.assertEqual(download.data,original)
        self.assertIn("no-store",download.headers["Cache-Control"])
        other=app.test_client()
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,401)
        self.assertEqual(other.post("/api/client/register",json={**owner,"email":"other-share@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get(url,base_url=ORIGIN).status_code,404)
        self.assertEqual(other.get("/api/client/session",base_url=ORIGIN).json["orders"],[])
        self.assertEqual(other.get("/public/photos/"+fid).status_code,404)
        self.assertEqual(admin.put("/api/files/"+fid+"/client-share",json={"shared":False},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(orders()[0]["files"],[])
        self.assertEqual(self.client.get(url,base_url=ORIGIN).status_code,404)

    def test_universal_order_rejects_bad_archive_and_executable(self):
        for name in ("bad.zip","program.exe"):
            d=self.data();d["files"]=(io.BytesIO(b"not an archive"),name)
            self.assertEqual(self.client.post("/api/order-requests",data=d,headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"},base_url=ORIGIN,content_type="multipart/form-data").status_code,415)
        with db() as c:self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"],0)
    def test_universal_text_only_order(self):
        d=self.data()
        headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"}
        for expected in (201,200):
            self.assertEqual(self.client.post("/api/order-requests",data=d,headers=headers,base_url=ORIGIN,content_type="multipart/form-data").status_code,expected)
    def test_request_sources_private_and_validated(self):
        expected=["3d","config","plan","engineering","order","support","partner","project"]
        for source in expected:
            d=self.data();d["source"]=source
            r=self.client.post("/api/order-requests",data=d,headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"},base_url=ORIGIN,content_type="multipart/form-data")
            self.assertEqual(r.status_code,201)
        d=self.data();d["source"]="ai"
        self.assertEqual(self.submit(d).status_code,201)
        d=self.data();d["source"]="invalid"
        self.assertEqual(self.submit(d).status_code,400)
        self.assertEqual(self.client.get("/public/portfolio").json["projects"],[])
        self.assertEqual(self.client.get("/api/projects",base_url=ORIGIN).status_code,401)
        self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        rows=self.client.get("/api/projects",base_url=ORIGIN).json["projects"]
        self.assertEqual({p["request_source"] for p in rows},set(expected+["ai"]))
        self.assertTrue(all(p["request_created"] and p["published"]==0 for p in rows))
    def test_support_telegram_route(self):
        from unittest.mock import patch
        with patch.dict(os.environ,{"LERIKA_SUPPORT_BOT_USERNAME":"@LerikaTestSupportBot"}):
            r=self.client.get("/support/telegram",base_url=ORIGIN)
            self.assertEqual(r.status_code,302)
            self.assertEqual(r.headers["Location"],"https://t.me/LerikaTestSupportBot")
        with patch.dict(os.environ,{"LERIKA_SUPPORT_BOT_USERNAME":"https://untrusted.invalid"}):
            r=self.client.get("/support/telegram",base_url=ORIGIN)
            self.assertEqual(r.status_code,503)
            self.assertNotIn("Location",r.headers)
    def test_clients_own_requests_and_admin_separation(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(self.client.get("/api/projects",base_url=ORIGIN).status_code,401)
        rid=self.submit(self.data()).json["id"]
        self.assertEqual([x["id"] for x in self.client.get("/api/client/session",base_url=ORIGIN).json["orders"]],[rid])
        other=app.test_client()
        self.assertEqual(other.post("/api/client/register",json={**d,"email":"b@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
        self.assertEqual(other.get("/api/client/session",base_url=ORIGIN).json["orders"],[])
        self.client.post("/api/client/logout",json={},headers=headers,base_url=ORIGIN)
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client.post("/api/client/login",json=d,headers=headers,base_url=ORIGIN).status_code,200)
        with db() as c:
            self.assertNotEqual(c.execute("SELECT password_hash FROM clients WHERE email=?",("a@example.invalid",)).fetchone()["password_hash"],d["password"])
    def test_telegram_web_link_http_owner_scope(self):
        import time
        from unittest.mock import patch
        from app import KEY
        from telegram_core import secret_for
        from telegram_client_pilot import JOIN,CONSENT
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        env={"LERIKA_TG_CLIENT_PILOT":"1","LERIKA_TG_PILOT_CHAT_IDS":"123456,123457","LERIKA_TELEGRAM_ADMIN_CHAT_ID":"999999","LERIKA_TELEGRAM_BOT_TOKEN":""}
        serial=123000
        def web(action,client=None,**data):
            return (client or self.client).post("/api/client/telegram-link",json={"action":action,**data},headers=headers,base_url=ORIGIN)
        def tg(text,cid=123456):
            nonlocal serial
            serial+=1
            r=app.test_client().post("/api/telegram/webhook",base_url=ORIGIN,headers={"X-Telegram-Bot-Api-Secret-Token":secret_for(KEY)},json={"update_id":serial,"message":{"date":int(time.time()),"chat":{"type":"private","id":cid},"from":{"id":cid,"is_bot":False},"text":text}})
            self.assertEqual(r.status_code,200)
            return r.json
        def session(client=None):
            return (client or self.client).get("/api/client/session",base_url=ORIGIN).json
        with patch.dict(os.environ,env),patch("app.notify_telegram_order",return_value=True):
            self.assertEqual(web("issue").status_code,401)
            d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
            self.assertEqual(self.client.post("/api/client/register",json=d,headers=headers,base_url=ORIGIN).status_code,201)
            other=app.test_client()
            self.assertEqual(other.post("/api/client/register",json={**d,"email":"b@example.invalid"},headers=headers,base_url=ORIGIN).status_code,201)
            website_result=self.submit(self.data()).json
            website_order=website_result["number"]
            tg(JOIN);tg(CONSENT)
            tg("/order_test synthetic cabinet")
            with db() as c:
                draft=c.execute("SELECT code FROM telegram_test_drafts").fetchone()["code"]
            telegram_reply=tg("/confirm "+draft)["text"]
            with db() as c:
                row=c.execute("SELECT n.number FROM request_numbers n JOIN telegram_test_owners o ON o.request_id=n.request_id").fetchone()
                telegram_number="L-"+str(row["number"]).zfill(6)
            self.assertIn(telegram_number,telegram_reply)
            self.assertNotIn(website_order,tg("📦 Мои заявки")["text"])
            self.assertEqual({o["number"] for o in session()["orders"]},{website_order})
            code=web("issue").json["code"]
            self.assertNotIn("Второй код",tg("/link "+code,cid=123458)["text"])
            proof=tg("/link "+code)["text"].rsplit(" ",1)[-1]
            self.assertFalse(web("confirm",client=other,proof=proof).json["ok"])
            self.assertTrue(web("confirm",proof=proof).json["ok"])
            self.assertTrue(session()["telegram_linked"])
            self.assertEqual({o["number"] for o in session()["orders"]},{website_order,telegram_number})
            self.assertEqual(session(other)["orders"],[])
            self.assertIn(website_order,tg("📦 Мои заявки")["text"])
            admin=app.test_client()
            login=admin.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
            csrf=login.json["csrf"]
            project=next(p for p in admin.get("/api/projects",base_url=ORIGIN).json["projects"] if p["id"]==website_result["id"])
            tg_project=next(p for p in admin.get("/api/projects",base_url=ORIGIN).json["projects"] if p["request_number"]==telegram_number)
            self.assertTrue(tg_project["client_share_available"])
            document=b"%PDF-1.4\nTelegram QA\n%%EOF"
            up=admin.post("/api/projects/"+tg_project["id"]+"/files",base_url=ORIGIN,headers={"X-CSRF":csrf},data={"stage":"3","file":(io.BytesIO(document),"telegram-plan.pdf")},content_type="multipart/form-data")
            self.assertEqual(up.status_code,201)
            fid=up.json["id"]
            download_url="/api/client/files/"+fid
            share_url="/api/files/"+fid+"/client-share"
            self.assertEqual(self.client.get(download_url,base_url=ORIGIN).status_code,404)
            self.assertEqual(admin.put(share_url,json={"shared":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,200)
            self.assertEqual(self.client.get(download_url,base_url=ORIGIN).data,document)
            self.assertEqual(other.get(download_url,base_url=ORIGIN).status_code,404)
            self.assertEqual(next(o for o in session()["orders"] if o["number"]==telegram_number)["files"][0]["id"],fid)
            with patch.dict(os.environ,{"LERIKA_TG_CLIENT_PILOT":"0"}):
                self.assertEqual(self.client.get(download_url,base_url=ORIGIN).status_code,404)
            def stage(value):
                return admin.put("/api/projects/"+project["id"],base_url=ORIGIN,headers={"X-CSRF":csrf},json={**project,"stage":value,"published":bool(project["published"])})
            with patch("telegram_core.bot_call",return_value={"message_id":1}) as sender:
                self.assertEqual(stage(2).status_code,200)
                sender.assert_not_called()
                tg("/notify_on")
                self.assertEqual(stage(3).status_code,200)
                self.assertEqual(sender.call_count,1)
                payload=sender.call_args.args[2]
                self.assertEqual(payload["chat_id"],123456)
                self.assertIn(website_order,payload["text"])
                self.assertIn("3D-проект",payload["text"])
                self.assertNotIn("Тестовая",payload["text"])
                self.assertEqual(stage(3).status_code,200)
                self.assertEqual(sender.call_count,1)
                self.assertTrue(web("unlink").json["ok"])
                self.assertEqual(self.client.get(download_url,base_url=ORIGIN).status_code,404)
                self.assertEqual(admin.put(share_url,json={"shared":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,409)
                with db() as c:
                    self.assertIsNone(c.execute("SELECT file FROM client_file_shares WHERE file=?",(fid,)).fetchone())
                self.assertEqual(stage(4).status_code,200)
                self.assertEqual(sender.call_count,1)
            # V5.67: alerts use only order number and event label, never message or file content.
            code=web("issue").json["code"]
            proof=tg("/link "+code)["text"].rsplit(" ",1)[-1]
            self.assertTrue(web("confirm",proof=proof).json["ok"])
            admin_messages="/api/projects/"+tg_project["id"]+"/messages"
            client_messages="/api/client/orders/"+tg_project["id"]+"/messages"
            tg("/notify_off")
            with patch("telegram_core.bot_call",return_value={"message_id":1}) as sender:
                self.assertEqual(admin.post(admin_messages,json={"text":"private disabled alert"},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,201)
                sender.assert_not_called()
            tg("/notify_on")
            with patch("telegram_core.bot_call",return_value={"message_id":1}) as sender:
                self.assertEqual(admin.post(admin_messages,json={"text":"private designer contents"},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,201)
                self.assertEqual(sender.call_count,1)
                payload=sender.call_args.args[2]
                self.assertEqual(payload["chat_id"],123456)
                self.assertIn(telegram_number,payload["text"])
                self.assertIn("Новое сообщение от дизайнера",payload["text"])
                self.assertNotIn("private designer contents",payload["text"])
                self.assertEqual(admin.put(share_url,json={"shared":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,200)
                self.assertEqual(sender.call_count,2)
                payload=sender.call_args.args[2]
                self.assertEqual(payload["chat_id"],123456)
                self.assertIn("Новый документ",payload["text"])
                self.assertNotIn("telegram-plan.pdf",payload["text"])
                self.assertEqual(admin.put(share_url,json={"shared":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,200)
                self.assertEqual(sender.call_count,2)
                self.assertEqual(other.post(client_messages,json={"text":"forbidden"},headers=headers,base_url=ORIGIN).status_code,404)
                self.assertEqual(sender.call_count,2)
                self.assertEqual(self.client.post(client_messages,json={"text":"private client contents"},headers=headers,base_url=ORIGIN).status_code,201)
                self.assertEqual(sender.call_count,3)
                payload=sender.call_args.args[2]
                self.assertEqual(payload["chat_id"],999999)
                self.assertIn("Новое сообщение от клиента",payload["text"])
                self.assertNotIn("private client contents",payload["text"])
            with patch("telegram_core.bot_call",return_value=None):
                self.assertEqual(admin.post(admin_messages,json={"text":"saved despite outage"},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,201)
                self.assertIn("saved despite outage",[m["body"] for m in self.client.get(client_messages,base_url=ORIGIN).json["messages"]])
            self.assertTrue(web("unlink").json["ok"])
            self.assertFalse(session()["telegram_linked"])
            self.assertEqual({o["number"] for o in session()["orders"]},{website_order})
            self.assertNotIn(website_order,tg("📦 Мои заявки")["text"])
            self.assertIn(telegram_number,tg("📦 Мои заявки")["text"])
    def test_price_upload_validation_and_privacy(self):
        raw="Группа;Материал;Цена\nкорпус;ЛДСП;1200\nфасады;МДФ эмаль;2500\n".encode("utf-8")
        def upload(headers):
            return self.client.post("/api/prices",data={"file":(io.BytesIO(raw),"price.csv")},headers=headers,base_url=ORIGIN)
        self.assertEqual(upload({}).status_code,401)
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        headers={"X-CSRF":login.json["csrf"]}
        self.assertEqual(upload(headers).status_code,200)
        result=self.client.get("/public/prices",base_url=ORIGIN).json
        self.assertEqual([x["price"] for x in result["entries"]],[1200,2500])
        bad=self.client.post("/api/prices",data={"file":(io.BytesIO("Группа;Материал;Цена\nкорпус;ЛДСП;-1".encode()),"bad.csv")},headers=headers,base_url=ORIGIN)
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.client.get("/public/prices",base_url=ORIGIN).json,result)
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active;ws.title="Прайс";ws.append(["Группа","Материал","Цена"]);ws.append(["корпус","ЛДСП",1500])
        stream=io.BytesIO();wb.save(stream);stream.seek(0)
        self.assertEqual(self.client.post("/api/prices",data={"file":(stream,"price.xlsx")},headers=headers,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get("/public/prices",base_url=ORIGIN).json["entries"][0]["price"],1500)
    def test_v521_price_import_excel_and_csv_variants(self):
        from openpyxl import Workbook
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        headers={"X-CSRF":login.json["csrf"]}
        def upload(raw,name):
            return self.client.post("/api/prices",data={"file":(io.BytesIO(raw),name)},headers=headers,base_url=ORIGIN)
        raw="Комментарий;Материал;Цена;Группа\nзаметка;ЛДСП;1\u00a0234,567;корпус\n;МДФ;;корпус\n;МДФ эмаль;2500;фасады".encode("cp1251")
        res=upload(raw,"price.csv")
        self.assertEqual(res.status_code,200,res.get_data(as_text=True))
        self.assertEqual([x["price"] for x in res.json["entries"]],[1234.57,2500])
        raw="Группа,Материал,Цена,Комментарий\nкорпус,ЛДСП,1500,тест".encode("cp1251")
        self.assertEqual(upload(raw,"price.csv").status_code,200)
        wb=Workbook();ws=wb.active;ws.title="Прайс"
        ws.append(["Группа","Материал","Цена","Комментарий"])
        ws.append(["корпус","ЛДСП",1500.125,"тест"])
        ws.append(["корпус","МДФ",None,"пока нет цены"])
        ws.append(["фасады","МДФ эмаль","=1000*1.2","формула"])
        stream=io.BytesIO();wb.save(stream)
        # openpyxl writes formula cells without caches. Reject that explicitly.
        rejected=upload(stream.getvalue(),"price.xlsx")
        self.assertEqual(rejected.status_code,400)
        self.assertEqual(rejected.json["row"],4)
        self.assertIn("сохранённого результата",rejected.json["error"])
        # Simulate the cached value stored by Excel, not formula evaluation.
        import zipfile
        cached=io.BytesIO()
        with zipfile.ZipFile(stream) as src,zipfile.ZipFile(cached,"w",zipfile.ZIP_DEFLATED) as dst:
            for name in src.namelist():
                data=src.read(name)
                if name=="xl/worksheets/sheet1.xml":
                    import xml.etree.ElementTree as ET
                    root=ET.fromstring(data)
                    ns={"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    cell=root.find(".//s:c[@r='C4']",ns)
                    self.assertEqual(cell.find("s:f",ns).text,"1000*1.2")
                    cell.find("s:v",ns).text="1200"
                    data=ET.tostring(root,encoding="utf-8")
                dst.writestr(name,data)
        result=upload(cached.getvalue(),"price.xlsx")
        self.assertEqual(result.status_code,200,result.get_data(as_text=True))
        self.assertEqual([x["price"] for x in result.json["entries"]],[1500.13,1200])
        previous=self.client.get("/public/prices",base_url=ORIGIN).json
        bad=upload("Группа;Материал;Цена\nкорпус;ЛДСП;100\nфасады;неизвестно;200".encode(),"price.csv")
        self.assertEqual(bad.status_code,400)
        self.assertEqual(bad.json["row"],3)
        self.assertEqual(self.client.get("/public/prices",base_url=ORIGIN).json,previous)

    def test_cabinet_guides_available(self):
        admin=self.client.get("/cabinet/",base_url=ORIGIN)
        self.assertEqual(admin.status_code,200)
        self.assertIn(b'id="viewGuide"',admin.data)
        self.assertIn(b'id="guidePane"',admin.data)
        self.assertEqual(admin.data.count(b'class="guide-lesson"'),7)
        showroom=self.client.get("/showroom/",base_url=ORIGIN)
        self.assertIn(b'class="client-guide"',showroom.data)
    def test_duplicate(self):
        d=self.data()
        self.assertEqual(self.submit(d.copy()).status_code,201)
        self.assertEqual(self.submit(d.copy()).status_code,200)
        with db() as c:self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"],1)
    def test_reject_origin_and_no_consent(self):
        self.assertEqual(self.submit(self.data(),{"Origin":"https://other.invalid","X-Lerika-Studio":"5.6"}).status_code,403)
        d=self.data();d["consent"]="no"
        self.assertEqual(self.submit(d).status_code,400)
    def test_invalid_images_rollback(self):
        d=self.data();d["files"]=[(io.BytesIO(png()),"valid.png"),(io.BytesIO(b"bad"),"fake.png")]
        self.assertEqual(self.submit(d).status_code,415)
        with db() as c:self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"],0)
    def test_bad_pdf_and_file_limit(self):
        d=self.data();d["files"]=(io.BytesIO(b"bad"),"bad.pdf")
        self.assertEqual(self.submit(d).status_code,415)
        d=self.data();d["files"]=[(io.BytesIO(png()),str(i)+".png") for i in range(7)]
        self.assertEqual(self.submit(d).status_code,400)
    def test_rate_limit(self):
        for i in range(12):self.assertEqual(self.submit(self.data()).status_code,201)
        self.assertEqual(self.submit(self.data()).status_code,429)
        self.assertEqual(self.submit(self.data(),ip="198.51.100.2").status_code,201)
    def test_v520_shared_intake_hour_and_day_quotas_per_sender(self):
        from app import limit_key
        from unittest.mock import patch
        ip="198.51.100.1"
        h={"Origin":ORIGIN,"X-Lerika-Studio":"5.8"}
        def order(sender):
            return self.client.post("/api/order-requests",data=self.data(),headers=h,base_url=ORIGIN,content_type="multipart/form-data",environ_overrides={"REMOTE_ADDR":sender})
        for i in range(6):
            self.assertEqual(self.submit(self.data(),ip=ip).status_code,201)
            self.assertEqual(order(ip).status_code,201)
        self.assertEqual(order(ip).status_code,429)
        self.assertEqual(self.submit(self.data(),ip="198.51.100.2").status_code,201)
        with app.test_request_context("/",environ_overrides={"REMOTE_ADDR":ip}):
            hour=limit_key("intake-hour")
            day=limit_key("intake-day")
        # Simulate the remaining daily quota after an hourly window has elapsed.
        with db() as c:
            c.execute("DELETE FROM client_limits WHERE action=?",(hour,))
            c.execute("UPDATE client_limits SET count=40 WHERE action=?",(day,))
        self.assertEqual(self.submit(self.data(),ip=ip).status_code,429)
        self.assertEqual(order("198.51.100.2").status_code,201)

    def test_v520_delete_project_isolated_and_confirmed(self):
        first=self.data();first["files"]=[(io.BytesIO(png()),"one.png")]
        rid=self.submit(first).json["id"]
        other=self.submit(self.data()).json["id"]
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        h={"X-CSRF":login.json["csrf"]}
        self.assertEqual(self.client.delete("/api/projects/"+rid,json={"confirm":True},base_url=ORIGIN).status_code,403)
        self.assertEqual(self.client.delete("/api/projects/"+rid,json={"confirm":False},headers=h,base_url=ORIGIN).status_code,400)
        self.assertEqual(self.client.delete("/api/projects/"+rid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.delete("/api/projects/"+rid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,404)
        with db() as c:
            for table,column in (("projects","id"),("design_requests","id"),("design_briefs","project"),("files","project"),("client_requests","project")):
                self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM "+table+" WHERE "+column+"=?",(rid,)).fetchone()["n"],0)
            self.assertIsNotNone(c.execute("SELECT id FROM projects WHERE id=?",(other,)).fetchone())

    def test_v520_client_global_quota_isolated_by_sender(self):
        from app import limit_key
        ip="198.51.100.1"
        h={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=h,base_url=ORIGIN).status_code,201)
        # Seed the exhausted per-sender aggregate counter, not a global counter.
        with app.test_request_context("/",environ_overrides={"REMOTE_ADDR":ip}):
            key=limit_key("client-login")
            registration=limit_key("register")
        import time
        with db() as c:
            for k,n in ((key,50),(registration,20)):
                c.execute("INSERT INTO client_limits VALUES(?,?,?) ON CONFLICT(action) DO UPDATE SET count=excluded.count,since=excluded.since",(k,n,int(time.time())))
        self.assertEqual(self.client.post("/api/client/login",json=d,headers=h,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":ip}).status_code,429)
        self.assertEqual(self.client.post("/api/client/login",json=d,headers=h,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.2"}).status_code,200)
        d["email"]="b@example.invalid"
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=h,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":ip}).status_code,429)
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=h,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.2"}).status_code,201)

    def test_v520_login_sender_isolation(self):
        for _ in range(8):
            self.assertEqual(self.client.post("/login",json={"password":"wrong"},base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.1"}).status_code,401)
        self.assertEqual(self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.1"}).status_code,429)
        self.assertEqual(self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.2"}).status_code,200)
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=headers,base_url=ORIGIN).status_code,201)
        for _ in range(8):
            self.assertEqual(self.client.post("/api/client/login",json={**d,"password":"wrong"},headers=headers,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.1"}).status_code,401)
        self.assertEqual(self.client.post("/api/client/login",json=d,headers=headers,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.1"}).status_code,429)
        self.assertEqual(self.client.post("/api/client/login",json=d,headers=headers,base_url=ORIGIN,environ_overrides={"REMOTE_ADDR":"198.51.100.2"}).status_code,200)
        self.assertEqual(self.client.get("/api/projects",base_url=ORIGIN).status_code,200)

    def test_v520_private_files_and_delete(self):
        headers={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=headers,base_url=ORIGIN).status_code,201)
        order=self.data();order["files"]=[(io.BytesIO(png()),"one.png"),(io.BytesIO(png()),"two.png")]
        rid=self.submit(order).json["id"]
        self.assertEqual(self.client.delete("/api/projects/"+rid,json={"confirm":True},base_url=ORIGIN).status_code,401)
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        h={"X-CSRF":login.json["csrf"]}
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).status_code,200)
        p=self.client.get("/api/projects",base_url=ORIGIN).json["projects"][0]
        fid=p["files"][0]["id"]
        self.assertEqual(self.client.put("/api/files/"+fid,json={"public":True},headers=h,base_url=ORIGIN).status_code,403)
        self.assertEqual(self.client.delete("/api/files/"+fid,json={"confirm":True},base_url=ORIGIN).status_code,403)
        self.assertEqual(self.client.delete("/api/files/"+fid,json={"confirm":False},headers=h,base_url=ORIGIN).status_code,400)
        self.assertEqual(self.client.delete("/api/files/"+fid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get("/api/files/"+fid,base_url=ORIGIN).status_code,404)
        cid=self.client.get("/api/clients",base_url=ORIGIN).json["clients"][0]["id"]
        self.assertEqual(self.client.delete("/api/clients/"+cid,json={"confirm":True},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).status_code,401)
        with db() as c:
            for table in ("projects","files","client_requests","design_briefs","design_requests","clients"):
                self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM "+table).fetchone()["n"],0)
        self.assertEqual(self.client.get("/api/projects",base_url=ORIGIN).status_code,200)

    def test_v520_ignore_untrusted_forwarded_address(self):
        from app import sender_address
        from unittest.mock import patch
        with patch.dict(os.environ, {"LERIKA_TRUSTED_CLIENT_IP_HEADER":"CF-Connecting-IP"}):
            with app.test_request_context("/",headers={"CF-Connecting-IP":"192.0.2.9","X-Forwarded-For":"192.0.2.10"},environ_overrides={"REMOTE_ADDR":"8.8.8.8"}):
                self.assertEqual(sender_address(),"8.8.8.8")

    def test_v520_render_proxy_header_and_ip_normalization(self):
        from app import sender_address
        from unittest.mock import patch
        with patch.dict(os.environ, {"RENDER":"true","LERIKA_TRUSTED_CLIENT_IP_HEADER":"CF-Connecting-IP"}):
            cases=[
                ("8.8.4.4","8.8.4.4"),
                ("::ffff:8.8.4.4","8.8.4.4"),
                ("2001:4860:1234:5678::1","2001:4860:1234:5678::/64"),
                ("2001:4860:1234:5678::2","2001:4860:1234:5678::/64"),
                ("8.8.8.8, 8.8.4.4","10.0.0.2"),
                ("invalid","10.0.0.2"),
                ("","10.0.0.2"),
            ]
            for value, expected in cases:
                with self.subTest(value=value):
                    with app.test_request_context("/",headers={"CF-Connecting-IP":value,"X-Forwarded-For":"1.1.1.1"},environ_overrides={"REMOTE_ADDR":"10.0.0.2"}):
                        self.assertEqual(sender_address(),expected)

    def test_v520_proxy_order_limit_ignores_spoofed_xff(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"RENDER":"true","LERIKA_TRUSTED_CLIENT_IP_HEADER":"CF-Connecting-IP"}):
            for i in range(12):
                h={**HEADERS,"CF-Connecting-IP":"8.8.8.8","X-Forwarded-For":"192.0.2."+str(i+1)}
                self.assertEqual(self.submit(self.data(),headers=h,ip="10.0.0.2").status_code,201)
            h={**HEADERS,"CF-Connecting-IP":"8.8.8.8","X-Forwarded-For":"192.0.2.99"}
            self.assertEqual(self.submit(self.data(),headers=h,ip="10.0.0.2").status_code,429)
            h["CF-Connecting-IP"]="8.8.4.4"
            self.assertEqual(self.submit(self.data(),headers=h,ip="10.0.0.2").status_code,201)

    def test_v520_logout_does_not_clear_other_role(self):
        h={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        d={"name":"Test","email":"a@example.invalid","password":"long-test-password-123","consent":True}
        self.assertEqual(self.client.post("/api/client/register",json=d,headers=h,base_url=ORIGIN).status_code,201)
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.client.post("/logout",headers={"X-CSRF":login.json["csrf"]},base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get("/session",base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).status_code,200)
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.client.post("/api/client/logout",json={},headers=h,base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client.get("/api/client/session",base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client.get("/session",base_url=ORIGIN).status_code,200)

    @unittest.skipUnless(QA_POSTGRES,"PostgreSQL-only connection check")
    def test_v520_postgres_connections_close_on_success_and_exception(self):
        with db() as c:
            self.assertEqual(c.execute("SELECT 1 AS n").fetchone()["n"],1)
        self.assertTrue(c.conn.closed)
        with self.assertRaisesRegex(RuntimeError,"rollback probe"):
            with db() as c:
                c.execute("INSERT INTO client_limits VALUES(?,?,?)",("qa-rollback",1,1))
                raise RuntimeError("rollback probe")
        self.assertTrue(c.conn.closed)
        with db() as check:
            self.assertIsNone(check.execute("SELECT action FROM client_limits WHERE action=?",("qa-rollback",)).fetchone())

    @unittest.skipIf(QA_POSTGRES,"SQLite-only connection check")
    def test_v520_sqlite_connections_close_on_success_and_exception(self):
        import sqlite3
        with db() as c:
            self.assertEqual(c.execute("SELECT 1").fetchone()[0],1)
        with self.assertRaises(sqlite3.ProgrammingError):
            c.execute("SELECT 1")
        with self.assertRaisesRegex(RuntimeError,"rollback probe"):
            with db() as c:
                c.execute("INSERT INTO client_limits VALUES(?,?,?)",("qa-rollback",1,1))
                raise RuntimeError("rollback probe")
        with self.assertRaises(sqlite3.ProgrammingError):
            c.execute("SELECT 1")
        with db() as check:
            self.assertIsNone(check.execute("SELECT action FROM client_limits WHERE action=?",("qa-rollback",)).fetchone())

    def test_request_numbers_migration_retry_and_delete(self):
        from app import migrate_request_numbers,lock
        h={"Origin":ORIGIN,"X-Lerika-Client":"1"}
        self.assertEqual(self.client.post("/api/client/register",json={"name":"Test","email":"number@example.invalid","password":"long-test-password-123","consent":True},headers=h,base_url=ORIGIN).status_code,201)
        first=self.data()
        a=self.submit(first);self.assertEqual(a.status_code,201)
        b=self.submit(self.data());self.assertEqual(b.status_code,201)
        self.assertRegex(a.json["number"],r"^L-[0-9]{6,}$")
        self.assertEqual(int(b.json["number"][2:]),int(a.json["number"][2:])+1)
        self.assertEqual(self.submit(first).json,a.json)
        self.assertEqual({o["number"] for o in self.client.get("/api/client/session",base_url=ORIGIN).json["orders"]},{a.json["number"],b.json["number"]})
        # Simulate one legacy request without a number and migrate twice.
        with db() as c:
            lock(c,82003)
            c.execute("DELETE FROM request_numbers WHERE request_id=?",(b.json["id"],))
            migrate_request_numbers(c)
            row=c.execute("SELECT number FROM request_numbers WHERE request_id=?",(b.json["id"],)).fetchone()["number"]
            migrate_request_numbers(c)
            self.assertEqual(c.execute("SELECT number FROM request_numbers WHERE request_id=?",(b.json["id"],)).fetchone()["number"],row)
        self.assertGreater(row,int(b.json["number"][2:]))
        login=self.client.post("/login",json={"password":"local-test-password-only"},base_url=ORIGIN)
        self.assertEqual(login.status_code,200)
        listing=self.client.get("/api/projects",base_url=ORIGIN).json["projects"]
        self.assertEqual(next(p["request_number"] for p in listing if p["id"]==a.json["id"]),a.json["number"])
        csrf=login.json["csrf"]
        self.assertEqual(self.client.delete("/api/projects/"+a.json["id"],json={"confirm":True},headers={"X-CSRF":csrf},base_url=ORIGIN).status_code,200)
        c=self.submit(self.data());self.assertEqual(c.status_code,201)
        self.assertGreater(int(c.json["number"][2:]),row)

    def test_configured_origin_and_public_cache(self):
        from unittest.mock import patch
        from app import checked_origin
        domain="https://lerika-qa.example.invalid"
        for bad in ("http://example.invalid","https://example.invalid/path","https://x.invalid@evil.invalid","https://x.invalid?x=1"):
            with self.assertRaises(RuntimeError): checked_origin(bad)
        with patch("app.PUBLIC_ORIGIN",domain),patch("app.ALLOWED_ORIGINS",{domain,ORIGIN}):
            r=self.client.get("/showroom/",base_url=domain)
            self.assertEqual(r.status_code,200)
            self.assertTrue(('name="lerika-app-origin" content="'+domain+'"').encode() in r.data)
            self.assertTrue(b'name="lerika-portfolio-api" content="/"' in r.data)
            self.assertEqual(r.headers["Cache-Control"],"no-store")
            self.assertEqual(self.client.post("/api/design-requests",data=self.data(),headers={"Origin":domain,"X-Lerika-Studio":"5.6"},base_url=domain,content_type="multipart/form-data").status_code,201)
            self.assertEqual(self.client.post("/api/design-requests",data=self.data(),headers={"Origin":"https://evil.invalid","X-Lerika-Studio":"5.6"},base_url=domain,content_type="multipart/form-data").status_code,403)
            self.assertEqual(self.client.post("/api/design-requests",data=self.data(),headers={"Origin":ORIGIN,"X-Lerika-Studio":"5.6"},base_url=domain,content_type="multipart/form-data").status_code,403)
            self.assertEqual(self.client.post("/api/design-requests",data=self.data(),headers={"Origin":domain,"X-Lerika-Studio":"5.6"},base_url="https://evil.invalid",content_type="multipart/form-data").status_code,403)
            r=self.client.get("/public/portfolio",headers={"Origin":domain},base_url=domain)
            self.assertEqual(r.headers["Access-Control-Allow-Origin"],domain)
            self.assertIn("Origin",r.headers["Vary"])
            self.assertEqual(r.headers["Cache-Control"],"no-store")
            r=self.client.get("/showroom/",base_url="https://evil.invalid")
            self.assertFalse(b'content="https://evil.invalid"' in r.data)
        from pathlib import Path
        from app import SITE_ROOT
        scenes=sorted(SITE_ROOT.glob("scene-*.webp"))
        self.assertEqual(len(scenes),2)
        for f in scenes:
            r=self.client.get("/showroom/"+f.name)
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers["Cache-Control"],"public, max-age=31536000, immutable")
            self.assertEqual(r.data,f.read_bytes())
        public=sorted(SITE_ROOT.glob("public-*.webp"))
        self.assertEqual(len(public),14)
        import hashlib
        for f in public:
            r=self.client.get("/showroom/"+f.name)
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers["Cache-Control"],"public, max-age=31536000, immutable")
            self.assertEqual(r.mimetype,"image/webp")
            self.assertLessEqual(len(r.data),200000)
            self.assertEqual(hashlib.sha256(r.data).hexdigest()[:16],f.stem.rsplit("-",1)[1])
            with Image.open(io.BytesIO(r.data)) as im:
                self.assertEqual(im.format,"WEBP")
                if f.name.startswith("public-kitchen-"):self.assertEqual(im.size,(1080,1400))
                if f.name.startswith("public-stairs-"):self.assertEqual(im.size,(1080,1020))
            # V5.37 removed the standalone configurator card; the content-addressed
            # asset remains available for old links but must not be used by the showroom.
            referenced = f.name in (SITE_ROOT/"index.html").read_text()
            if f.name == "public-lab-config-3c29837353a0ee70.webp":
                self.assertFalse(referenced)
            else:
                self.assertTrue(referenced, f.name)
        self.assertEqual(self.client.get("/showroom/public-unknown-0000000000000000.webp").headers["Cache-Control"],"no-store")
        self.assertLess((SITE_ROOT/"index.html").stat().st_size,500000)
        self.assertEqual(self.client.get("/api/projects").headers["Cache-Control"],"no-store")

    def test_showroom_local_revision_and_csp(self):
        r=self.client.get("/showroom/")
        self.assertEqual(r.status_code,200)
        self.assertTrue("ЛЕРИКА · V5.23.1".encode() in r.data,"local V5.23.1 revision not served")
        self.assertNotIn(b'id="lab-ai-generate"',r.data)
        self.assertIn("sha256-",r.headers["Content-Security-Policy"])
        self.assertIn(b'id="lab3-canvas"',r.data)

if __name__=="__main__":unittest.main()
