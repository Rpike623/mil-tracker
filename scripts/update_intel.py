#!/usr/bin/env python3
"""
update_intel.py — Auto-updates intel-data.json every 4 hours via GitHub Actions.

Data sources (all open/public):
  - USNI News RSS          — carrier movements, fleet deployments
  - Naval News RSS         — ship deployments, exercises
  - Defense News RSS       — CENTCOM ops, exercises
  - Breaking Defense RSS   — military exercises, new deployments
  - GDACS / USGS           — conflict/natural disaster zones
  - Wikipedia / public     — exercise schedules (static fallback)

For semi-static data (troop counts, base details) the JSON baseline is
manually maintained and only the timestamp + news refs are auto-updated.
"""

import json
import os
import re
import sys
import requests
from datetime import datetime, timezone, timedelta

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    print('  feedparser not available — install with: pip install feedparser')

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'intel-data.json')

HEADERS = {'User-Agent': 'PikeClaw-OSINT-Bot/1.0 (https://rpike623.github.io/mil-tracker)'}

# ─────────────────────────────────────────
# NEWS FEEDS
# ─────────────────────────────────────────

NEWS_FEEDS = [
    {'url': 'https://news.usni.org/feed',               'label': 'USNI News'},
    {'url': 'https://www.navalnews.com/feed/',           'label': 'Naval News'},
    {'url': 'https://www.defensenews.com/arc/outboundfeeds/rss/', 'label': 'Defense News'},
    {'url': 'https://taskandpurpose.com/feed/',          'label': 'Task & Purpose'},
    {'url': 'https://www.militarytimes.com/arc/outboundfeeds/rss/', 'label': 'Military Times'},
]

# Keywords that indicate deployment/exercise/conflict relevance
DEPLOYMENT_KW = [
    'carrier', 'strike group', 'csg', 'arg', 'deployed', 'deployment', 'transit',
    'destroyer', 'submarine', 'uss ', 'naval', 'fleet', 'centcom', 'fifth fleet',
    '5th fleet', 'middle east', 'persian gulf', 'arabian sea', 'red sea',
    'mediterranean', 'israel', 'iran', 'houthi', 'yemen', 'iraq', 'syria',
]

EXERCISE_KW = [
    'exercise', 'drills', 'nato', 'operation', 'maneuver', 'wargame',
    'iron dome', 'juniper', 'bright star',
]

CONFLICT_KW = [
    'strike', 'attack', 'killed', 'missile', 'drone strike', 'airstrike',
    'ceasefire', 'offensive', 'invasion', 'escalat',
]


def fetch_feed(src):
    """Fetch and parse a single RSS feed."""
    if not HAS_FEEDPARSER:
        return []
    try:
        feed = feedparser.parse(src['url'])
        items = []
        for entry in feed.entries[:10]:
            title = entry.get('title', '').strip()
            if not title:
                continue
            items.append({
                'title': title,
                'link': entry.get('link', ''),
                'published': entry.get('published', ''),
                'source': src['label'],
            })
        return items
    except Exception as e:
        print(f'  Warning: Failed to fetch {src["label"]}: {e}')
        return []


def categorize(title):
    t = title.lower()
    cats = []
    if any(k in t for k in DEPLOYMENT_KW):
        cats.append('deployment')
    if any(k in t for k in EXERCISE_KW):
        cats.append('exercise')
    if any(k in t for k in CONFLICT_KW):
        cats.append('conflict')
    return cats


def fetch_all_news():
    """Pull all feeds and categorize articles."""
    all_items = []
    for src in NEWS_FEEDS:
        items = fetch_feed(src)
        print(f'  {src["label"]}: {len(items)} items')
        for item in items:
            item['categories'] = categorize(item['title'])
            all_items.append(item)

    # Sort by relevance — articles with categories first
    all_items.sort(key=lambda x: (len(x['categories']) == 0, x.get('published', '')))
    return all_items


# ─────────────────────────────────────────
# GPS JAMMING — pull from gpsjam.org data
# (they provide a public CSV/JSON endpoint)
# ─────────────────────────────────────────

