#!/bin/bash
# update_mitre_data.sh — Regenerate MITRE ATT&CK and D3FEND data files
# Intended to be run via cron on the Docker host.
# Runs generator scripts inside the backend container, then restarts it
# so the new data modules are loaded.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="$SCRIPT_DIR/data/mitre_update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting MITRE data update..." >> "$LOG_FILE"

# Run ATT&CK generator
if docker compose exec -T backend python scripts/generate_mitre_attack_data.py >> "$LOG_FILE" 2>&1; then
    echo "[$TIMESTAMP] ATT&CK data updated successfully" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] ERROR: ATT&CK data update failed" >> "$LOG_FILE"
fi

# Run D3FEND generator
if docker compose exec -T backend python scripts/generate_d3fend_data.py >> "$LOG_FILE" 2>&1; then
    echo "[$TIMESTAMP] D3FEND data updated successfully" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] ERROR: D3FEND data update failed" >> "$LOG_FILE"
fi

# Restart backend to load new data modules
echo "[$TIMESTAMP] Restarting backend to load updated data..." >> "$LOG_FILE"
docker compose restart backend >> "$LOG_FILE" 2>&1

echo "[$TIMESTAMP] MITRE data update complete" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
