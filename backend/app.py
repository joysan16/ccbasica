from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import sqlite3, json, os

app = Flask(__name__,
  template_folder='../frontend/templates',
  static_folder='../frontend/static')
app.secret_key = 'careercompass-dev-key'
CORS(app)

BASE   = os.path.dirname(__file__)
DB     = os.path.join(BASE, '../data/careercompass.db')
DATA   = os.path.join(BASE, '../data')

# ── DB INIT ──────────────────────────────────────
def init_db():
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('''CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, year TEXT, company TEXT,
    days INTEGER, hours INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
  c.execute('''CREATE TABLE IF NOT EXISTS user_subjects(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, subject TEXT, level TEXT)''')
  c.execute('''CREATE TABLE IF NOT EXISTS topic_progress(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, topic_id TEXT, subject TEXT,
    status TEXT DEFAULT "not_started", score INTEGER DEFAULT 0,
    completed_at TIMESTAMP)''')
  c.execute('''CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, date TEXT, xp_earned INTEGER DEFAULT 0)''')
  conn.commit(); conn.close()
  print("✅ DB ready")

# ── PAGES ────────────────────────────────────────
@app.route('/')           
def index():      return render_template('index.html')
@app.route('/signup')     
def signup():     return render_template('signup.html')
@app.route('/company')    
def company():    return render_template('company.html')
@app.route('/subjects')   
def subjects():   return render_template('subjects.html')
@app.route('/days')       
def days():       return render_template('days.html')
@app.route('/dashboard')  
def dashboard():  return render_template('dashboard.html')
@app.route('/learn')      
def learn():      return render_template('learn.html')
@app.route('/practice')   
def practice():   return render_template('practice.html')
@app.route('/mock')       
def mock():       return render_template('mock.html')

# ── API: SAVE ONBOARDING ─────────────────────────
@app.route('/api/setup', methods=['POST'])
def save_setup():
  d = request.json
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('INSERT INTO users(name,year,company,days,hours) VALUES(?,?,?,?,?)',
    (d['name'], d['year'], d['company'], d['days'], d['hours']))
  uid = c.lastrowid
  for sub in d['subjects']:
    c.execute('INSERT INTO user_subjects(user_id,subject,level) VALUES(?,?,?)',
      (uid, sub['name'], sub['level']))
  conn.commit(); conn.close()
  session['user_id'] = uid
  return jsonify({'success':True, 'user_id':uid})

# ── API: GET DASHBOARD DATA ───────────────────────
@app.route('/api/dashboard/<int:uid>')
def get_dashboard(uid):
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('SELECT * FROM users WHERE id=?',(uid,))
  u = c.fetchone()
  if not u: return jsonify({'error':'User not found'}),404
  c.execute('SELECT subject,level FROM user_subjects WHERE user_id=?',(uid,))
  subs = c.fetchall()
  c.execute('SELECT subject,COUNT(*) t,SUM(CASE WHEN status="completed" THEN 1 ELSE 0 END) d FROM topic_progress WHERE user_id=? GROUP BY subject',(uid,))
  prog = c.fetchall()
  c.execute('SELECT SUM(xp_earned) FROM sessions WHERE user_id=?',(uid,))
  xp_row = c.fetchone()
  c.execute('SELECT COUNT(DISTINCT date) FROM sessions WHERE user_id=?',(uid,))
  streak = c.fetchone()[0]
  conn.close()

  level_score = {'Beginner':20,'Intermediate':50,'Expert':75}
  scores = [level_score.get(s[1],20) for s in subs]
  readiness = round(sum(scores)/len(scores)) if scores else 0

  return jsonify({
    'user':{'name':u[1],'year':u[2],'company':u[3],'days':u[4],'hours':u[5]},
    'subjects':[{'name':s[0],'level':s[1]} for s in subs],
    'readiness':readiness,
    'xp':xp_row[0] or 0,
    'streak':streak,
    'progress':[{'subject':p[0],'total':p[1],'done':p[2]} for p in prog]
  })

# ── API: TOPICS ───────────────────────────────────
@app.route('/api/topics')
def get_topics():
  path = os.path.join(DATA,'hcl_syllabus.json')
  if os.path.exists(path):
    with open(path) as f: return jsonify(json.load(f))
  return jsonify({'error':'Syllabus not found'}),404

# ── API: CONCEPTS ─────────────────────────────────
@app.route('/api/concepts/<subject_id>')
def get_concepts(subject_id):
  path = os.path.join(DATA,f'concepts/{subject_id}.json')
  if os.path.exists(path):
    with open(path) as f: return jsonify(json.load(f))
  return jsonify({'error':'Not found'}),404

# ── API: QUESTIONS ────────────────────────────────
@app.route('/api/questions/<topic_id>')
def get_questions(topic_id):
  path = os.path.join(DATA,'questions/mcq_bank.json')
  if os.path.exists(path):
    with open(path) as f:
      bank = json.load(f)
      return jsonify(bank.get(topic_id, []))
  return jsonify([])

# ── API: SAVE PROGRESS ────────────────────────────
@app.route('/api/progress', methods=['POST'])
def save_progress():
  d = request.json
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('''INSERT OR REPLACE INTO topic_progress(user_id,topic_id,subject,status,score)
    VALUES(?,?,?,?,?)''',
    (d['user_id'],d['topic_id'],d['subject'],d['status'],d.get('score',0)))
  if d.get('xp',0)>0:
    from datetime import date
    c.execute('INSERT INTO sessions(user_id,date,xp_earned) VALUES(?,?,?)',
      (d['user_id'],date.today().isoformat(),d['xp']))
  conn.commit(); conn.close()
  return jsonify({'success':True})

if __name__ == '__main__':
  os.makedirs(os.path.join(BASE,'../data'), exist_ok=True)
  init_db()
  app.run(debug=True, port=5000)
