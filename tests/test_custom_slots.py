import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class CustomSlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        server.DB_FILE=Path(self.tmp.name)/'db.sqlite3'
        server.init_db()
        self.db=server.connect()
        self.teacher=self.db.execute('INSERT INTO teachers(name,max_minutes) VALUES (?,?)',('Docente',2520)).lastrowid
        self.cls=self.db.execute('INSERT INTO classes(name) VALUES (?)',('Turma 4',)).lastrowid
        self.sub=self.db.execute('INSERT INTO subjects(name) VALUES (?)',('Matemática',)).lastrowid
        self.db.execute("INSERT INTO availability(teacher_id,day,shift) VALUES (?,0,'tarde')",(self.teacher,))
        self.handler=object.__new__(server.Handler)
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def test_register_and_use_night_period(self):
        out=self.handler.post(self.db,'/api/slots',{'shift':'tarde','start':'20:00','end':'21:30','label':'Reposição'})
        self.assertEqual(server.SLOT_MAP[out['id']]['label'],'Reposição')
        server.create_entry(self.db,{'teacher_id':self.teacher,'class_id':self.cls,'subject_id':self.sub,'day':0,'slot_id':out['id']})
        self.assertEqual(server.load_state(self.db)['entries'][0]['slot_id'],out['id'])
        self.assertEqual(server.length(server.SLOT_MAP[out['id']]),90)
        with self.assertRaisesRegex(ValueError,'possui aulas'):
            self.handler.post(self.db,'/api/slots/update',{'id':out['id'],'shift':'tarde','start':'20:00','end':'21:00'})
    def test_prevent_overlapping_or_break(self):
        for st,en in [('19:30','20:30'),('16:05','16:45')]:
            with self.assertRaisesRegex(ValueError,'sobrepõe|intervalo'):
                self.handler.post(self.db,'/api/slots',{'shift':'tarde','start':st,'end':en})
    def test_edit_unused_standard_period(self):
        result=self.handler.post(self.db,'/api/slots/update',{'id':'T7','shift':'tarde','start':'19:10','end':'19:55','label':'Sétima aula'})
        self.assertEqual(result['id'],'T7')
        self.assertEqual(server.SLOT_MAP['T7']['end'],'19:55')
        out=self.handler.post(self.db,'/api/slots',{'shift':'tarde','start':'19:55','end':'20:45','label':'Oitava'})
        self.assertTrue(out['id'].startswith('X'))
    def test_preexisting_database_migration(self):
        self.assertEqual(len(server.load_state(self.db)['slots']),14)
        self.assertEqual(server.SLOT_MAP['M7']['end'],'13:20')

if __name__=='__main__': unittest.main()
