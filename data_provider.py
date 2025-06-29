# data_provider.py 

import os
import sys
import time
import math
import sqlite3
import pandas as pd
from datetime import datetime
from threading import Lock
from Bio import Entrez

# --- 全局配置 ---
SJR_DATA_FILE = "sjr_data_2024.csv"

# --- NCBI API 配置 ---
NCBI_EMAIL = os.getenv("NCBI_EMAIL")
if not NCBI_EMAIL:
    print("FATAL ERROR: NCBI_EMAIL environment variable not set.")
    sys.exit(1)
Entrez.email = NCBI_EMAIL

NCBI_API_KEY = os.getenv("NCBI_API_KEY")
if NCBI_API_KEY:
    Entrez.api_key = NCBI_API_KEY
    print("✅ NCBI API key loaded successfully.")
    API_DELAY_SECONDS = 0.11
else:
    print("⚠️ NCBI API key not found. Using lower request rate.")
    API_DELAY_SECONDS = 0.35

# --- 数据库设置 ---
DB_FILE = "journal_cache.db"
db_lock = Lock()

def load_sjr_data_to_db(csv_file_path=SJR_DATA_FILE):
    if not os.path.exists(csv_file_path):
        print(f"⚠️ WARNING: SJR data file not found at '{csv_file_path}'.")
        return
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS journal_metrics (title TEXT PRIMARY KEY, sjr_score REAL)")
        cursor.execute("SELECT COUNT(*) FROM journal_metrics")
        if cursor.fetchone()[0] == 0:
            print("[data_provider] Populating journal_metrics table from SJR data...")
            try:
                df = pd.read_csv(csv_file_path, sep=';')
                df_to_load = df[['Title', 'SJR Best Quartile']].copy()
                quartile_map = {'Q1': 4.0, 'Q2': 2.5, 'Q3': 1.5, 'Q4': 0.5}
                df_to_load['sjr_score'] = df_to_load['SJR Best Quartile'].map(quartile_map).fillna(1.0)
                df_to_load['title'] = df_to_load['Title'].str.lower()
                final_df = df_to_load[['title', 'sjr_score']].drop_duplicates(subset=['title'])
                final_df.to_sql('journal_metrics', conn, if_exists='append', index=False)
                print(f"✅ Successfully loaded {len(final_df)} journal metrics into the database.")
            except KeyError:
                 print(f"❌ ERROR loading SJR data: 'SJR Best Quartile' column not found. Please check the CSV file.")
            except Exception as e:
                print(f"❌ ERROR loading SJR data: {e}")
        conn.commit()
        conn.close()

