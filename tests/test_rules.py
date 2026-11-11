import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        server.DB_FILE=Path(self.tmp.name)/'test.sqlite3'
        server.init_db()
        self.db=server.connect()
        self.t1=self.db.execute("INSERT INTO teachers(name,max_minutes) VALUES ('Prof A',100)").lastrowid
        self.t2=self.db.execute("INSERT INTO teachers(name,max_minutes) VALUES ('Prof B',2520)").lastrowid
        self.c1=self.db.execute("INSERT INTO classes(name) VALUES ('Turma A')").lastrowid
        self.c2=self.db.execute("INSERT INTO classes(name) VALUES ('Turma B')").lastrowid
        self.s=self.db.execute("INSERT INTO subjects(name) VALUES ('Programação')").lastrowid
        self.r=self.db.execute("INSERT INTO rooms(name) VALUES ('Sala 01')").lastrowid
        for t in (self.t1,self.t2):
            for day in range(5):
                for shift in ('manha','tarde'):
                    self.db.execute('INSERT INTO availability VALUES(?,?,?)',(t,day,shift))
        self.base=dict(teacher_id=self.t1,class_id=self.c1,subject_id=self.s,room_id=self.r,day=0,slot_id='M1')
    def tearDown(self): self.db.close();self.tmp.cleanup()
    def test_conflict_teacher(self):
        server.create_entry(self.db,self.base)
        with self.assertRaisesRegex(ValueError,'professor'):
            server.create_entry(self.db,{**self.base,'class_id':self.c2,'room_id':None})
    def test_conflict_class(self):
        server.create_entry(self.db,self.base)
        with self.assertRaisesRegex(ValueError,'turma'):
            server.create_entry(self.db,{**self.base,'teacher_id':self.t2,'room_id':None})
    def test_conflict_room(self):
        server.create_entry(self.db,self.base)
        with self.assertRaisesRegex(ValueError,'sala'):
            server.create_entry(self.db,{**self.base,'teacher_id':self.t2,'class_id':self.c2})
    def test_limit(self):
        server.create_entry(self.db,self.base)
        server.create_entry(self.db,{**self.base,'slot_id':'M2'})
        with self.assertRaisesRegex(ValueError,'Limite'):
            server.create_entry(self.db,{**self.base,'slot_id':'M3'})
    def test_no_availability(self):
        self.db.execute("DELETE FROM availability WHERE teacher_id=? AND day=0 AND shift='manha'",(self.t1,))
        with self.assertRaisesRegex(ValueError,'indisponível'):
            server.create_entry(self.db,self.base)
    def test_schedule_morning_and_afternoon(self):
        self.assertEqual(server.SLOT_MAP['M7']['end'],'13:20')
        self.assertEqual(server.SLOT_MAP['T7']['end'],'20:00')
        self.assertNotIn('09:30', [x['start'] for x in server.SLOTS])
        self.assertNotIn('16:10', [x['start'] for x in server.SLOTS])
    def test_generator_respects_constraints(self):
        self.db.execute('INSERT INTO requirements(teacher_id,class_id,subject_id,room_id,lessons) VALUES(?,?,?,?,?)',(self.t1,self.c1,self.s,self.r,3))
        proposal=server.build_proposal(self.db)
        self.assertEqual(len(proposal['proposed']),2)
        self.assertEqual(len(proposal['missing']),1)
    def test_activity_counts_in_limit(self):
        self.db.execute('INSERT INTO workload(teacher_id,description,minutes) VALUES(?,?,?)',(self.t1,'Planejamento',75))
        with self.assertRaisesRegex(ValueError,'Limite'):
            server.create_entry(self.db,self.base)

if __name__=='__main__':unittest.main()
