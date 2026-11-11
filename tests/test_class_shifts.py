import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class ClassShiftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        server.DB_FILE=Path(self.tmp.name)/'db.sqlite3'
        server.init_db()
        self.db=server.connect()
        self.handler=object.__new__(server.Handler)
        self.teacher=self.db.execute("INSERT INTO teachers(name) VALUES ('Ana')").lastrowid
        self.subject=self.db.execute("INSERT INTO subjects(name) VALUES ('Matematica')").lastrowid
        for shift in ('manha','tarde'):
            self.db.execute('INSERT INTO availability(teacher_id,day,shift) VALUES (?,0,?)',(self.teacher,shift))
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def test_new_morning_class_blocks_afternoon(self):
        cid=self.handler.post(self.db,'/api/classes',{'name':'Primeiro A','shift':'manha'})['id']
        self.assertEqual(server.load_state(self.db)['classes'][0]['shift'],'manha')
        data={'teacher_id':self.teacher,'class_id':cid,'subject_id':self.subject,'day':0,'slot_id':'T1'}
        with self.assertRaisesRegex(ValueError,'não funciona neste turno'):
            server.create_entry(self.db,data)
        data['slot_id']='M1'
        server.create_entry(self.db,data)
        with self.assertRaisesRegex(ValueError,'Remaneje'):
            self.handler.post(self.db,'/api/classes/update',{'id':cid,'name':'Primeiro A','shift':'tarde'})
    def test_legacy_class_integral_default(self):
        cid=self.db.execute("INSERT INTO classes(name) VALUES ('Legado')").lastrowid
        self.assertEqual(server.scalar(self.db,'SELECT shift FROM classes WHERE id=?',(cid,)),'integral')
    def test_generator_only_allowed_shift(self):
        cid=self.handler.post(self.db,'/api/classes',{'name':'Noite','shift':'tarde'})['id']
        self.handler.post(self.db,'/api/requirements',{'teacher_id':self.teacher,'class_id':cid,'subject_id':self.subject,'lessons':2})
        proposal=server.build_proposal(self.db)
        self.assertEqual(len(proposal['proposed']),2)
        self.assertTrue(all(server.SLOT_MAP[p['slot_id']]['shift']=='tarde' for p in proposal['proposed']))
if __name__=='__main__':unittest.main()
