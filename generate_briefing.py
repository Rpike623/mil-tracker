#!/usr/bin/env python3
"""
PIKECLAW OSINT BRIEFING GENERATOR
Fetches live military aircraft data + news, generates an AI briefing,
commits it to the GitHub repo as briefing.json
Runs every 60 minutes.
"""

import json, time, urllib.request, urllib.parse, subprocess, os, sys
from datetime import datetime, timezone

GITHUB_TOKEN = None  # loaded from git config
REPO = "Rpike623/mil-tracker"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BRIEFING_FILE = "/root/.openclaw/workspace/mil-tracker/briefing.json"

def fetch_url(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PikeClaw-OSINT/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        print(f"  fetch error {url[:60]}: {e}")
        return None

def fetch_aircraft():
    data = fetch_url("https://api.adsb.lol/v2/mil")
    if not data:
        return []
    try:
        return json.loads(data).get("ac", [])
    except:
        return []

def fetch_news():
    sources = [
        ("DEFNEWS", "https://www.defensenews.com/arc/outboundfeeds/rss/"),
        ("REUTERS", "https://feeds.reuters.com/Reuters/worldNews"),
        ("BBC ME",  "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ]
    headlines = []
    for label, url in sources:
        try:
            proxied = "https://api.allorigins.win/raw?url=" + urllib.parse.quote(url)
            raw = fetch_url(proxied, timeout=10)
            if not raw:
                continue
            import re
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", raw)
            for t1, t2 in titles[1:8]:  # skip feed title
                title = (t1 or t2).strip()
                if title and len(title) > 20:
                    headlines.append(f"[{label}] {title}")
        except Exception as e:
            print(f"  news error {label}: {e}")
    return headlines

def analyze_aircraft(aircraft):
    """Produce a structured summary of current military aircraft activity."""
    if not aircraft:
        return {}

    # Country ranges
    def get_group(hex_str):
        try:
            h = int(hex_str, 16)
        except:
            return "unknown"
        if 0xA00000 <= h <= 0xAFFFFF: return "us"
        if 0x730000 <= h <= 0x737FFF: return "iran"
        if 0x100000 <= h <= 0x13FFFF: return "russia"
        if 0x780000 <= h <= 0x7BFFFF: return "china"
        return "allied"

    def get_type(ac):
        t = (ac.get("t") or "").upper().replace(" ","").replace("-","")
        fighters   = ["F15","F16","F18","F22","F35","SU27","SU30","SU35","MIG29","J10","J11","J20","A10"]
        transports = ["C17","C130","C30J","C5","IL76","AN124","Y20","A400"]
        tankers    = ["KC10","KC46","KC135","KC130","MRTT","IL78"]
        recon      = ["P8","P3","RC135","E3","E6","U2","RQ4","MQ9","AWACS","E737"]
        bombers    = ["B52","B1","B2","TU95","TU160","H6"]
        helis      = ["UH60","AH64","CH47","CH53","MH60","MI17","MI24"]
        for p in fighters:
            if p in t: return "fighter"
        for p in tankers:
            if p in t: return "tanker"
        for p in bombers:
            if p in t: return "bomber"
        for p in recon:
            if p in t: return "recon"
        for p in transports:
            if p in t: return "transport"
        for p in helis:
            if p in t: return "heli"
        return "other"

    positioned = [a for a in aircraft if a.get("lat") and a.get("lon")]
    counts = {"us":0,"iran":0,"russia":0,"china":0,"allied":0}
    types  = {"fighter":0,"tanker":0,"recon":0,"bomber":0,"transport":0,"heli":0,"other":0}
    adversary_details = []

    for ac in positioned:
        grp = get_group(ac.get("hex",""))
        tp  = get_type(ac)
        counts[grp] = counts.get(grp, 0) + 1
        types[tp]   = types.get(tp, 0) + 1
        if grp in ("iran","russia","china"):
            adversary_details.append({
                "country": grp,
                "callsign": (ac.get("flight") or "").strip() or ac.get("hex",""),
                "type": ac.get("t","?"),
                "alt": ac.get("alt_baro","?"),
                "speed": round(ac.get("gs",0)) if ac.get("gs") else "?",
                "lat": round(ac.get("lat",0),2),
                "lon": round(ac.get("lon",0),2),
            })

    # Zone checks
    ZONES = [
        ("Strait of Hormuz",  25.5, 55.5, 27.5, 57.5),
        ("Persian Gulf",      24.0, 48.0, 30.0, 56.0),
        ("Taiwan Strait",     22.0, 117.0,26.0,121.0),
        ("South China Sea",   5.0, 108.0, 18.0,121.0),
        ("Black Sea",         41.0, 27.0, 47.0, 42.0),
    ]
    zone_activity = []
    for name, lat1, lon1, lat2, lon2 in ZONES:
        in_zone = [a for a in positioned
                   if lat1<=a.get("lat",0)<=lat2 and lon1<=a.get("lon",0)<=lon2]
        if in_zone:
            zone_activity.append(f"{name}: {len(in_zone)} aircraft")

    return {
        "total": len(positioned),
        "counts": counts,
        "types": types,
        "adversary_details": adversary_details[:20],
        "zone_activity": zone_activity,
        "tankers": types["tanker"],
        "bombers": types["bomber"],
        "recon": types["recon"],
    }

def generate_briefing_ai(analysis, headlines):
    """Call OpenRouter to generate the actual briefing text."""
    if not OPENROUTER_KEY:
        return generate_briefing_local(analysis, headlines)

    adv = analysis.get("adversary_details", [])
    zones = analysis.get("zone_activity", [])
    counts = analysis.get("counts", {})
    types = analysis.get("types", {})

    prompt = f"""You are a military OSINT analyst. Generate a concise, objective intelligence briefing based on the following live data. Be analytical, not alarmist. Use plain language. No markdown headers — just 3-4 short paragraphs. Be specific about numbers and locations.

LIVE AIRCRAFT DATA ({analysis.get('total',0)} aircraft tracked):
- US: {counts.get('us',0)}, Iran: {counts.get('iran',0)}, Russia: {counts.get('russia',0)}, China: {counts.get('china',0)}, Allied: {counts.get('allied',0)}
- Tankers airborne: {types.get('tanker',0)} (high tanker count = extended ops being prepared)
- ISR/Recon airborne: {types.get('recon',0)}
- Bombers airborne: {types.get('bomber',0)}
- Fighters/Attack: {types.get('fighter',0)}

ADVERSARY AIRCRAFT CURRENTLY VISIBLE:
{json.dumps(adv[:10], indent=2) if adv else "None currently broadcasting ADS-B"}

ACTIVE ALERT ZONES:
{chr(10).join(zones) if zones else "No aircraft in monitored zones"}

RECENT NEWS HEADLINES:
{chr(10).join(headlines[:10]) if headlines else "No headlines available"}

Write a 3-4 paragraph intelligence briefing. Include: overall activity assessment, notable adversary movements if any, zone activity significance, and one sentence on what to watch for in the next 24 hours."""

    payload = {
        "model": "openrouter/anthropic/claude-sonnet-4.6",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.3,
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://rpike623.github.io/mil-tracker/",
                "X-Title": "PikeClaw OSINT Tracker",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode())
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  AI briefing error: {e}")
        return generate_briefing_local(analysis, headlines)

def generate_briefing_local(analysis, headlines):
    """Fallback: algorithmic briefing without AI."""
    counts = analysis.get("counts", {})
    types  = analysis.get("types", {})
    zones  = analysis.get("zone_activity", [])
    adv    = analysis.get("adversary_details", [])
    total  = analysis.get("total", 0)

    threat = "LOW"
    if types.get("bomber",0) >= 1: threat = "ELEVATED"
    if counts.get("iran",0) + counts.get("russia",0) + counts.get("china",0) >= 3: threat = "ELEVATED"
    if zones: threat = "ELEVATED"
    if types.get("bomber",0) >= 2 and zones: threat = "HIGH"

    lines = []
    lines.append(f"THREAT ASSESSMENT: {threat}. Currently tracking {total} military aircraft globally across all monitored nations. "
                 f"US forces have {counts.get('us',0)} aircraft airborne. Allied partners account for {counts.get('allied',0)} additional tracked assets.")

    if types.get("tanker",0) >= 3:
        lines.append(f"LOGISTICS INDICATOR: {types['tanker']} aerial refueling tankers are currently airborne, suggesting extended-range operations are underway or being prepared. Tanker surges typically precede strike packages or long-duration ISR missions by 2-6 hours.")
    if types.get("recon",0) >= 2:
        lines.append(f"INTELLIGENCE COLLECTION: {types['recon']} ISR and reconnaissance aircraft are active. Elevated recon activity typically indicates active target acquisition or battle damage assessment operations.")
    if types.get("bomber",0) >= 1:
        lines.append(f"STRATEGIC INDICATOR: {types['bomber']} strategic bomber(s) currently tracked airborne. Bomber deployments are high-visibility signals and may indicate signaling, training, or pre-strike positioning.")

    if adv:
        countries = list(set(a["country"] for a in adv))
        lines.append(f"ADVERSARY ACTIVITY: {len(adv)} adversary aircraft currently broadcasting: {', '.join(countries)}. "
                     + (f"Zone activity detected: {'; '.join(zones)}." if zones else "No adversary aircraft in monitored chokepoints."))
    else:
        lines.append("ADVERSARY ACTIVITY: No Iranian, Russian, or Chinese military aircraft currently broadcasting ADS-B. This is normal — adversary forces frequently operate with transponders off, particularly during sensitive operations.")

    top_headlines = headlines[:3]
    if top_headlines:
        lines.append("MEDIA SIGNALS: " + " | ".join(top_headlines[:2]))

    lines.append("WATCH: Monitor tanker and ISR aircraft positioning relative to adversary territory. Any increase in adversary aircraft broadcasting combined with tanker surges warrants elevated attention.")

    return "\n\n".join(lines)

def save_and_commit(briefing_data):
    with open(BRIEFING_FILE, "w") as f:
        json.dump(briefing_data, f, indent=2)
    print("  Saved briefing.json")

    try:
        subprocess.run(["git", "add", "briefing.json"],
                       cwd="/root/.openclaw/workspace/mil-tracker", check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"📡 Auto briefing {briefing_data['generated_utc']}"],
                       cwd="/root/.openclaw/workspace/mil-tracker", check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"],
                       cwd="/root/.openclaw/workspace/mil-tracker", check=True, capture_output=True)
        print("  Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"  Git error: {e.stderr.decode() if e.stderr else e}")

def run_once():
    now = datetime.now(timezone.utc)
    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Generating OSINT briefing...")

    print("  Fetching aircraft data...")
    aircraft = fetch_aircraft()
    print(f"  Got {len(aircraft)} aircraft")

    print("  Fetching news...")
    headlines = fetch_news()
    print(f"  Got {len(headlines)} headlines")

    print("  Analyzing...")
    analysis = analyze_aircraft(aircraft)

    print("  Generating briefing text...")
    text = generate_briefing_ai(analysis, headlines)

    briefing = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_ts": int(now.timestamp()),
        "threat_level": "ELEVATED" if (analysis.get("bombers",0)>=1 or analysis.get("zone_activity")) else
                        "GUARDED"  if (analysis.get("tankers",0)>=3 or analysis.get("recon",0)>=2) else "LOW",
        "summary": text,
        "stats": {
            "total": analysis.get("total",0),
            "counts": analysis.get("counts",{}),
            "types": analysis.get("types",{}),
            "adversary_active": len(analysis.get("adversary_details",[])),
            "zones_active": len(analysis.get("zone_activity",[])),
            "zone_names": analysis.get("zone_activity",[]),
        }
    }

    save_and_commit(briefing)
    print(f"  Done. Threat: {briefing['threat_level']}")
    return briefing

if __name__ == "__main__":
    # Run immediately, then every 60 minutes
    print("PikeClaw OSINT Briefing Daemon starting...")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"  ERROR: {e}")
        print("  Sleeping 60 minutes...")
        time.sleep(3600)
