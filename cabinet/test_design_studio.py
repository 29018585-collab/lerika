"""Isolated Lab V5.6 acceptance tests; no production DB or credentials."""
import os, tempfile, unittest, io, secrets
from pathlib import Path
from PIL import Image
tmp=tempfile.TemporaryDirectory()
os.environ.pop("RENDER",None)
os.environ["DATABASE_URL"]=""
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
            for table in ("covers","files","design_briefs","design_requests","projects","attempts"):
                c.execute("DELETE FROM "+table)
    def data(self,rid=None):
        return dict(request_id=rid or secrets.token_hex(16),consent="yes",title="Тест кухни",room="Кухня",contact="test@example.invalid",brief="Пожелания: тест")
    def submit(self,data,headers=HEADERS):
        return self.client.post("/api/design-requests",data=data,headers=headers,base_url=ORIGIN,content_type="multipart/form-data")
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
        self.assertEqual(self.client.put("/api/projects/"+rid,base_url=ORIGIN,headers={"X-CSRF":csrf},json={**p,"published":True}).status_code,200)
        public=self.client.get("/public/portfolio").json["projects"][0]
        self.assertNotIn("private_brief",public)
        self.assertNotIn("test@example.invalid",str(public))
        self.assertNotIn("Пожелания: тест",str(public))
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
    def test_showroom_local_revision_and_csp(self):
        r=self.client.get("/showroom/")
        self.assertEqual(r.status_code,200)
        self.assertIn(b"LERIKA LAB V5.6",r.data)
        self.assertNotIn(b'id="lab-ai-generate"',r.data)
        self.assertIn("sha256-",r.headers["Content-Security-Policy"])
        self.assertIn(b'id="lab3-canvas"',r.data)

if __name__=="__main__":unittest.main()
