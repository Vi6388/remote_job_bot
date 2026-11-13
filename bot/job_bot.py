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


def job(source, source_id, title, company, url, location='', description='', published='', category='', compensation=''):
    url = canonical_url(url)
    if not url.startswith(('https://', 'http://')):
        return None
    return dict(id=hashlib.sha256(f'{source}:{source_id or url}'.encode()).hexdigest()[:24],
                source=source, title=plain(title), company=plain(company), url=url,
                location=plain(location), description=plain(description)[:18000],
                published=iso_date(published), category=plain(category), compensation=plain(compensation) or 'Not disclosed')


def fetch_remotive():
    data = get_json('https://remotive.com/api/remote-jobs', {'limit': 2000}) or {}
    for x in data.get('jobs', []):
        j = job('Remotive', x.get('id'), x.get('title'), x.get('company_name'),
                x.get('url'), x.get('candidate_required_location'), x.get('description'),
                x.get('publication_date'), x.get('category'), x.get('salary'))
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


def fetch_lever(board):
    # Lever's public postings API requires a known company site slug.
    data = get_json(f'https://api.lever.co/v0/postings/{board}', {'mode': 'json'}) or []
    if not isinstance(data, list):
        return
    for x in data:
        categories = x.get('categories') or {}
        description = ' '.join([plain(x.get('descriptionPlain') or x.get('description')),
                                plain(x.get('additionalPlain') or x.get('additional'))])
        salary = x.get('salaryDescriptionPlain') or ''
        j = job('Lever', f'{board}:{x.get("id")}', x.get('text'), board,
                x.get('hostedUrl') or x.get('applyUrl'),
                categories.get('location') or x.get('workplaceType') or '',
                description, '', ', '.join(categories.get('allLocations') or []), salary)
        if j: yield j


def fetch_himalayas():
    # Public Himalayas job API; gracefully skip if unavailable or changed.
    for offset in (0, 20, 40, 60, 80):
        data = get_json('https://himalayas.app/jobs/api', {'limit': 20, 'offset': offset})
        if not isinstance(data, dict):
            break
        items = data.get('jobs') or []
        if not items:
            break
        for x in items:
            company = x.get('companyName') or (x.get('company') or {}).get('name') if isinstance(x.get('company'), dict) else x.get('companyName')
            loc = x.get('location') or x.get('locationRestrictions') or ''
            if isinstance(loc, (dict, list)):
                loc = json.dumps(loc)
            salary = x.get('salary') or ''
            if isinstance(salary, (dict, list)):
                salary = json.dumps(salary, ensure_ascii=False)
            j = job('Himalayas', x.get('id'), x.get('title'), company,
                    x.get('applicationLink') or x.get('url') or x.get('applicationUrl'),
                    loc, x.get('description') or x.get('excerpt'),
                    x.get('pubDate') or x.get('publishedAt'), '', salary)
            if j: yield j
        if len(items) < 20:
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
                x.get('descriptionPlain') or x.get('descriptionHtml'), x.get('publishedAt'),
                (x.get('compensation') or {}).get('compensationTierSummary') if isinstance(x.get('compensation'), dict) else '')
        if j: yield j


def fetch_remoteok():
    data = get_json('https://remoteok.com/api') or []
    if not isinstance(data, list):
        return
    for x in data:
        if not isinstance(x, dict) or not x.get('position'):
            continue
        low, high = x.get('salary_min'), x.get('salary_max')
        salary = f'{low}–{high} (currency unspecified)' if low and high else ''
        j = job('RemoteOK', x.get('id'), x.get('position'), x.get('company'),
                x.get('url') or x.get('apply_url'), x.get('location') or 'Remote',
                x.get('description'), x.get('date'), ', '.join(x.get('tags') or []), salary)
        if j: yield j


def fetch_jobicy():
    data = get_json('https://jobicy.com/api/v2/remote-jobs', {'count': 50}) or {}
    for x in data.get('jobs', []):
        salary = x.get('annualSalary') or ''
        if not salary and (x.get('salaryMin') or x.get('salaryMax')):
            salary = f"{x.get('salaryCurrency', '')} {x.get('salaryMin', '')}–{x.get('salaryMax', '')}"
        j = job('Jobicy', x.get('id'), x.get('jobTitle'), x.get('companyName'),
                x.get('url'), x.get('jobGeo') or 'Remote', x.get('jobDescription'),
                x.get('pubDate'), x.get('jobIndustry'), salary)
        if j: yield j


def match_category(title, config):
    """Match job titles to verified role families, not incidental JD keywords."""
    for category in ('software_development', 'ai_training_annotation'):
        rules = config['role_categories'][category]
        if any(re.search(pattern, title, flags=re.I) for pattern in rules['title_patterns']):
            if not any(re.search(pattern, title, flags=re.I) for pattern in rules.get('exclude_title_patterns', [])):
                return category
    return None


