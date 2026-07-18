from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from rag import mentor_chat, explain_concept, generate_mcqs, build_vectorstore
from manager_scenarios import get_scenario_for_topic
import sqlite3, json, os
from datetime import date, datetime, timedelta

app = Flask(__name__,
  template_folder='../frontend/templates',
  static_folder='../frontend/static')
app.secret_key = 'careercompass-dev-key'
CORS(app)

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, '../data/careercompass.db')
DATA = os.path.join(BASE, '../data')

# ── DB INIT ──────────────────────────────────────────────────────
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

# ── PAGES ────────────────────────────────────────────────────────
@app.route('/')          
def index():     return render_template('index.html')
@app.route('/signup')    
def signup():    return render_template('signup.html')
@app.route('/signin')    
def signin():    return render_template('signin.html')
@app.route('/company')   
def company():   return render_template('company.html')
@app.route('/subjects')  
def subjects():  return render_template('subjects.html')
@app.route('/days')      
def days():      return render_template('days.html')
@app.route('/dashboard') 
def dashboard(): return render_template('dashboard.html')
@app.route('/learn')     
def learn():     return render_template('learn.html')
@app.route('/practice')  
def practice():  return render_template('practice.html')
@app.route('/mock')      
def mock():      return render_template('mock.html')
@app.route('/mentor')    
def mentor():    return render_template('mentor.html')
@app.route('/manager')   
def manager():   return render_template('manager_call.html')
@app.route('/cheatsheet')
def cheatsheet(): return render_template('cheatsheet.html')

# ── API: SAVE ONBOARDING ─────────────────────────────────────────
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
  return jsonify({'success': True, 'user_id': uid})

# ── API: SIGN IN — looks up an existing user by name ─────────────
@app.route('/api/signin', methods=['POST'])
def api_signin():
  d    = request.json
  name = (d.get('name') or '').strip()
  if not name:
    return jsonify({'success': False, 'error': 'Name required'}), 400

  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('''SELECT id, name, company, year, days, hours
               FROM users WHERE LOWER(name)=LOWER(?)
               ORDER BY id DESC LIMIT 1''', (name,))
  user = c.fetchone()

  if not user:
    conn.close()
    return jsonify({'success': False, 'error': 'Name not found. Please sign up first.'})

  uid = user[0]
  c.execute('SELECT subject, level FROM user_subjects WHERE user_id=?', (uid,))
  rows = c.fetchall()
  subjects = [r[0] for r in rows]
  ratings  = {r[0]: r[1] for r in rows}
  conn.close()

  return jsonify({
    'success':  True,
    'user_id':  user[0],
    'name':     user[1],
    'company':  user[2],
    'year':     user[3],
    'days':     user[4] if user[4] else 14,
    'hours':    user[5] if user[5] else 2,
    'subjects': subjects,
    'ratings':  ratings
  })

# ── API: GET DASHBOARD DATA ──────────────────────────────────────
@app.route('/api/dashboard/<int:uid>')
def get_dashboard(uid):
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('SELECT * FROM users WHERE id=?', (uid,))
  u = c.fetchone()
  if not u:
    conn.close()
    return jsonify({'error': 'User not found'}), 404
  c.execute('SELECT subject,level FROM user_subjects WHERE user_id=?', (uid,))
  subs = c.fetchall()
  c.execute('''SELECT subject,COUNT(*) t,
    SUM(CASE WHEN status="completed" THEN 1 ELSE 0 END) d
    FROM topic_progress WHERE user_id=? GROUP BY subject''', (uid,))
  prog = c.fetchall()
  c.execute('SELECT SUM(xp_earned) FROM sessions WHERE user_id=?', (uid,))
  xp_row = c.fetchone()
  c.execute('SELECT COUNT(DISTINCT date) FROM sessions WHERE user_id=?', (uid,))
  streak = c.fetchone()[0]
  conn.close()

  level_score = {'Beginner': 20, 'Intermediate': 50, 'Expert': 75}
  scores = [level_score.get(s[1], 20) for s in subs]
  readiness = round(sum(scores) / len(scores)) if scores else 0

  return jsonify({
    'user': {'name': u[1], 'year': u[2], 'company': u[3], 'days': u[4], 'hours': u[5]},
    'subjects': [{'name': s[0], 'level': s[1]} for s in subs],
    'readiness': readiness,
    'xp': xp_row[0] or 0,
    'streak': streak,
    'progress': [{'subject': p[0], 'total': p[1], 'done': p[2]} for p in prog]
  })

# ── API: TOPICS ───────────────────────────────────────────────────
@app.route('/api/topics')
def get_topics():
  path = os.path.join(DATA, 'hcl_syllabus.json')
  if os.path.exists(path):
    with open(path) as f: return jsonify(json.load(f))
  return jsonify({'error': 'Syllabus not found'}), 404

