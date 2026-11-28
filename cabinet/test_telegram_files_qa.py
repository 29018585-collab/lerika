"""Synthetic tests only. Run: cd cabinet && python -m unittest test_telegram_files_qa"""
import contextlib
import sqlite3
import time
import unittest
from telegram_files import attachment_from_message, validate_bytes, receive_attachment, IntakeError, MAX_BYTES
from telegram_intake import handle_test_order, pilot_keyboard

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
    def test_photo_and_path(self):
        spec=attachment_from_message({"photo":[{"file_size":3,"file_id":"small"},{"file_size":5,"file_id":"big","file_unique_id":"x"}]})
        self.assertEqual(spec[1:],("big",5))
        self.assertEqual(attachment_from_message(self.msg("../../private.pdf"))[0],"private.pdf")
        validate_bytes("photo.jpg",b"\xff\xd8\xfftest")
        with self.assertRaises(IntakeError):
            validate_bytes("bad.zip",b"not a zip")

if __name__=="__main__":
    unittest.main()
