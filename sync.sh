#!/bin/bash
# Auto-sync napcore changes to GitHub via API
# Requires: GITHUB_TOKEN env var

REPO="suanrongbaicai/napcore-pro"
BRANCH="main"
TOKEN="${GITHUB_TOKEN}"
DIR="${DATA_DIR:-$(cd "$(dirname "$0")" && pwd)}"

if [ -z "$TOKEN" ]; then
  echo "GITHUB_TOKEN not set, skipping sync"
  exit 0
fi

for FILE in index.html changelog.json contributions.json counter.json feedback.json; do
  [ -f "$DIR/$FILE" ] || continue

  # Get current SHA from GitHub
  SHA=$(curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/$REPO/contents/$FILE" | \
    python3 -c "import json,sys; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null)

  [ -z "$SHA" ] && continue

  # Encode and commit
  CONTENT=$(base64 -w0 "$DIR/$FILE")
  curl -s -X PUT -H "Authorization: token $TOKEN" \
    -H "Content-Type: application/json" \
    "https://api.github.com/repos/$REPO/contents/$FILE" \
    -d "{\"message\":\"🔄 Auto-sync $FILE\",\"content\":\"$CONTENT\",\"sha\":\"$SHA\",\"branch\":\"$BRANCH\"}" > /dev/null 2>&1

  echo "Synced: $FILE"
done
