#!/usr/bin/env python3
"""Gestor de Horários: API HTTP e SQLite, usando apenas a biblioteca padrão do Python."""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_FILE = Path(os.getenv('HORARIOS_DB', str(ROOT / 'horarios.sqlite3')))
HOST = os.getenv('HORARIOS_HOST', '127.0.0.1')
PORT = int(os.getenv('HORARIOS_PORT', '8000'))
WRITE_LOCK = threading.RLock()
DAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta']
SLOTS = [
    {'id': f'M{i+1}', 'shift':'manha', 'start':start, 'end':end, 'label':f'{i+1}ª aula'}
    for i,(start,end) in enumerate([('07:00','07:50'),('07:50','08:40'),('08:40','09:30'),('10:00','10:50'),('10:50','11:40'),('11:40','12:30'),('12:30','13:20')])
] + [
    {'id': f'T{i+1}', 'shift':'tarde', 'start':start, 'end':end, 'label':f'{i+1}ª aula'}
    for i,(start,end) in enumerate([('13:40','14:30'),('14:30','15:20'),('15:20','16:10'),('16:40','17:30'),('17:30','18:20'),('18:20','19:10'),('19:10','20:00')])
]
SLOT_MAP = {s['id']:s for s in SLOTS}
DEFAULT_SLOTS = [dict(s) for s in SLOTS]
BREAKS = [('09:30', '10:00'), ('16:10', '16:40')]

def minutes(t):
    return int(t[:2])*60 + int(t[3:])

def length(slot):
    return minutes(slot['end']) - minutes(slot['start'])

def overlaps(a, b):
    return minutes(a['start']) < minutes(b['end']) and minutes(b['start']) < minutes(a['end'])

def refresh_slots(db):
    slots = rows(db, 'SELECT id,shift,start,end,label FROM slots ORDER BY start,end,id')
    SLOTS[:] = slots
    SLOT_MAP.clear()
    SLOT_MAP.update((s['id'],s) for s in slots)