def setup_database():
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS query_jobs (query TEXT PRIMARY KEY, status TEXT NOT NULL, max_results INTEGER, results TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS articles_data (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, pmid TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(query, pmid))")
        cursor.execute("CREATE TABLE IF NOT EXISTS trends_data (query TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.commit()
        conn.close()
    print("[data_provider] All database tables are ready.")
    load_sjr_data_to_db()

def get_dynamic_journal_score(journal_title: str) -> float:
    if not journal_title: return 5.0
    with db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT sjr_score FROM journal_metrics WHERE title=?", (journal_title.lower(),))
        result = cursor.fetchone()
        conn.close()
        return float(result[0]) * 5 if result else 5.0

def get_pub_type_weight(pub_types: list) -> float:
    weights = {'Review': 1.2, 'Journal Article': 1.0, 'Clinical Trial': 1.3, 'Meta-Analysis': 1.5}
    return max((weights.get(pt, 1.0) for pt in pub_types), default=1.0)

def get_citation_count(pmid: str) -> int:
    try:
        handle = Entrez.elink(dbfrom="pubmed", id=pmid, linkname="pubmed_pubmed_citedin")
        record = Entrez.read(handle)
        handle.close()
        return len(record[0]["LinkSetDb"][0]["Link"]) if record and record[0]["LinkSetDb"] else 0
    except Exception:
        return 0

def calculate_impact_score(citations: int, journal_title: str, year: str, pub_types: list) -> float:
    try:
        citation_score = math.log1p(citations) * 15
        journal_score = get_dynamic_journal_score(journal_title)
        current_year = datetime.now().year
        pub_year = int(year) if year and year.isdigit() else current_year
        years_since_pub = max(1, current_year - pub_year)
        citation_velocity = citations / years_since_pub
        velocity_score = math.log1p(citation_velocity) * 10
        pub_type_bonus = get_pub_type_weight(pub_types) - 1.0
        pub_type_score = pub_type_bonus * 20
        final_score = citation_score + journal_score + velocity_score + pub_type_score
        return round(final_score, 2)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        print(f"DEBUG: Could not calculate score. Citations: {citations}, Year: {year}. Error: {e}")
        return 0.0

def get_publication_trend(query: str, years_to_scan: int = 20) -> dict:
    current_year = datetime.now().year
    years = range(current_year - years_to_scan + 1, current_year + 1)
    trend = {str(year): 0 for year in years}
    total_results = 0
    try:
        handle = Entrez.esearch(db="pubmed", term=query, retmax="0")
        record = Entrez.read(handle)
        handle.close()
        total_results = int(record["Count"])
    except Exception: total_results = -1
    for year in years:
        try:
            year_query = f"({query}) AND ({year}[Publication Date])"
            handle = Entrez.esearch(db="pubmed", term=year_query, retmax="0")
            record = Entrez.read(handle)
            handle.close()
            trend[str(year)] = int(record["Count"])
            time.sleep(API_DELAY_SECONDS)
        except Exception: trend[str(year)] = 0
    return {"trend": trend, "total_results": total_results}

def get_articles_by_query(query: str, max_results: int = 10) -> list:
    articles = []
    try:
        handle = Entrez.esearch(db="pubmed", term=query, sort="relevance", retmax=str(max_results))
        record = Entrez.read(handle)
        handle.close()
        id_list = record["IdList"]
        if not id_list: return []
        handle = Entrez.efetch(db="pubmed", id=id_list, rettype="medline", retmode="xml")
        pubmed_articles = Entrez.read(handle)["PubmedArticle"]
        handle.close()
        for pubmed_article in pubmed_articles:
            time.sleep(API_DELAY_SECONDS)
            try:
                article = pubmed_article['MedlineCitation']['Article']
                pmid = str(pubmed_article['MedlineCitation']['PMID'])
                title = article.get('ArticleTitle', 'No Title Available')
                journal_info = article.get('Journal', {})
                journal_title = journal_info.get('Title', 'N/A')
                pub_date = journal_info.get('JournalIssue', {}).get('PubDate', {})
                year_str = pub_date.get('Year') or pub_date.get('MedlineDate', 'N/A').split(' ')[0]
                authors_list = article.get('AuthorList', [])
                authors_str = ", ".join([f"{a.get('Initials', '')} {a.get('LastName', '')}".strip() for a in authors_list])
                abstract_list = article.get('Abstract', {}).get('AbstractText', [])
                abstract_text = " ".join(abstract_list) if abstract_list else "No abstract available."
                pub_types = article.get('PublicationTypeList', [])
                citations = get_citation_count(pmid)
                impact_score = calculate_impact_score(citations, journal_title, year_str, pub_types)
                articles.append({
                    'pmid': pmid, 'title': title, 'authors_str': authors_str,
                    'year': year_str, 'journal': journal_title, 'abstract_text': abstract_text,
                    'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    'citations': citations, 'impact_score': impact_score
                })
            except Exception as e:
                print(f"[data_provider] FAILED to process one article: {e}")
                continue
        return articles
    except Exception as e:
        print(f"[data_provider] FATAL ERROR in get_articles_by_query: {e}")
        raise e

# 【已删除】文件末尾的 setup_database() 调用已被移除。