def classify(j, config):
    title = j['title']
    description = j['description'].lower()
    location = j['location'].lower()
    if any(term.lower() in (j['company'] + ' ' + j['url']).lower() for term in config.get('excluded_companies', [])):
        return None
    category = match_category(title, config)
    if not category:
        return None
    combined = f'{location} {description[:7000]}'
    negative = any(p in combined for p in config['blocked_location_phrases'])
    positive = any(p in combined for p in ('philippines', 'worldwide', 'anywhere in the world', 'work from anywhere', 'global remote', 'any location', 'anywhere globally'))
    if negative:
        return None
    eligibility = 'likely_eligible' if positive else 'needs_verification'
    if config.get('strict_eligibility_only') and not positive:
        return None
    priority = any(p in combined for p in config['priority_countries'])
    verified = ('shopify', 'ecommerce', 'e-commerce', 'bubble', 'data annotation', 'data labeling', 'coding evaluation')
    match_bonus = min(20, sum(5 for k in verified if k in (title + ' ' + description[:2500]).lower()))
    score = min(100, 40 + (25 if positive else 0) + (15 if priority else 0) + match_bonus)
    return eligibility, score, category


def recent(j, days):
    if not j['published']:
        return True  # Keep but flag unknown date in output.
    return datetime.fromisoformat(j['published']) >= datetime.now(timezone.utc) - timedelta(days=days)


def setup_db(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, source TEXT, title TEXT, company TEXT, url TEXT,
        location TEXT, description TEXT, published TEXT, category TEXT, compensation TEXT,
        eligibility TEXT, score INTEGER, first_seen TEXT, last_seen TEXT)''')
    if 'compensation' not in [r[1] for r in conn.execute('PRAGMA table_info(jobs)')]:
        conn.execute("ALTER TABLE jobs ADD COLUMN compensation TEXT DEFAULT 'Not disclosed'")
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS jobs_url ON jobs(url)')
    conn.commit()


def run():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    OUT.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    setup_db(conn)
    candidates = []
    sources = [('Remotive', fetch_remotive), ('Arbeitnow', fetch_arbeitnow),
               ('RemoteOK', fetch_remoteok), ('Jobicy', fetch_jobicy),
               ('Himalayas', fetch_himalayas)]
    for name, fetcher in sources:
        if name in config.get('disabled_sources', []):
            continue
        try:
            batch = list(fetcher())
            logging.info('%s: %d raw jobs', name, len(batch))
            candidates.extend(batch)
        except Exception as exc:
            logging.warning('%s failed: %s', name, exc)
    for board in config.get('lever_boards', []):
        candidates.extend(fetch_lever(board))
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
        j['eligibility'], j['score'], j['role_category'] = classified
        existing = conn.execute('SELECT first_seen FROM jobs WHERE url=?', (j['url'],)).fetchone()
        first_seen = existing[0] if existing else today
        conn.execute('''INSERT INTO jobs (id,source,title,company,url,location,description,published,category,compensation,eligibility,score,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET title=excluded.title, location=excluded.location,
              description=excluded.description, published=excluded.published, compensation=excluded.compensation,
              eligibility=excluded.eligibility, score=excluded.score, last_seen=excluded.last_seen''',
            (j['id'], j['source'], j['title'], j['company'], j['url'], j['location'], j['description'],
             j['published'], j['category'], j['compensation'], j['eligibility'], j['score'], first_seen, today))
        if not existing:
            fresh.append(j)
    conn.commit()
    fresh.sort(key=lambda j: (j['eligibility'] == 'likely_eligible', j['score'], j['published']), reverse=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    # Show all currently matching listings, not just those first seen today.
    # Exactly four columns as requested.
    # Quota applies to the *top 100*, not to the number of source results.
    # Never invent or duplicate jobs to fill a quota.
    current = [j for j in candidates if j['url'] in seen and 'role_category' in j]
    current.sort(key=lambda j: (j['eligibility'] == 'likely_eligible', j['score'], j['published']), reverse=True)
    limit = config['target_daily_leads']
    sw_limit = round(limit * config['role_priorities']['software_development'] / 100)
    ai_limit = limit - sw_limit
    software = [j for j in current if j['role_category'] == 'software_development']
    ai = [j for j in current if j['role_category'] == 'ai_training_annotation']
    chosen = software[:sw_limit] + ai[:ai_limit]
    # Fill unused slots with remaining verified matches, software first.
    chosen_urls = {j['url'] for j in chosen}
    for j in software[sw_limit:] + ai[ai_limit:]:
        if len(chosen) >= limit:
            break
        if j['url'] not in chosen_urls:
            chosen.append(j)
            chosen_urls.add(j['url'])
    chosen.sort(key=lambda j: (j['eligibility'] == 'likely_eligible', j['score']), reverse=True)
    rows = [(j['company'], j['title'], j['compensation'], j['url']) for j in chosen]
    print(f"Category totals: software={len(software)}, AI training/annotation={len(ai)}; exported software={sum(j['role_category']=='software_development' for j in chosen)}, AI={sum(j['role_category']=='ai_training_annotation' for j in chosen)}")
    output = OUT / f'jobs_{stamp}.csv'
    with output.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['Company Name', 'Role', 'Compensation', 'Job Link'])
        writer.writerows((company, title, compensation or 'Not disclosed', url)
                         for company, title, compensation, url in rows)
    print(f'Collected {len(candidates)} raw postings; {len(rows)} current matching jobs ({len(fresh)} newly seen); report: {output}')
    print(f'Target: {config["target_daily_leads"]} daily leads (not guaranteed).')
    if len(rows) < config['target_daily_leads']:
        print('Below target: add verified Lever/Greenhouse/Ashby board slugs or other permitted APIs.')
    conn.close()


if __name__ == '__main__':
    run()
