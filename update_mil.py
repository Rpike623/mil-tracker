import json
import os
from datetime import datetime

# Path to the data file
data_path = 'data/intel-data.json'

with open(data_path, 'r') as f:
    data = json.load(f)

# Update Generated Time
data['generated_utc'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

# 1. Update Breaking Alert
data['breaking_alert'] = "DAY 5: 12 US KIA TOTAL IN IRAN CONFLICT — ISRAELI F-35 DOWNS IRANIAN YAK-130 OVER TEHRAN"

# 2. Update Ground Intel / Threat Indicators
data['ground_intel'] = {
    "ground_buildup": 5,
    "naval_concentration": 5,
    "active_conflict_count": 5,
    "nuclear_posture": 4,
    "diplomatic_breakdown": 5
}

data['_threat_indicators'] = {
    "manual_override": "DEFCON_1",
    "breaking_events": [
        "12 US personnel confirmed KIA in operations against Iran (Mar 4 total)",
        "Israeli F-35 downs Iranian Yak-130 jet over Tehran — first air-to-air kill",
        "US Submarine sinks Iranian Frigate IRIS Dena off Sri Lanka coast",
        "IRGC Quds Force Lebanon Corps commander Daoud Alizadeh killed",
        "Iran Death Toll: ~1,045 civilian / 1,300+ military deaths estimated",
        "Israel Death Toll: 12 civilian / ~1,274 injured from missile barrages",
        "Hormuz Status: BLOCKADE — IRGC fires on tankers, Brent Crude at $82.42",
        "Cyber: US activates Op Silent Thunder against Iranian grid attacks",
        "Internal: Khamenei funeral begins; Son targeted by assassination warnings",
        "Lebanon: IDF ground units crossing border for 'protection zones'"
    ]
}

# 3. Update Conflicts
for conflict in data['conflicts']:
    if "Ukraine" in conflict['name']:
        conflict['status'] = "WAR OF ATTRITION"
        conflict['intensity'] = "HIGH"
    if "Gaza" in conflict['name']:
        conflict['intensity'] = "HIGH"
    if "Red Sea" in conflict['name']:
        conflict['intensity'] = "HIGH"
        conflict['status'] = "BLOCKADE ACTIVE"
    if "Hezbollah" in conflict['name']:
        conflict['intensity'] = "HIGH"
        conflict['status'] = "FULL SCALE ESCALATION"
    if "Iran-Israel" in conflict['name']:
        conflict['intensity'] = "HIGH"
        conflict['status'] = "ACTIVE COMBAT / DAY 5"
        conflict['summary'] = "Operation Epic Fury (US) and Operation Roaring Lion (Israel) entering total air dominance phase. Regime change objectives stated."

# 4. Update Chokepoints
for cp in data['chokepoints']:
    if "Hormuz" in cp['name']:
        cp['status'] = "CRITICAL BLOCKADE"
        cp['note'] = "IRGC firing on tankers. Brent at $82.42. US providing military escorts."
    if "Bab el-Mandeb" in cp['name']:
        cp['status'] = "HIGH RISK"
    if "Taiwan Strait" in cp['name']:
        cp['status'] = "WATCH"

# 5. Update Naval Deployments (General updates based on data)
# Add the Sri Lanka sinking info etc.
# Note: Keep existing carrier data but update notes
for naval in data['naval_deployments']:
    if "Lincoln" in naval['name']:
        naval['status'] = "combat"
        naval['notes'] = "Conducting strikes on Southern Iran — F-35C sorties active"
    if naval['name'] == "IRIS Dena":
        naval['status'] = "sunk"
        naval['notes'] = "Sunk by US Submarine off Sri Lanka coast (Mar 4)"

# Save back
with open(data_path, 'w') as f:
    json.dump(data, f, indent=2)

print("Intel data updated successfully.")