def connect():
    db = sqlite3.connect(str(DB_FILE), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    return db


def init_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS teachers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, max_minutes INTEGER NOT NULL DEFAULT 2520 CHECK(max_minutes BETWEEN 0 AND 10080), color TEXT NOT NULL DEFAULT '#2878A8');
        CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, course TEXT NOT NULL DEFAULT '', campus TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS availability(teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE, day INTEGER NOT NULL CHECK(day BETWEEN 0 AND 4), shift TEXT NOT NULL CHECK(shift IN ('manha','tarde')), PRIMARY KEY(teacher_id,day,shift));
        CREATE TABLE IF NOT EXISTS workload(id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE, description TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes >= 0));
        CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL, day INTEGER NOT NULL CHECK(day BETWEEN 0 AND 4), slot_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(teacher_id,day,slot_id), UNIQUE(class_id,day,slot_id));
        CREATE UNIQUE INDEX IF NOT EXISTS unique_room_slot ON entries(room_id,day,slot_id) WHERE room_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS requirements(id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL, lessons INTEGER NOT NULL CHECK(lessons BETWEEN 1 AND 35));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS slots(id TEXT PRIMARY KEY, shift TEXT NOT NULL CHECK(shift IN ('manha','tarde')), start TEXT NOT NULL, end TEXT NOT NULL, label TEXT NOT NULL);

        ''')
        db.executemany('INSERT OR IGNORE INTO slots(id,shift,start,end,label) VALUES (:id,:shift,:start,:end,:label)', DEFAULT_SLOTS)
        columns={row['name'] for row in db.execute('PRAGMA table_info(classes)')}
        if 'shift' not in columns:
            db.execute("ALTER TABLE classes ADD COLUMN shift TEXT NOT NULL DEFAULT 'integral'")
        refresh_slots(db)


def rows(db, sql, params=()):
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def scalar(db, sql, params=()):
    r = db.execute(sql, params).fetchone()
    return r[0] if r else None


def valid_id(db, table, idval):
    try: n = int(idval)
    except (TypeError, ValueError): raise ValueError(f'Identificador inválido: {table}')
    if scalar(db, f'SELECT id FROM {table} WHERE id=?', (n,)) is None:
        raise ValueError(f'Registro não encontrado: {table} #{n}')
    return n


def load_state(db):
    return {
        'teachers': rows(db, 'SELECT * FROM teachers ORDER BY name COLLATE NOCASE'),
        'classes': rows(db, 'SELECT * FROM classes ORDER BY name COLLATE NOCASE'),
        'subjects': rows(db, 'SELECT * FROM subjects ORDER BY name COLLATE NOCASE'),
        'rooms': rows(db, 'SELECT * FROM rooms ORDER BY name COLLATE NOCASE'),
        'availability': rows(db, 'SELECT * FROM availability ORDER BY teacher_id,day,shift'),
        'workload': rows(db, 'SELECT * FROM workload ORDER BY teacher_id,id'),
        'entries': rows(db, '''SELECT e.*, t.name teacher_name,t.color teacher_color,c.name class_name,c.course,c.campus,s.name subject_name,COALESCE(r.name,'—') room_name
                                  FROM entries e JOIN teachers t ON t.id=e.teacher_id JOIN classes c ON c.id=e.class_id JOIN subjects s ON s.id=e.subject_id LEFT JOIN rooms r ON r.id=e.room_id ORDER BY e.day,e.slot_id,e.id'''),
        'requirements': rows(db, 'SELECT r.*,t.name teacher_name,c.name class_name,s.name subject_name FROM requirements r JOIN teachers t ON t.id=r.teacher_id JOIN classes c ON c.id=r.class_id JOIN subjects s ON s.id=r.subject_id ORDER BY r.id'),
        'slots': SLOTS, 'days': DAYS
    }


def is_available(db, teacher, day, shift):
    return bool(scalar(db, 'SELECT 1 FROM availability WHERE teacher_id=? AND day=? AND shift=?', (teacher,day,shift)))


def class_allows_shift(db, class_id, shift):
    allowed=scalar(db,'SELECT shift FROM classes WHERE id=?',(class_id,))
    return allowed == 'integral' or allowed == shift


def check_entry(db, data, ignored_id=None, extra=None):
    try:
        teacher = valid_id(db, 'teachers', data.get('teacher_id'))
        cls = valid_id(db, 'classes', data.get('class_id'))
        subject = valid_id(db, 'subjects', data.get('subject_id'))
        room = valid_id(db, 'rooms',data.get('room_id')) if data.get('room_id') not in ('',None) else None
        day = int(data.get('day'))
        slot_id = str(data.get('slot_id',''))
    except (TypeError, ValueError) as ex:
        raise ValueError(str(ex))
    if day not in range(5) or slot_id not in SLOT_MAP:
        raise ValueError('Dia ou horário inválido.')
    slot = SLOT_MAP[slot_id]
    if not class_allows_shift(db,cls,slot['shift']):
        raise ValueError('A turma não funciona neste turno. Edite o turno no cadastro da turma.')
    if not is_available(db,teacher,day,slot['shift']):
        raise ValueError('Professor indisponível neste dia e turno.')
    existing = rows(db, 'SELECT * FROM entries WHERE day=? AND id!=?',(day,ignored_id or -1))
    existing += extra or []
    for e in existing:
        oldslot = SLOT_MAP.get(e['slot_id'])
        if not oldslot or not overlaps(slot, oldslot):
            continue
        if e['teacher_id']==teacher: raise ValueError('Choque: professor já possui aula neste horário.')
        if e['class_id']==cls: raise ValueError('Choque: turma já possui aula neste horário.')
        if room is not None and e['room_id']==room: raise ValueError('Choque: sala ocupada neste horário.')
    used = sum(length(SLOT_MAP[e['slot_id']]) for e in rows(db, 'SELECT slot_id FROM entries WHERE teacher_id=? AND id!=?',(teacher,ignored_id or -1)))
    other = scalar(db, 'SELECT COALESCE(SUM(minutes),0) FROM workload WHERE teacher_id=?',(teacher,)) or 0
    used += sum(length(SLOT_MAP[e['slot_id']]) for e in (extra or []) if e['teacher_id']==teacher)
    limit = scalar(db, 'SELECT max_minutes FROM teachers WHERE id=?',(teacher,))
    if used + other + length(slot) > limit:
        raise ValueError(f'Limite de carga horária excedido: {(used+other+length(slot))/60:.2f}h > {limit/60:.2f}h.')
    return {'teacher_id':teacher,'class_id':cls,'subject_id':subject,'room_id':room,'day':day,'slot_id':slot_id}


def log(db, action, detail):
    db.execute('INSERT INTO audit(action,detail) VALUES (?,?)',(action,detail))


def create_entry(db, data, extra=None):
    x = check_entry(db,data,extra=extra)
    cur = db.execute('INSERT INTO entries(teacher_id,class_id,subject_id,room_id,day,slot_id) VALUES(:teacher_id,:class_id,:subject_id,:room_id,:day,:slot_id)',x)
    log(db,'entry.created',str(cur.lastrowid))
    return cur.lastrowid


def build_proposal(db):
    requirements=rows(db,'SELECT * FROM requirements ORDER BY id')
    if not requirements: raise ValueError('Cadastre demandas de aulas para utilizar a geração automática.')
    scheduled=rows(db,'SELECT * FROM entries')
    pending=[]
    for req in requirements:
        already=sum(1 for e in scheduled if e['teacher_id']==req['teacher_id'] and e['class_id']==req['class_id'] and e['subject_id']==req['subject_id'])
        remaining=max(0,req['lessons']-already)
        pending.extend([req]*remaining)
    if not pending: return {'proposed':[],'missing':[],'message':'Todas as demandas já foram atendidas.'}
    load = {t['id']: (scalar(db,'SELECT COALESCE(SUM(minutes),0) FROM workload WHERE teacher_id=?',(t['id'],)) or 0) + sum(length(SLOT_MAP[e['slot_id']]) for e in scheduled if e['teacher_id']==t['id']) for t in rows(db,'SELECT id FROM teachers')}
    limits={t['id']:t['max_minutes'] for t in rows(db,'SELECT * FROM teachers')}
    available={(a['teacher_id'],a['day'],a['shift']) for a in rows(db,'SELECT * FROM availability')}
    class_shifts={c['id']:c['shift'] for c in rows(db,'SELECT id,shift FROM classes')}
    allentries=list(scheduled)
    proposed=[]
    missing=[]
    # Maior restrição primeiro; escolha gulosa determinística (não garante solução ótima).
    pending.sort(key=lambda r:(sum((r['teacher_id'],d,s['shift']) in available for d in range(5) for s in SLOTS), -r['lessons'],r['id']))
    for req in pending:
        candidates=[]
        for day in range(5):
            for slot in SLOTS:
                if class_shifts.get(req['class_id']) not in ('integral',slot['shift']): continue
                if (req['teacher_id'],day,slot['shift']) not in available: continue
                if load[req['teacher_id']]+length(slot)>limits[req['teacher_id']]: continue
                occupied=any(e['day']==day and overlaps(slot,SLOT_MAP[e['slot_id']]) and (e['teacher_id']==req['teacher_id'] or e['class_id']==req['class_id'] or (req['room_id'] is not None and e['room_id']==req['room_id'])) for e in allentries)
                if occupied: continue
                same_day=sum(e['teacher_id']==req['teacher_id'] and e['day']==day for e in allentries)
                same_subject_day=sum(e['teacher_id']==req['teacher_id'] and e['class_id']==req['class_id'] and e['subject_id']==req['subject_id'] and e['day']==day for e in allentries)
                # Evita excesso da mesma matéria em um dia; favorece blocos já utilizados.
                penalty=(same_subject_day*12, 0 if same_day else 1, day, minutes(slot['start']),0 if slot['shift']=='manha' else 1)
                candidates.append((penalty,day,slot['id']))
        if not candidates:
            missing.append({'requirement_id':req['id'],'teacher_id':req['teacher_id'],'class_id':req['class_id'],'subject_id':req['subject_id'],'reason':'Sem horário compatível com disponibilidade, sala, turma e carga horária.'})
            continue
        _, day, slot_id=min(candidates)
        e={'teacher_id':req['teacher_id'],'class_id':req['class_id'],'subject_id':req['subject_id'],'room_id':req['room_id'],'day':day,'slot_id':slot_id}
        allentries.append(e); proposed.append(e); load[req['teacher_id']]+=length(SLOT_MAP[slot_id])
    return {'proposed':proposed,'missing':missing,'message':f'{len(proposed)} aula(s) proposta(s); {len(missing)} pendência(s).'}


class Handler(BaseHTTPRequestHandler):
    server_version='GestorHorarios/1.0'
    def log_message(self,fmt,*args): print('%s - %s'%(self.address_string(),fmt%args))
    def send(self,obj,status=200):
        body=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def fail(self,ex): self.send({'error':str(ex)},400 if isinstance(ex,(ValueError,sqlite3.IntegrityError)) else 500)
    def body(self):
        length=int(self.headers.get('Content-Length',0))
        if length>1024*1024: raise ValueError('Requisição muito grande.')
        obj=json.loads(self.rfile.read(length) or b'{}')
        if not isinstance(obj,dict): raise ValueError('Formato JSON inválido.')
        return obj
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/state':
            with connect() as db: self.send(load_state(db))
            return
        if path=='/api/export.csv':
            with connect() as db: state=load_state(db)
            out=io.StringIO();writer=csv.writer(out,delimiter=';')
            writer.writerow(['Dia','Horário','Professor','Turma','Curso','Unidade','Disciplina','Sala'])
            for e in state['entries']:
                slot=SLOT_MAP[e['slot_id']]
                writer.writerow([DAYS[e['day']],slot['start']+'-'+slot['end'],e['teacher_name'],e['class_name'],e['course'],e['campus'],e['subject_name'],e['room_name']])
            content=b'\xef\xbb\xbf'+out.getvalue().encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="grade_docente.csv"');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
            return
        if path=='/api/health': self.send({'ok':True});return
        if path=='/': path='/index.html'
        allowed={'/index.html':'text/html; charset=utf-8','/styles.css':'text/css; charset=utf-8','/app.js':'application/javascript; charset=utf-8'}
        if path not in allowed: self.send_error(404);return
        content=(ROOT/'static'/path.lstrip('/')).read_bytes()
        self.send_response(200);self.send_header('Content-Type',allowed[path]);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            data=self.body()
            with WRITE_LOCK, connect() as db:
                db.execute('BEGIN IMMEDIATE')
                result=self.post(db,path,data)
                db.commit()
            self.send(result)
        except Exception as ex: self.fail(ex)
    def do_DELETE(self):
        path=urlparse(self.path).path
        try:
            parts=path.split('/')
            table={'teachers':'teachers','classes':'classes','subjects':'subjects','rooms':'rooms','entries':'entries','slots':'slots','workload':'workload','requirements':'requirements'}.get(parts[2] if len(parts)>2 else '')
            if len(parts)!=4 or parts[1]!='api' or not table: raise ValueError('Rota inválida.')
            with WRITE_LOCK,connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if table == 'slots':
                    idval = parts[3]
                    if idval not in SLOT_MAP: raise ValueError('Período não encontrado.')
                    if not idval.startswith('X'): raise ValueError('Os períodos padrão não podem ser excluídos; use Editar.')
                    if scalar(db, 'SELECT 1 FROM entries WHERE slot_id=? LIMIT 1',(idval,)):
                        raise ValueError('Este período possui aulas. Remaneje-as antes de excluir.')
                    db.execute('DELETE FROM slots WHERE id=?',(idval,))
                    refresh_slots(db)
                else:
                    idval=valid_id(db,table,parts[3])
                    db.execute(f'DELETE FROM {table} WHERE id=?',(idval,))
                log(db,table+'.deleted',str(idval));db.commit()
            self.send({'ok':True})
        except Exception as ex: self.fail(ex)
    def post(self,db,path,d):
        if path=='/api/teachers':
            name=str(d.get('name','')).strip(); color=str(d.get('color') or '#2878A8')
            if not name: raise ValueError('Informe o nome do professor.')
            if len(name)>160: raise ValueError('Nome do professor muito longo.')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): raise ValueError('Cor inválida.')
            if scalar(db,'SELECT 1 FROM teachers WHERE lower(trim(name))=lower(?)',(name,)): raise ValueError('Já existe um professor com esse nome.')
            max_minutes=int(d.get('max_minutes',2520))
            if not (0<=max_minutes<=10080): raise ValueError('Limite inválido.')
            cur=db.execute('INSERT INTO teachers(name,max_minutes,color) VALUES(?,?,?)',(name,max_minutes,color))
            return {'id':cur.lastrowid}
        if path in ('/api/slots','/api/slots/update'):
            updating=path.endswith('/update')
            slot_to_edit=str(d.get('id','')) if updating else None
            if updating:
                if slot_to_edit not in SLOT_MAP: raise ValueError('Período não encontrado.')
                if scalar(db,'SELECT 1 FROM entries WHERE slot_id=? LIMIT 1',(slot_to_edit,)):
                    raise ValueError('Não é possível editar um período que possui aulas. Remaneje as aulas antes.')
            start=str(d.get('start','')).strip()
            end=str(d.get('end','')).strip()
            shift=str(d.get('shift','')).strip()
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end):
                raise ValueError('Informe início e término no formato HH:MM.')
            if shift not in ('manha','tarde'):
                raise ValueError('Turno inválido.')
            start_min,end_min=minutes(start),minutes(end)
            if not 15<=end_min-start_min<=180:
                raise ValueError('O período deve durar entre 15 e 180 minutos.')
            lower,upper=(360,800) if shift=='manha' else (820,1350)
            if start_min<lower or end_min>upper:
                raise ValueError('Período fora dos limites do turno selecionado.')
            candidate={'start':start,'end':end}
            if any(overlaps(candidate,{'start':a,'end':b}) for a,b in BREAKS):
                raise ValueError('O período invade um intervalo obrigatório.')
            if any(overlaps(candidate,s) for s in SLOTS if s['id']!=slot_to_edit):
                raise ValueError('O período se sobrepõe a outro horário já cadastrado.')
            label=str(d.get('label','')).strip() or 'Período adicional'
            if len(label)>90: raise ValueError('Descrição do período muito longa.')
            if updating:
                db.execute('UPDATE slots SET shift=?,start=?,end=?,label=? WHERE id=?',(shift,start,end,label,slot_to_edit))
                slot_id=slot_to_edit
            else:
                idx=1
                while 'X'+str(idx) in SLOT_MAP: idx+=1
                slot_id='X'+str(idx)
                db.execute('INSERT INTO slots(id,shift,start,end,label) VALUES(?,?,?,?,?)',(slot_id,shift,start,end,label))
            refresh_slots(db)
            log(db,'slots.updated' if updating else 'slots.created',slot_id)
            return {'id':slot_id}
        if path in ('/api/classes','/api/classes/update'):
            name=str(d.get('name','')).strip()
            if not name: raise ValueError('Informe a turma.')
            shift=str(d.get('shift','integral')).strip()
            if shift not in ('manha','tarde','integral'):
                raise ValueError('Turno da turma inválido.')
            course=str(d.get('course','')).strip()
            campus=str(d.get('campus','')).strip()
            if path.endswith('/update'):
                cid=valid_id(db,'classes',d.get('id'))
                for e in rows(db,'SELECT slot_id FROM entries WHERE class_id=?',(cid,)):
                    if shift!='integral' and SLOT_MAP[e['slot_id']]['shift']!=shift:
                        raise ValueError('A turma já possui aulas em outro turno. Remaneje-as antes de alterar.')
                db.execute('UPDATE classes SET name=?,course=?,campus=?,shift=? WHERE id=?',(name,course,campus,shift,cid))
                log(db,'classes.updated',str(cid))
                return {'id':cid}
            cur=db.execute('INSERT INTO classes(name,course,campus,shift) VALUES(?,?,?,?)',(name,course,campus,shift))
            return {'id':cur.lastrowid}
        if path in ('/api/subjects','/api/rooms'):
            name=str(d.get('name','')).strip()
            if not name: raise ValueError('Informe o nome.')
            table='subjects' if path.endswith('subjects') else 'rooms'
            cur=db.execute(f'INSERT INTO {table}(name) VALUES(?)',(name,));return {'id':cur.lastrowid}
        if path=='/api/availability':
            teacher=valid_id(db,'teachers',d.get('teacher_id'))
            cells=d.get('cells',[])
            if not isinstance(cells,list): raise ValueError('Disponibilidade inválida.')
            prepared=[]
            for cell in cells:
                day=int(cell['day']);shift=cell['shift']
                if day not in range(5) or shift not in ('manha','tarde'): raise ValueError('Dia ou turno inválido.')
                prepared.append((teacher,day,shift))
            # Retirar disponibilidade não pode invalidar aulas já registradas.
            for e in rows(db,'SELECT day,slot_id FROM entries WHERE teacher_id=?',(teacher,)):
                if (teacher,e['day'],SLOT_MAP[e['slot_id']]['shift']) not in prepared:
                    raise ValueError('Não é possível retirar a disponibilidade de um período que possui aulas. Remova ou remaneje essas aulas antes.')
            db.execute('DELETE FROM availability WHERE teacher_id=?',(teacher,))
            db.executemany('INSERT OR IGNORE INTO availability(teacher_id,day,shift) VALUES (?,?,?)',prepared)
            return {'ok':True}
        if path=='/api/workload':
            teacher=valid_id(db,'teachers',d.get('teacher_id'))
            desc=str(d.get('description','')).strip();activity_minutes=int(d.get('minutes',0))
            if not desc or activity_minutes<=0: raise ValueError('Informe a atividade e sua duração em minutos.')
            used=sum(length(SLOT_MAP[e['slot_id']]) for e in rows(db,'SELECT slot_id FROM entries WHERE teacher_id=?',(teacher,)))+(scalar(db,'SELECT COALESCE(SUM(minutes),0) FROM workload WHERE teacher_id=?',(teacher,)) or 0)
            limit=scalar(db,'SELECT max_minutes FROM teachers WHERE id=?',(teacher,))
            if used+activity_minutes>limit: raise ValueError('Atividade ultrapassaria o limite semanal do professor.')
            cur=db.execute('INSERT INTO workload(teacher_id,description,minutes) VALUES(?,?,?)',(teacher,desc,activity_minutes));return {'id':cur.lastrowid}
        if path=='/api/entries': return {'id':create_entry(db,d)}
        if path=='/api/requirements':
            teacher=valid_id(db,'teachers',d.get('teacher_id'));cls=valid_id(db,'classes',d.get('class_id'));subj=valid_id(db,'subjects',d.get('subject_id'))
            room=valid_id(db,'rooms',d['room_id']) if d.get('room_id') not in (None,'') else None
            lessons=int(d.get('lessons',0))
            if not 1<=lessons<=35:raise ValueError('Informe de 1 a 35 aulas semanais.')
            if scalar(db,'SELECT 1 FROM requirements WHERE teacher_id=? AND class_id=? AND subject_id=?',(teacher,cls,subj)):
                raise ValueError('Essa demanda já está cadastrada para o mesmo professor, turma e disciplina.')
            already=scalar(db,'SELECT COALESCE(SUM(lessons),0) FROM requirements WHERE class_id=?',(cls,)) or 0
            limit_slots=sum(s['shift']==(scalar(db,'SELECT shift FROM classes WHERE id=?',(cls,))) or scalar(db,'SELECT shift FROM classes WHERE id=?',(cls,))=='integral' for s in SLOTS)*5
            if already+lessons>limit_slots:raise ValueError('As demandas desta turma ultrapassariam os períodos semanais disponíveis.')
            cur=db.execute('INSERT INTO requirements(teacher_id,class_id,subject_id,room_id,lessons) VALUES(?,?,?,?,?)',(teacher,cls,subj,room,lessons));return {'id':cur.lastrowid}
        if path=='/api/proposal': return build_proposal(db)
        if path=='/api/proposal/apply':
            proposed=d.get('proposed')
            if not isinstance(proposed,list) or len(proposed)>350: raise ValueError('Proposta inválida.')
            ids=[]
            for item in proposed:ids.append(create_entry(db,item))
            return {'ok':True,'created':len(ids)}
        if path=='/api/demo':
            if scalar(db,'SELECT COUNT(*) FROM teachers') or scalar(db,'SELECT COUNT(*) FROM entries'):
                raise ValueError('Dados de exemplo só podem ser inseridos em uma base vazia.')
            ts=[]
            for name,color in [('Ana Beatriz','#9061D1'),('Carlos Almeida','#2878A8'),('Marina Souza','#D97752')]:
                ts.append(db.execute('INSERT INTO teachers(name,color) VALUES(?,?)',(name,color)).lastrowid)
            cs=[]
            for name in ['DS 1º A','DS 2º A','DS 3º A']:
                cs.append(db.execute('INSERT INTO classes(name,course,campus) VALUES(?,?,?)',(name,'Desenvolvimento de Sistemas','Paulista')).lastrowid)
            ss=[]
            for name in ['Programação','Banco de Dados','Redes de Computadores']:
                ss.append(db.execute('INSERT INTO subjects(name) VALUES(?)',(name,)).lastrowid)
            rr=db.execute('INSERT INTO rooms(name) VALUES(?)',('Laboratório 01',)).lastrowid
            for t in ts:
                db.executemany('INSERT INTO availability(teacher_id,day,shift) VALUES (?,?,?)',[(t,day,shift) for day in range(5) for shift in ('manha','tarde')])
            for t,c,s,day,slot in [(ts[0],cs[0],ss[0],0,'M1'),(ts[0],cs[0],ss[0],0,'M2'),(ts[1],cs[1],ss[1],1,'T1'),(ts[1],cs[1],ss[1],1,'T2'),(ts[2],cs[2],ss[2],2,'M3')]:
                create_entry(db,{'teacher_id':t,'class_id':c,'subject_id':s,'room_id':rr,'day':day,'slot_id':slot})
            return {'ok':True}
        raise ValueError('Rota inválida.')


if __name__=='__main__':
    init_db()
    print(f'\nGESTOR DE HORÁRIOS — http://{HOST}:{PORT}\nBanco: {DB_FILE}\nPara encerrar: Ctrl+C\n')
    try: ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
    except KeyboardInterrupt: print('\nServidor encerrado.')
