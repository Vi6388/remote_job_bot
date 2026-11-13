"""Public API job collector. No credentials or scraping required for initial sources."""
from __future__ import annotations
import csv
import hashlib
import html
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import requests

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'jobs.sqlite3'
OUT = ROOT / 'output'
USER_AGENT = 'RemoteJobResearchBot/1.0 (personal job search; public APIs)'
HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}


def get_json(url, params=None):
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=25)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logging.warning('Source failed: %s (%s)', url, exc)
        return None


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def iso_date(value):
    if not value:
        return ''
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return ''


def canonical_url(url):
    p = urlparse(url or '')
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), '', '', ''))


def job(source, source_id, title, company, url, location='', description='', published='', category=''):
    url = canonical_url(url)
    if not url.startswith(('https://', 'http://')):
        return None
    return dict(id=hashlib.sha256(f'{source}:{source_id or url}'.encode()).hexdigest()[:24],
                source=source, title=plain(title), company=plain(company), url=url,
                location=plain(location), description=plain(description)[:18000],
                published=iso_date(published), category=plain(category))


def fetch_remotive():
    data = get_json('https://remotive.com/api/remote-jobs', {'limit': 2000}) or {}
    for x in data.get('jobs', []):
        j = job('Remotive', x.get('id'), x.get('title'), x.get('company_name'),
                x.get('url'), x.get('candidate_required_location'), x.get('description'),
                x.get('publication_date'), x.get('category'))
        if j: yield j


def fetch_arbeitnow():
    # Paginated public API. Avoid aggressive traffic; 5 pages maximum per run.
    for page in range(1, 6):
        data = get_json('https://www.arbeitnow.com/api/job-board-api', {'page': page}) or {}
        for x in data.get('data', []):
            if not x.get('remote'):
                continue
            published = datetime.fromtimestamp(x['created_at'], tz=timezone.utc).isoformat() if x.get('created_at') else ''
            j = job('Arbeitnow', x.get('slug'), x.get('title'), x.get('company_name'),
                    x.get('url'), x.get('location'), x.get('description'), published,
                    ', '.join(x.get('tags') or []))
            if j: yield j
        if not data.get('links', {}).get('next'):
            break


def fetch_greenhouse(board):
    # Public Greenhouse job board API. Board tokens must be configured by user.
    data = get_json(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs', {'content': 'true'}) or {}
    for x in data.get('jobs', []):
        j = job('Greenhouse', f'{board}:{x.get("id")}', x.get('title'), board,
                x.get('absolute_url'), (x.get('location') or {}).get('name'),
                x.get('content'), x.get('updated_at'))
        if j: yield j


def fetch_ashby(board):
    data = get_json(f'https://api.ashbyhq.com/posting-api/job-board/{board}', {'includeCompensation': 'true'}) or {}
    for x in data.get('jobs', []):
        if not x.get('isRemote') and 'remote' not in str(x.get('workplaceType', '')).lower():
            continue
        j = job('Ashby', f'{board}:{x.get("id") or x.get("jobUrl")}', x.get('title'), board,
                x.get('jobUrl') or x.get('applyUrl'), x.get('location'),
                x.get('descriptionPlain') or x.get('descriptionHtml'), x.get('publishedAt'))
        if j: yield j


def classify(j, config):
    title = j['title'].lower()
    description = j['description'].lower()
    location = j['location'].lower()
    text = f'{title} {description[:9000]} {j["category"].lower()}'
    if not any(k in text for k in config['keywords']):
        return None
    # Titles must be engineering-related: avoid recruiting/marketing posts that mention code.
    if not any(k in title for k in ('engineer', 'developer', 'programmer', 'full stack', 'fullstack', 'frontend', 'front end', 'backend', 'back end', 'software', 'machine learning', 'ai ')):
        return None
    combined = f'{location} {description[:7000]}'
    negative = any(p in combined for p in config['blocked_location_phrases'])
    positive = any(p in combined for p in ('philippines', 'worldwide', 'anywhere in the world', 'work from anywhere', 'global remote', 'any location', 'anywhere globally'))
    # Do not treat generic 'remote' as verified Philippines eligibility.
    eligibility = 'excluded' if negative else 'likely_eligible' if positive else 'needs_verification'
    if negative:
        return None
    priority = any(p in combined for p in config['priority_countries'])
    score = 40 + (25 if positive else 0) + (15 if priority else 0)
    score += min(20, sum(4 for k in ('react', 'typescript', 'node.js', 'python', 'next.js') if k in text))
    return eligibility, min(score, 100)


def recent(j, days):
    if not j['published']:
        return True  # Keep but flag unknown date in output.
    return datetime.fromisoformat(j['published']) >= datetime.now(timezone.utc) - timedelta(days=days)


def setup_db(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, source TEXT, title TEXT, company TEXT, url TEXT,
        location TEXT, description TEXT, published TEXT, category TEXT,
        eligibility TEXT, score INTEGER, first_seen TEXT, last_seen TEXT)''')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS jobs_url ON jobs(url)')
    conn.commit()


def run():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    OUT.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    setup_db(conn)
    candidates = list(fetch_remotive()) + list(fetch_arbeitnow())
    for board in config.get('greenhouse_boards', []):
        candidates.extend(fetch_greenhouse(board))
    for board in config.get('ashby_boards', []):
        candidates.extend(fetch_ashby(board))
    today = datetime.now(timezone.utc).isoformat()
    fresh = []
    seen = set()
    for j in candidates:
        if j['url'] in seen or not recent(j, config['max_age_days']):
            continue
        seen.add(j['url'])
        classified = classify(j, config)
        if classified is None:
            continue
        j['eligibility'], j['score'] = classified
        existing = conn.execute('SELECT first_seen FROM jobs WHERE url=?', (j['url'],)).fetchone()
        first_seen = existing[0] if existing else today
        conn.execute('''INSERT INTO jobs (id,source,title,company,url,location,description,published,category,eligibility,score,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title, location=excluded.location,
              description=excluded.description, published=excluded.published,
              eligibility=excluded.eligibility, score=excluded.score, last_seen=excluded.last_seen''',
            (j['id'], j['source'], j['title'], j['company'], j['url'], j['location'], j['description'],
             j['published'], j['category'], j['eligibility'], j['score'], first_seen, today))
        if not existing:
            fresh.append(j)
    conn.commit()
    fresh.sort(key=lambda j: (j['eligibility'] == 'likely_eligible', j['score'], j['published']), reverse=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    fields = ['score', 'eligibility', 'title', 'company', 'location', 'source', 'published', 'url']
    output = OUT / f'new_jobs_{stamp}.csv'
    with output.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(fresh)
    print(f'Collected {len(candidates)} raw postings; {len(fresh)} new filtered jobs; report: {output}')
    print(f'Target: {config["target_daily_leads"]} daily leads (not guaranteed).')
    conn.close()


if __name__ == '__main__':
    run()
