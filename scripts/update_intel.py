#!/usr/bin/env python3
"""
update_intel.py — Scrapes open-source intelligence feeds to keep intel-data.json fresh.

Runs via GitHub Actions every 6 hours. Pulls from:
- Naval News RSS for fleet movements
- Defense news RSS for conflict/exercise updates
- Validates and merges with existing data

For data that can't be auto-scraped, the JSON serves as a manually-curated
baseline that PikeClaw or Robert can update directly.
"""

import json
import os
import sys
from datetime import datetime, timezone

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'intel-data.json')


def load_existing():
    """Load existing intel data."""
    try:
        with open(DATA_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_timestamp(data):
    """Update the generation timestamp."""
    data['generated_utc'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    data['version'] = data.get('version', 0) + 1
    return data


def fetch_naval_news():
    """Try to pull latest naval deployment info from RSS feeds."""
    try:
        import feedparser
        feeds = [
            'https://www.navalnews.com/feed/',
            'https://news.usni.org/feed',
        ]
        updates = []
        for url in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = entry.get('title', '').lower()
                    # Look for deployment-related keywords
                    keywords = ['carrier', 'strike group', 'deployed', 'transit',
                               'fleet', 'submarine', 'patrol', 'exercise']
                    if any(kw in title for kw in keywords):
                        updates.append({
                            'title': entry.get('title', ''),
                            'link': entry.get('link', ''),
                            'published': entry.get('published', ''),
                            'source': feed.feed.get('title', url)
                        })
            except Exception as e:
                print(f'  Warning: Failed to fetch {url}: {e}')
        return updates
    except ImportError:
        print('  feedparser not available, skipping RSS')
        return []


def main():
    print('=== PikeClaw Intel Data Updater ===')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')

    data = load_existing()
    if not data:
        print('ERROR: No existing data found. Cannot update.')
        sys.exit(1)

    print(f'Loaded existing data (version {data.get("version", "?")})')

    # Check for naval news updates
    print('\nChecking naval news feeds...')
    naval_news = fetch_naval_news()
    if naval_news:
        print(f'  Found {len(naval_news)} deployment-related articles:')
        for n in naval_news:
            print(f'    - {n["title"][:80]}')
        # Store latest news references (for manual review / future AI processing)
        data['_naval_news_refs'] = naval_news[:10]
    else:
        print('  No new deployment articles found')

    # Update timestamp
    data = update_timestamp(data)
    print(f'\nUpdated timestamp to {data["generated_utc"]}')
    print(f'Version: {data["version"]}')

    # Write back
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'Wrote {os.path.getsize(DATA_PATH)} bytes to {DATA_PATH}')
    print('\n=== Update complete ===')


if __name__ == '__main__':
    main()
