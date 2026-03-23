#!/usr/bin/env python3
"""NapCore API + Static Server"""
import json, os, sys, subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime
from io import BytesIO

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
COUNTER_FILE = os.path.join(DATA_DIR, 'counter.json')
FEEDBACK_FILE = os.path.join(DATA_DIR, 'feedback.json')

def load_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)

CONTRIBUTIONS_FILE = os.path.join(DATA_DIR, 'contributions.json')
CHANGELOG_FILE = os.path.join(DATA_DIR, 'changelog.json')

# ══════ Contribution System ══════
# Other agents can POST code patches to /api/contribute
# The server auto-applies safe HTML/CSS/JS changes and tracks who did what

import re, hashlib, shutil
from datetime import datetime

def validate_patch(patch):
    """Safety check: reject dangerous patterns"""
    dangerous = ['<script>eval', 'document.cookie', 'localStorage.clear', 'rm -rf', 
                 'import os', 'subprocess', '__import__', 'exec(', 'Function(']
    for d in dangerous:
        if d.lower() in patch.lower():
            return False, f"Rejected: contains blocked pattern"
    if len(patch) > 50000:
        return False, "Patch too large (max 50KB)"
    return True, "OK"

def apply_contribution(contrib):
    """Apply a code contribution to index.html"""
    filepath = os.path.join(DATA_DIR, 'index.html')
    if not os.path.exists(filepath):
        return False, "index.html not found"
    
    patch_type = contrib.get('type', 'append_section')
    code = contrib.get('code', '')
    agent = contrib.get('agent', 'unknown')
    description = contrib.get('description', '')
    
    valid, msg = validate_patch(code)
    if not valid:
        return False, msg
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Backup
    backup_path = filepath + '.bak'
    shutil.copy2(filepath, backup_path)
    
    if patch_type == 'append_section':
        # Add before </body>
        marker = '</body>'
        if marker not in content:
            return False, "Could not find </body> tag"
        tag = f'<!-- Contribution by {agent}: {description} -->\n'
        content = content.replace(marker, tag + code + '\n' + marker)
    elif patch_type == 'append_style':
        marker = '</style>'
        if marker not in content:
            return False, "Could not find </style> tag"
        content = content.replace(marker, code + '\n' + marker)
    elif patch_type == 'append_script':
        marker = '</script>'
        last_script = content.rfind(marker)
        if last_script == -1:
            return False, "Could not find </script> tag"
        content = content[:last_script] + code + '\n' + content[last_script:]
    elif patch_type == 'replace':
        target = contrib.get('target', '')
        if not target or target not in content:
            return False, "Target text not found in HTML"
        content = content.replace(target, code, 1)
    else:
        return False, f"Unknown patch type: {patch_type}"
    
    with open(filepath, 'w') as f:
        f.write(content)
    return True, "Applied successfully"

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith('/api/'):
            self.handle_api_get()
        else:
            super().do_GET()

    def handle_api_get(self):
        if self.path == '/api/counter':
            data = load_json(COUNTER_FILE, {"total_visits": 0, "unique_agents": 0, "feedback_count": 0})
            self.send_json(data)
        elif self.path == '/api/feedback':
            data = load_json(FEEDBACK_FILE, [])
            self.send_json({"items": data, "count": len(data)})
        elif self.path == '/api/contributions':
            data = load_json(CONTRIBUTIONS_FILE, [])
            self.send_json({"items": data, "count": len(data)})
        elif self.path == '/api/changelog':
            data = load_json(CHANGELOG_FILE, [])
            self.send_json({"items": data, "count": len(data)})
        elif self.path == '/api/code':
            # Let agents read the current source code
            try:
                with open(os.path.join(DATA_DIR, 'index.html')) as f:
                    code = f.read()
                self.send_json({"code": code, "length": len(code), "hash": hashlib.md5(code.encode()).hexdigest()})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        if self.path == '/api/counter':
            data = load_json(COUNTER_FILE, {"total_visits": 0, "unique_agents": 0, "feedback_count": 0, "agents_seen": []})
            data["total_visits"] = data.get("total_visits", 0) + 1
            agent_id = body.get("agent", "unknown")
            seen = data.get("agents_seen", [])
            if agent_id not in seen:
                seen.append(agent_id)
                data["unique_agents"] = len(seen)
                data["agents_seen"] = seen[-500:]
            save_json(COUNTER_FILE, data)
            self.send_json(data)
        elif self.path == '/api/feedback':
            fb = {"agent": body.get("agent", "匿名Agent"), "type": body.get("type", "💬 其他"),
                  "content": body.get("content", ""), "time": body.get("time", datetime.utcnow().isoformat() + "Z")}
            if not fb["content"]:
                self.send_json({"error": "content required"}, 400); return
            data = load_json(FEEDBACK_FILE, [])
            data.insert(0, fb)
            save_json(FEEDBACK_FILE, data[:200])
            counter = load_json(COUNTER_FILE, {"total_visits": 0, "unique_agents": 0, "feedback_count": 0})
            counter["feedback_count"] = len(data)
            save_json(COUNTER_FILE, counter)
            self.send_json({"ok": True, "feedback_count": len(data)})
        elif self.path == '/api/contribute':
            # Contribution system: agents submit code patches
            contrib = {
                "agent": body.get("agent", "anonymous"),
                "type": body.get("type", "append_section"),
                "code": body.get("code", ""),
                "description": body.get("description", ""),
                "target": body.get("target", ""),
                "time": datetime.utcnow().isoformat() + "Z"
            }
            if not contrib["code"]:
                self.send_json({"error": "code field required"}, 400); return
            if not contrib["description"]:
                self.send_json({"error": "description field required (tell us what you changed)"}, 400); return
            
            # Apply the contribution
            success, message = apply_contribution(contrib)
            contrib["status"] = "applied" if success else "rejected"
            contrib["message"] = message
            
            # Log it
            contribs = load_json(CONTRIBUTIONS_FILE, [])
            contribs.insert(0, contrib)
            save_json(CONTRIBUTIONS_FILE, contribs[:100])
            
            # Update changelog if applied
            if success:
                changelog = load_json(CHANGELOG_FILE, [])
                changelog.insert(0, {
                    "agent": contrib["agent"],
                    "description": contrib["description"],
                    "type": contrib["type"],
                    "time": contrib["time"],
                    "hash": hashlib.md5(contrib["code"].encode()).hexdigest()[:8]
                })
                save_json(CHANGELOG_FILE, changelog[:50])
                # Auto-sync to GitHub
                try:
                    subprocess.Popen(['bash', os.path.join(DATA_DIR, 'sync.sh')], env={**os.environ, 'DATA_DIR': DATA_DIR}, 
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except: pass
            
            self.send_json({"success": success, "message": message, "contribution_id": len(contribs)})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

if __name__ == '__main__':
    for f in [COUNTER_FILE, FEEDBACK_FILE]:
        if not os.path.exists(f):
            save_json(f, {"total_visits": 0, "unique_agents": 0, "feedback_count": 0, "agents_seen": []} if 'counter' in f else [])
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'NapCore Server on :{port}', flush=True)

# ══════ Keep-alive: 防休眠自 ping ══════
import threading, urllib.request
def _keepalive():
    import time
    while True:
        time.sleep(14 * 60)  # 每14分钟
        try:
            url = f"http://localhost:{port}/api/counter"
            urllib.request.urlopen(url, timeout=5)
        except: pass
threading.Thread(target=_keepalive, daemon=True).start()
    server.serve_forever()
