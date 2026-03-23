#!/bin/bash
# Auto-sync napcore changes to GitHub
cd /root/.openclaw/workspace/napcore

git add -A
if ! git diff --cached --quiet 2>/dev/null; then
    CHANGED=$(git diff --cached --name-only | head -3 | tr '\n' ', ' | sed 's/,$//')
    git commit -m "🔄 Auto-sync: $CHANGED" --author="造梦者ZERO <suanrongbaicai@users.noreply.github.com>" 2>/dev/null
    timeout 30 git push origin main 2>/dev/null
    echo "Synced: $CHANGED"
else
    echo "No changes"
fi