# ── API: CONCEPTS ─────────────────────────────────────────────────
@app.route('/api/concepts/<subject_id>')
def get_concepts(subject_id):
  path = os.path.join(DATA, f'concepts/{subject_id}.json')
  if os.path.exists(path):
    with open(path) as f: return jsonify(json.load(f))
  return jsonify({'error': 'Not found'}), 404

# ── API: QUESTIONS ────────────────────────────────────────────────
@app.route('/api/questions/<topic_id>')
def get_questions(topic_id):
  path = os.path.join(DATA, 'questions/mcq_bank.json')
  if os.path.exists(path):
    with open(path) as f:
      bank = json.load(f)
      return jsonify(bank.get(topic_id, []))
  return jsonify([])

# ── API: SAVE PROGRESS ────────────────────────────────────────────
@app.route('/api/progress', methods=['POST'])
def save_progress():
  d = request.json
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('''INSERT OR REPLACE INTO topic_progress(user_id,topic_id,subject,status,score)
    VALUES(?,?,?,?,?)''',
    (d['user_id'], d['topic_id'], d['subject'], d['status'], d.get('score', 0)))
  if d.get('xp', 0) > 0:
    c.execute('INSERT INTO sessions(user_id,date,xp_earned) VALUES(?,?,?)',
      (d['user_id'], date.today().isoformat(), d['xp']))
  conn.commit(); conn.close()
  return jsonify({'success': True})

# ── API: SAVE STREAK ──────────────────────────────────────────────
@app.route('/api/streak', methods=['POST'])
def api_streak():
  d       = request.json
  user_id = d.get('user_id')
  today   = d.get('date', date.today().isoformat())
  if not user_id:
    return jsonify({'error': 'user_id required'}), 400
  conn = sqlite3.connect(DB)
  c = conn.cursor()
  c.execute('SELECT id FROM sessions WHERE user_id=? AND date=?', (user_id, today))
  if not c.fetchone():
    c.execute('INSERT INTO sessions(user_id,date,xp_earned) VALUES(?,?,?)', (user_id, today, 0))
  conn.commit()
  c.execute('SELECT DISTINCT date FROM sessions WHERE user_id=? ORDER BY date DESC', (user_id,))
  dates = [row[0] for row in c.fetchall()]
  conn.close()

  streak = 0
  check  = datetime.today().date()
  for d_str in dates:
    d_date = datetime.strptime(d_str, '%Y-%m-%d').date()
    if d_date == check:
      streak += 1
      check  -= timedelta(days=1)
    else:
      break
  return jsonify({'success': True, 'streak': streak})

# ── API: MANAGER SCENARIO ────────────────────────────────────────
@app.route('/api/manager-scenario', methods=['POST'])
def api_manager_scenario():
  d             = request.json
  user_id       = d.get('user_id', 1)
  topic         = d.get('last_topic', 'Logic Gates')
  weakest_topic = d.get('weakest_topic', 'Logic Gates')
  result = get_scenario_for_topic(topic, weakest_topic, user_id)
  return jsonify(result)

# ── API: AI MENTOR CHAT ──────────────────────────────────────────
@app.route('/api/mentor', methods=['POST'])
def api_mentor():
  try:
    d        = request.json
    question = d.get('question', '').strip()
    company  = d.get('company', 'HCL')
    if not question:
      return jsonify({'error': 'No question provided'}), 400
    result = mentor_chat(question, company)
    return jsonify(result)
  except Exception as e:
    print("❌ Mentor API error:", str(e))
    import traceback; traceback.print_exc()
    return jsonify({'answer': f'Server error: {str(e)}', 'sources': []}), 500

# ── API: EXPLAIN CONCEPT ─────────────────────────────────────────
@app.route('/api/explain', methods=['POST'])
def api_explain():
  d     = request.json
  topic = d.get('topic', '').strip()
  level = d.get('level', 'Beginner')
  if not topic:
    return jsonify({'error': 'No topic provided'}), 400
  return jsonify(explain_concept(topic, level))

# ── API: GENERATE MCQs ───────────────────────────────────────────
@app.route('/api/generate-mcqs', methods=['POST'])
def api_generate_mcqs():
  d     = request.json
  topic = d.get('topic', '').strip()
  level = d.get('level', 'basic')
  count = d.get('count', 5)
  if not topic:
    return jsonify({'error': 'No topic provided'}), 400
  return jsonify(generate_mcqs(topic, level, count))

# ── API: REBUILD VECTORSTORE ─────────────────────────────────────
@app.route('/api/rebuild-rag', methods=['POST'])
def api_rebuild_rag():
  try:
    build_vectorstore()
    return jsonify({'success': True, 'message': 'Vectorstore rebuilt'})
  except Exception as e:
    return jsonify({'error': str(e)}), 500
# Runs on import — works for BOTH local (python app.py) AND
# gunicorn on Render (which imports app, never runs __main__)
os.makedirs(os.path.join(BASE, '../data'), exist_ok=True)
os.makedirs(os.path.join(BASE, '../data/knowledge'), exist_ok=True)
init_db()

if __name__ == '__main__':
  app.run(debug=True, port=5000, use_reloader=False)