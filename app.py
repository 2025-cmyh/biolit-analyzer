# app.py (最终正确版)

from flask import Flask, request, jsonify, render_template
import sqlite3
import json
from threading import Lock
# 【重要】app 需要导入 setup_database 和 worker 里的任务函数
from data_provider import setup_database
from worker import process_job as create_background_job # 用别名导入，避免混淆

app = Flask(__name__)
DB_FILE = "journal_cache.db"
db_lock = Lock()
setup_database()
def get_query_status(query):
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM query_jobs WHERE query = ?", (query,))
        result = cursor.fetchone()
        conn.close()
    return result[0] if result else None

def get_cached_data(query, max_results):
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM articles_data WHERE query = ? LIMIT ?", (query, max_results))
        articles = [json.loads(row[0]) for row in cursor.fetchall()]
        cursor.execute("SELECT data FROM trends_data WHERE query = ?", (query,))
        trend_row = cursor.fetchone()
        trend_data = json.loads(trend_row[0]) if trend_row else {}
        conn.close()
    return {"articles": articles, "trend_analysis": trend_data}

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    try:
        max_results = int(request.args.get('max_results', 20))
        if not 5 <= max_results <= 5000:
            raise ValueError("max_results must be between 5 and 5000")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    status = get_query_status(query)

    if status == 'completed':
        print(f"✅ Cache hit for '{query}'. Serving from local DB.")
        cached_data = get_cached_data(query, max_results)
        return jsonify({"status": "completed", "data": cached_data})

    elif status in ['pending', 'processing']:
        print(f"⏳ Query '{query}' is already processing.")
        return jsonify({"status": status, "message": "We are gathering data for this query. Please check back in a moment."}), 202

    else:
        print(f"🚀 New job created for '{query}'.")
        with db_lock:
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            cursor = conn.cursor()
            # 在任务队列中也记录 max_results
            cursor.execute("CREATE TABLE IF NOT EXISTS query_jobs (query TEXT PRIMARY KEY, status TEXT NOT NULL, max_results INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cursor.execute("INSERT OR REPLACE INTO query_jobs (query, status, max_results) VALUES (?, 'pending', ?)", (query, max_results))
            conn.commit()
            conn.close()
        
        # 【重要】这里我们不再使用Celery的.delay()，而是直接调用，但需要在一个新线程中运行它
        # 为了保持简单，我们先简化模型，让worker独立运行
        # app只负责把任务放入队列
        return jsonify({"status": "accepted", "message": "This is a new query. We've started gathering data. Please check back in a few moments."}), 202

@app.route('/')
def index():
    return render_template('index.html')

