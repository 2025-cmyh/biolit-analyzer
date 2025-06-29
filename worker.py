# worker.py 

import time
import sqlite3
import json
from threading import Lock
# 【重要】worker 现在需要自己导入 setup_database
from data_provider import get_articles_by_query, get_publication_trend, setup_database

DB_FILE = "journal_cache.db"
db_lock = Lock()

def get_job_from_queue():
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("BEGIN EXCLUSIVE")
        cursor.execute("SELECT query, max_results FROM query_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1")
        job = cursor.fetchone()
        if job:
            query = job[0]
            cursor.execute("UPDATE query_jobs SET status = 'processing', updated_at = CURRENT_TIMESTAMP WHERE query = ?", (query,))
        conn.commit()
        conn.close()
    return job if job else None

def process_job(query, max_results=20):
    print(f"🔥 Worker: Starting job for query '{query}' with max_results={max_results}")
    try:
        articles = get_articles_by_query(query, max_results=max_results)
        trend_response = get_publication_trend(query)
        trend_data = trend_response.get("trend", {})

        with db_lock:
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM articles_data WHERE query = ?", (query,))
            for article in articles:
                cursor.execute(
                    "INSERT INTO articles_data (query, pmid, data) VALUES (?, ?, ?)",
                    (query, article['pmid'], json.dumps(article))
                )
            cursor.execute("INSERT OR REPLACE INTO trends_data (query, data) VALUES (?, ?)",(query, json.dumps(trend_data)))
            cursor.execute("UPDATE query_jobs SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE query = ?", (query,))
            conn.commit()
            conn.close()
        print(f"✅ Worker: Job for '{query}' completed successfully.")
    except Exception as e:
        print(f"❌ Worker: Job for '{query}' failed. Error: {e}")
        with db_lock:
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE query_jobs SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE query = ?", (query,))
            conn.commit()
            conn.close()

def main_loop():
    print("🚀 Worker process started. Waiting for jobs...")
    while True:
        job_details = get_job_from_queue()
        if job_details:
            query, max_results = job_details
            process_job(query, max_results)
        else:
            time.sleep(5) 

if __name__ == "__main__":
    # 【重要】worker 在启动时，自己负责初始化数据库
    setup_database()
    main_loop()