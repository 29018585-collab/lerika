import os, tempfile, io, unittest
from werkzeug.security import generate_password_hash
from PIL import Image
tmp=tempfile.TemporaryDirectory()
os.environ.update(DATA_DIR=tmp.name,SESSION_SECRET="test-secret-not-for-production-123456",ADMIN_PASSWORD_HASH=generate_password_hash("test-only-password"))
from app import app

class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.c=app.test_client()
        self.base="https://localhost"
        r=self.c.post("/login",json={"password":"test-only-password"},base_url=self.base)
        self.assertEqual(r.status_code,200)
        self.headers={"X-CSRF":r.json["csrf"]}
        self.p={"category":8,"title":"Test","description":"Example","stage":3,"status":"work","published":True}
        r=self.c.post("/api/projects",json=self.p,headers=self.headers,base_url=self.base)
        self.assertEqual(r.status_code,201)
        self.id=r.json["id"]
    def upload(self,name,raw):
        r=self.c.post("/api/projects/"+self.id+"/files",data={"stage":"3","file":(io.BytesIO(raw),name)},headers=self.headers,base_url=self.base)
        self.assertEqual(r.status_code,201)
        return r.json["id"]
    def test_publication_boundaries(self):
        anon=app.test_client()
        b=io.BytesIO();Image.new("RGB",(32,32),"red").save(b,"PNG")
        photo=self.upload("photo.png",b.getvalue())
        doc=self.upload("estimate.pdf",b"private test")
        url="/api/projects/"+self.id
        pub="/public/photos/"
        self.assertEqual(anon.get("/api/projects").status_code,401)
        self.assertEqual(anon.get("/api/files/"+doc).status_code,401)
        self.assertEqual(anon.get(pub+photo).status_code,404)
        self.assertEqual(self.c.put(url,json=self.p,base_url=self.base).status_code,403)
        self.assertEqual(self.c.put("/api/files/"+doc,json={"public":True},headers=self.headers,base_url=self.base).status_code,400)
        self.assertEqual(self.c.put("/api/files/"+photo,json={"public":True},headers=self.headers,base_url=self.base).status_code,200)
        self.assertEqual(anon.get(pub+photo).status_code,404)
        self.assertEqual(self.c.put(url,json=self.p,headers=self.headers,base_url=self.base).status_code,200)
        result=anon.get("/public/portfolio").json
        project=next(p for p in result["projects"] if p["id"]==self.id)
        self.assertEqual(project["photos"],[{"id":photo,"stage":3}])
        self.assertEqual(anon.get(pub+photo).status_code,200)
        self.assertEqual(anon.get(pub+doc).status_code,404)
        self.assertEqual(self.c.put("/api/covers/8",json={"file":photo},headers=self.headers,base_url=self.base).status_code,200)
        self.assertEqual(anon.get("/public/portfolio").json["covers"]["8"],photo)
        self.p["published"]=False
        self.assertEqual(self.c.put(url,json=self.p,headers=self.headers,base_url=self.base).status_code,200)
        self.assertEqual(anon.get(pub+photo).status_code,404)
        self.assertNotIn("8",anon.get("/public/portfolio").json["covers"])
    def test_complete_requires_final_stage(self):
        self.p["status"]="ready"
        self.assertEqual(self.c.put("/api/projects/"+self.id,json=self.p,headers=self.headers,base_url=self.base).status_code,400)
if __name__=="__main__": unittest.main()
