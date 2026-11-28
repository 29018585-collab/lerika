"""Synthetic tests only. Run: cd cabinet && python -m unittest test_telegram_files_qa"""
import contextlib
import hashlib
import hmac
import sqlite3
import time
import unittest
from telegram_files import attachment_from_message, validate_bytes, receive_attachment, IntakeError, MAX_BYTES
from telegram_intake import handle_test_order, pilot_keyboard
from telegram_stage_notifications import preference,event_for_edit,deliver_event
from telegram_client_pilot import allowed,enrolled,registration,registration_keyboard,notification_chat,digest_for,JOIN,CONSENT,LEAVE
from telegram_web_link import issue,claim,confirm,unlink,active_digests

class TelegramFileQA(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(":memory:")
        self.conn.row_factory=sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
        CREATE TABLE telegram_test_drafts(chat_key TEXT PRIMARY KEY, code TEXT, brief TEXT, expires INTEGER);
        CREATE TABLE telegram_test_files(chat_key TEXT REFERENCES telegram_test_drafts(chat_key) ON DELETE CASCADE,code TEXT,checksum TEXT,name TEXT,data BLOB,PRIMARY KEY(chat_key,code,checksum));
        CREATE TABLE projects(id TEXT PRIMARY KEY,category INT,title TEXT,description TEXT,stage INT,status TEXT,published INT,updated INT);
        CREATE TABLE files(id TEXT PRIMARY KEY,project TEXT,stage INT,name TEXT,mime TEXT,image INT,public INT,data BLOB);
        CREATE TABLE design_briefs(project TEXT,brief TEXT);
        CREATE TABLE design_requests(id TEXT PRIMARY KEY,created INT);
        CREATE TABLE request_numbers(number INTEGER,request_id TEXT PRIMARY KEY);
        CREATE TABLE telegram_test_owners(request_id TEXT PRIMARY KEY REFERENCES design_requests(id) ON DELETE CASCADE,chat_key TEXT NOT NULL);
        CREATE TABLE telegram_test_subscriptions(chat_key TEXT PRIMARY KEY);
        CREATE TABLE telegram_pilot_clients(chat_key TEXT PRIMARY KEY, created INTEGER NOT NULL);
        CREATE TABLE telegram_pilot_pending(chat_key TEXT PRIMARY KEY, expires INTEGER NOT NULL);
        CREATE TABLE clients(id TEXT PRIMARY KEY);
        CREATE TABLE client_requests(project TEXT PRIMARY KEY,client TEXT NOT NULL REFERENCES clients(id));
        CREATE TABLE telegram_web_links(client TEXT PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,chat_key TEXT UNIQUE NOT NULL,created INTEGER NOT NULL);
        CREATE TABLE telegram_web_pending(client TEXT PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,token_hash TEXT UNIQUE NOT NULL,expires INTEGER NOT NULL,chat_key TEXT,proof_hash TEXT);
        """)
        self.notices=[]
        self.key="k"*32
        self.digest="admin"
        self.raw=b"%PDF-1.4\nsynthetic"
    def tearDown(self):
        self.conn.close()
    @contextlib.contextmanager
    def db(self):
        with self.conn:
            yield self.conn
    def lock(self,c,k):
        c.execute("BEGIN IMMEDIATE")
    def existing(self,c,rid):
        row=c.execute("SELECT number FROM request_numbers WHERE request_id=?",(rid,)).fetchone()
        return "L-"+str(row["number"]).zfill(6) if row else None
    def allocate(self,c,rid):
        n=c.execute("SELECT COALESCE(MAX(number),0)+1 AS n FROM request_numbers").fetchone()["n"]
        c.execute("INSERT INTO request_numbers VALUES(?,?)",(n,rid))
        return "L-"+str(n).zfill(6)
    def order(self,text,digest=None):
        return handle_test_order(text,digest or self.digest,self.key,self.db,self.lock,self.allocate,self.existing,lambda v:None,lambda *v:self.notices.append(v))
    def code(self):
        return self.conn.execute("SELECT code FROM telegram_test_drafts").fetchone()["code"]
    def msg(self,name="test.pdf",raw=None):
        raw=self.raw if raw is None else raw
        return {"document":{"file_name":name,"file_id":"synthetic_1","file_size":len(raw)}}
    def receive(self,name="test.pdf",raw=None,digest=None):
        raw=self.raw if raw is None else raw
        return receive_attachment(self.msg(name,raw),digest or self.digest,"unused",self.db,self.lock,downloader=lambda *a:raw)
    def count(self,table):
        return self.conn.execute("SELECT COUNT(*) AS n FROM "+table).fetchone()["n"]
    def test_confirm_private_idempotent(self):
        self.order("/order_test synthetic cabinet")
        code=self.code()
        self.assertIn("прикреплён",self.receive())
        self.assertIn("уже",self.receive())
        self.assertEqual(self.count("files"),0)
        self.assertIn("L-000001",self.order("/confirm "+code))
        self.assertIn("L-000001",self.order("/confirm "+code))
        self.assertEqual(self.count("files"),1)
        f=self.conn.execute("SELECT * FROM files").fetchone()
        self.assertEqual((f["public"],f["image"],f["mime"],f["data"]),(0,0,"application/octet-stream",self.raw))
        self.assertEqual(self.count("telegram_test_files"),0)
        self.assertEqual(len(self.notices),1)
        self.assertEqual(self.notices[0][-1],1)
    def test_no_draft_or_other_sender(self):
        self.assertIn("Сначала",self.receive())
        self.order("/order_test synthetic cabinet")
        self.assertIn("Сначала",self.receive(digest="other"))
    def test_cancel_replace_expiry(self):
        self.order("/order_test synthetic cabinet")
        self.receive()
        self.order("/cancel")
        self.assertEqual(self.count("telegram_test_files"),0)
        self.order("/order_test synthetic cabinet")
        self.receive()
        self.order("/order_test another draft")
        self.assertEqual(self.count("telegram_test_files"),0)
        self.receive()
        with self.conn:
            self.conn.execute("UPDATE telegram_test_drafts SET expires=?",(int(time.time())-1,))
        self.assertIn("Сначала",self.receive())
        self.assertEqual(self.count("telegram_test_files"),0)
    def test_bad_files(self):
        self.order("/order_test synthetic cabinet")
        self.assertIn("формат",self.receive("malware.exe"))
        self.assertIn("Содержимое",self.receive("fake.pdf",b"not a pdf"))
        self.assertEqual(self.count("telegram_test_files"),0)
        with self.assertRaises(IntakeError):
            attachment_from_message({"document":{"file_name":"large.pdf","file_id":"f","file_size":MAX_BYTES+1}})
    def test_count_limit(self):
        self.order("/order_test synthetic cabinet")
        for i in range(10):
            self.assertIn("прикреплён",self.receive(str(i)+".pdf",self.raw+str(i).encode()))
        self.assertIn("Лимит",self.receive("extra.pdf",self.raw+b"extra"))
        self.assertEqual(self.count("telegram_test_files"),10)
    def buttons(self):
        return [b["text"] for row in pilot_keyboard(self.digest,self.db,self.lock)["keyboard"] for b in row]
    def test_button_flow(self):
        self.assertIn("➕ Новая тестовая заявка",self.buttons())
        self.order("➕ Новая тестовая заявка")
        code=self.code()
        self.assertNotIn("✅ Отправить "+code,self.buttons())
        self.assertIn("Сначала",self.receive())
        self.assertIn("Сначала",self.order("✅ Отправить "+code))
        self.assertIn("Описание сохранено",self.order("Тестовая мебель для условной комнаты"))
        self.assertIn("✅ Отправить "+code,self.buttons())
        self.assertIn("прикреплён",self.receive())
        self.assertIn("Вложений: 1",self.order("📋 Черновик"))
        self.assertIn("L-000001",self.order("✅ Отправить "+code))
        self.assertIn("L-000001",self.order("✅ Отправить "+code))
        self.assertEqual(self.count("files"),1)
        self.assertEqual(self.count("design_requests"),1)
        self.assertEqual(len(self.notices),1)
        self.assertIn("➕ Новая тестовая заявка",self.buttons())
    def test_stale_buttons_and_duplicate_begin(self):
        self.order("➕ Новая тестовая заявка")
        old=self.code()
        self.order("➕ Новая тестовая заявка")
        self.assertEqual(self.code(),old)
        self.order("❌ Отменить "+old)
        self.order("➕ Новая тестовая заявка")
        new=self.code()
        self.assertNotEqual(old,new)
        self.assertIn("старому",self.order("❌ Отменить "+old))
        self.assertIn("Код не подходит",self.order("✅ Отправить "+old))
        self.assertEqual(self.code(),new)
        self.assertEqual(self.count("design_requests"),0)
        self.assertIsNone(self.order("🌐 Инструменты сайта"))
        self.assertIsNone(self.order("/ai synthetic question"))
    def test_history_and_live_status_owner_scope(self):
        self.assertIn("пока нет",self.order("📦 Мои заявки"))
        self.order("/order_test synthetic cabinet")
        code=self.code()
        self.assertIn("L-000001",self.order("/confirm "+code))
        self.assertIn("📦 Мои заявки",self.buttons())
        self.assertIn("L-000001",self.order("📦 Мои заявки"))
        self.assertIn("Исходное помещение",self.order("/status L-000001"))
        self.assertNotIn("L-000001",self.order("/orders",digest="other"))
        self.assertEqual(self.order("/status L-000001",digest="other"),self.order("/status L-999999"))
        self.assertIn("формате",self.order("/status invalid"))
        with self.conn:
            self.conn.execute("UPDATE projects SET stage=3 WHERE id IN (SELECT request_id FROM telegram_test_owners)")
        self.assertIn("3D-проект",self.order("/status L-000001"))
        with self.conn:
            self.conn.execute("UPDATE projects SET stage=6,status='ready'")
        self.assertIn("Готово",self.order("/status L-000001"))
        with self.conn:
            self.conn.execute("DELETE FROM design_requests")
        self.assertEqual(self.count("telegram_test_owners"),0)
        self.assertIn("не найдена",self.order("/status L-000001"))
    def test_history_does_not_consume_description(self):
        self.order("➕ Новая тестовая заявка")
        self.order("📦 Мои заявки")
        self.order("/status L-000001")
        row=self.conn.execute("SELECT brief FROM telegram_test_drafts").fetchone()
        self.assertEqual(row["brief"],"")
        self.assertIn("Описание сохранено",self.order("Тестовое описание"))
    def test_stage_notification_opt_in_and_dedup(self):
        cid="123456"
        self.digest=hmac.new(self.key.encode(),cid.encode(),hashlib.sha256).hexdigest()[:32]
        self.order("/order_test synthetic cabinet")
        self.order("/confirm "+self.code())
        rid=self.conn.execute("SELECT id FROM design_requests").fetchone()["id"]
        old={"stage":1,"status":"work"}
        self.assertIn("🔔 Включить уведомления",self.buttons())
        self.assertIsNone(event_for_edit(self.conn,rid,old,3,"work"))
        preference("/notify_on",self.digest,self.db,self.lock)
        preference("/notify_on",self.digest,self.db,self.lock)
        self.assertEqual(self.count("telegram_test_subscriptions"),1)
        self.assertIn("🔕 Выключить уведомления",self.buttons())
        self.assertIsNone(event_for_edit(self.conn,rid,old,1,"work"))
        event=event_for_edit(self.conn,rid,old,3,"work")
        sent=[]
        def sender(token,method,payload):
            sent.append(payload)
            return {"message_id":1}
        self.assertFalse(deliver_event(event,self.key,"123457","synthetic",sender))
        self.assertEqual(sent,[])
        self.assertTrue(deliver_event(event,self.key,cid,"synthetic",sender))
        self.assertEqual(sent[0]["chat_id"],int(cid))
        self.assertIn("3D-проект",sent[0]["text"])
        self.assertNotIn("synthetic cabinet",sent[0]["text"])
        self.assertIsNone(event_for_edit(self.conn,rid,{"stage":3,"status":"work"},3,"work"))
        self.assertFalse(deliver_event(event,self.key,cid,"synthetic",lambda *a:None))
        preference("/notify_off",self.digest,self.db,self.lock)
        self.assertIsNone(event_for_edit(self.conn,rid,old,4,"work"))
    def test_pilot_access_and_consent(self):
        self.assertFalse(allowed(123456,"","123456"))
        self.assertFalse(allowed(123456,"1","123457"))
        self.assertTrue(allowed(123456,"1","123456,123457"))
        self.assertFalse(allowed(True,"1","1"))
        self.assertNotIn(CONSENT,str(registration_keyboard()))
        self.assertIn(CONSENT,str(registration_keyboard(True)))
        digest=digest_for(self.key,123456)
        registration(CONSENT,digest,self.db,self.lock,now=100)
        self.assertFalse(enrolled(self.conn,digest))
        registration(JOIN,digest,self.db,self.lock,now=100)
        registration(CONSENT,digest,self.db,self.lock,now=1001)
        self.assertFalse(enrolled(self.conn,digest))
        registration(JOIN,digest,self.db,self.lock,now=1100)
        registration(CONSENT,digest,self.db,self.lock,now=1101)
        self.assertTrue(enrolled(self.conn,digest))
        self.assertIn(LEAVE,str(pilot_keyboard(digest,self.db,self.lock,client=True)))
    def test_two_pilot_owners_and_exit(self):
        first,second=[digest_for(self.key,i) for i in (123456,123457)]
        for digest in (first,second):
            registration(JOIN,digest,self.db,self.lock)
            registration(CONSENT,digest,self.db,self.lock)
            self.order("/order_test synthetic cabinet",digest=digest)
            code=self.conn.execute("SELECT code FROM telegram_test_drafts WHERE chat_key=?",(digest,)).fetchone()["code"]
            self.order("/confirm "+code,digest=digest)
            preference("/notify_on",digest,self.db,self.lock)
        self.assertIn("L-000001",self.order("/orders",digest=first))
        self.assertNotIn("L-000002",self.order("/orders",digest=first))
        self.assertIn("L-000002",self.order("/orders",digest=second))
        self.assertIn("недоступна",self.order("/status L-000001",digest=second))
        rid=self.conn.execute("SELECT request_id FROM telegram_test_owners WHERE chat_key=?",(first,)).fetchone()["request_id"]
        event=event_for_edit(self.conn,rid,{"stage":1,"status":"work"},3,"work")
        self.assertEqual(notification_chat(self.conn,event,self.key,"999999","1","123456,123457"),"123456")
        self.assertEqual(notification_chat(self.conn,event,self.key,"999999","1","123457"),"")
        self.assertEqual(notification_chat(self.conn,event,self.key,"999999","0","123456"),"")
        self.order("/order_test new synthetic draft",digest=first)
        self.receive(digest=first)
        registration(LEAVE,first,self.db,self.lock)
        self.assertFalse(enrolled(self.conn,first))
        self.assertTrue(enrolled(self.conn,second))
        self.assertEqual(self.count("telegram_test_files"),0)
        self.assertEqual(self.count("telegram_test_drafts"),0)
        self.assertEqual(self.count("design_requests"),2)
        self.assertIsNone(event_for_edit(self.conn,rid,{"stage":1,"status":"work"},3,"work"))
        self.assertEqual(notification_chat(self.conn,event,self.key,"999999","1","123456,123457"),"")
    def test_web_link_two_channels_and_expiry(self):
        first,second=[digest_for(self.key,i) for i in (123456,123457)]
        for digest in (first,second):
            registration(JOIN,digest,self.db,self.lock)
            registration(CONSENT,digest,self.db,self.lock)
        permitted=active_digests(self.key,"1","123456,123457")
        with self.conn:
            self.conn.execute("INSERT INTO clients VALUES('a'),('b')")
            token=issue(self.conn,"a",self.key,100)
            self.assertNotEqual(token,self.conn.execute("SELECT token_hash FROM telegram_web_pending").fetchone()["token_hash"])
            self.assertIsNone(claim(self.conn,first,self.key,token,701))
            token=issue(self.conn,"a",self.key,800)
            proof=claim(self.conn,first,self.key,token,801)
            self.assertIsNotNone(proof)
            self.assertIsNone(claim(self.conn,second,self.key,token,802))
            self.assertFalse(confirm(self.conn,"b",self.key,proof,803,permitted))
            self.assertFalse(confirm(self.conn,"a",self.key,proof,803,{second}))
            self.assertFalse(confirm(self.conn,"a",self.key,"0"*16,803,permitted))
            self.assertTrue(confirm(self.conn,"a",self.key,proof,804,permitted))
            self.assertFalse(confirm(self.conn,"a",self.key,proof,805,permitted))
            self.assertIsNone(issue(self.conn,"a",self.key,806))
            other=issue(self.conn,"b",self.key,807)
            self.assertIsNone(claim(self.conn,first,self.key,other,808))
            unlink(self.conn,"a")
            self.assertEqual(self.count("telegram_web_links"),0)
    def test_linked_history_without_transfer_and_revocation(self):
        first,second=[digest_for(self.key,i) for i in (123456,123457)]
        for digest in (first,second):
            registration(JOIN,digest,self.db,self.lock)
            registration(CONSENT,digest,self.db,self.lock)
        self.order("/order_test synthetic cabinet",digest=first)
        self.order("/confirm "+self.code(),digest=first)
        rid=self.conn.execute("SELECT id FROM design_requests").fetchone()["id"]
        with self.conn:
            self.conn.execute("INSERT INTO clients VALUES('web')")
            self.conn.execute("INSERT INTO client_requests VALUES(?,?)",(rid,"web"))
            token=issue(self.conn,"web",self.key,100)
            proof=claim(self.conn,second,self.key,token,101)
            self.assertTrue(confirm(self.conn,"web",self.key,proof,102,{first,second}))
        self.assertIn("L-000001",self.order("/orders",digest=second))
        registration(LEAVE,second,self.db,self.lock)
        self.assertNotIn("L-000001",self.order("/orders",digest=second))
        self.assertIn("L-000001",self.order("/orders",digest=first))
        self.assertEqual(self.count("client_requests"),1)
        self.assertEqual(self.count("design_requests"),1)
        self.assertEqual(self.count("telegram_web_links"),0)
    def test_photo_and_path(self):
        spec=attachment_from_message({"photo":[{"file_size":3,"file_id":"small"},{"file_size":5,"file_id":"big","file_unique_id":"x"}]})
        self.assertEqual(spec[1:],("big",5))
        self.assertEqual(attachment_from_message(self.msg("../../private.pdf"))[0],"private.pdf")
        validate_bytes("photo.jpg",b"\xff\xd8\xfftest")
        with self.assertRaises(IntakeError):
            validate_bytes("bad.zip",b"not a zip")

if __name__=="__main__":
    unittest.main()