def fetch_gps_status():
    """Check gpsjam.org for active jamming regions (best-effort)."""
    try:
        # gpsjam doesn't have a public API but we can pull their latest GeoJSON
        r = requests.get('https://gpsjam.org/map.json', headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            print(f'  gpsjam.org: fetched {len(data)} records')
            return data
    except Exception as e:
        print(f'  gpsjam.org: {e}')
    return None


# ─────────────────────────────────────────
# THREAT LEVEL — compute from news volume
# ─────────────────────────────────────────

def compute_threat_indicators(news_items):
    """Count conflict/deployment mentions as a rough signal."""
    deployment_count = sum(1 for i in news_items if 'deployment' in i.get('categories', []))
    conflict_count   = sum(1 for i in news_items if 'conflict' in i.get('categories', []))
    exercise_count   = sum(1 for i in news_items if 'exercise' in i.get('categories', []))
    return {
        'deployment_articles': deployment_count,
        'conflict_articles':   conflict_count,
        'exercise_articles':   exercise_count,
        'total_articles':      len(news_items),
        'computed_at':         datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def load_existing():
    try:
        with open(DATA_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_timestamp(data):
    data['generated_utc'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    data['version'] = data.get('version', 0) + 1
    return data


def main():
    print('╔══════════════════════════════════════╗')
    print('║   PikeClaw Intel Data Updater v2.0   ║')
    print('╚══════════════════════════════════════╝')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}\n')

    data = load_existing()
    if not data:
        print('ERROR: No existing data found at', DATA_PATH)
        sys.exit(1)

    print(f'Loaded existing data (v{data.get("version","?")})\n')

    # ── 1. News feeds
    print('[ 1/3 ] Fetching news feeds...')
    news_items = fetch_all_news()
    print(f'        Total: {len(news_items)} articles')

    deployment_news = [i for i in news_items if 'deployment' in i.get('categories', [])]
    conflict_news   = [i for i in news_items if 'conflict' in i.get('categories', [])]
    exercise_news   = [i for i in news_items if 'exercise' in i.get('categories', [])]

    print(f'        Deployment: {len(deployment_news)} | Conflict: {len(conflict_news)} | Exercise: {len(exercise_news)}')

    # Store top refs for the dashboard to optionally display
    data['_naval_news_refs'] = deployment_news[:10]
    data['_conflict_news_refs'] = conflict_news[:5]
    data['_exercise_news_refs'] = exercise_news[:5]
    # Compute new threat indicators but preserve manual_override and breaking_events if set
    new_indicators = compute_threat_indicators(news_items)
    existing_indicators = data.get('_threat_indicators', {})
    for preserve_key in ('manual_override', 'breaking_events'):
        if preserve_key in existing_indicators:
            new_indicators[preserve_key] = existing_indicators[preserve_key]
    data['_threat_indicators'] = new_indicators

    # ── 2. GPS jamming status (best-effort)
    print('\n[ 2/3 ] Checking GPS jamming data...')
    gps_data = fetch_gps_status()
    if gps_data:
        # Don't replace our curated zones, just note the latest fetch
        data['_gps_last_fetch'] = datetime.now(timezone.utc).isoformat()
        print('        GPS jamming data fetched (zones remain manually curated)')
    else:
        print('        GPS jamming data unavailable — keeping existing zones')

    # ── 3. Update timestamp & version
    print('\n[ 3/3 ] Updating metadata...')
    data = update_timestamp(data)
    print(f'        Version: {data["version"]}')
    print(f'        Timestamp: {data["generated_utc"]}')

    # Write
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(DATA_PATH) / 1024
    print(f'\n✅ Written {size_kb:.1f} KB to intel-data.json')
    print('=== Update complete ===')

    # Print notable headlines for the Actions log
    if deployment_news:
        print('\n📡 Top deployment headlines:')
        for n in deployment_news[:5]:
            print(f'   [{n["source"]}] {n["title"][:90]}')
    if conflict_news:
        print('\n⚔️  Top conflict headlines:')
        for n in conflict_news[:3]:
            print(f'   [{n["source"]}] {n["title"][:90]}')


if __name__ == '__main__':
    main()
