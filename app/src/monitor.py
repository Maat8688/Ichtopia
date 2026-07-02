#!/usr/bin/env python3
import re
import time
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import threading
import json
import urllib.request
import os

# =========================
# CONFIG
# =========================

# Path to your Flask / Werkzeug access log
# LOG_PATH = Path("/app/logs/access.log")  # <-- change this

def resolve_log_path() -> Path:
    here = Path(__file__).resolve().parents[1]  # app/src -> app
    env = os.getenv("ACCESS_LOG_PATH") or os.getenv("LOG_PATH")
    candidates = []
    if env:
        candidates.append(Path(env))

    # project-relative (when running on host)
    candidates += [
        here / "log" / "access.log",
        here / "logs" / "access.log",
    ]

    # common container paths
    candidates += [
        Path("/app/log/access.log"),
        Path("/app/logs/access.log"),
        Path("/var/log/flask_app/access.log"),
    ]

    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue

    # fallback — create project-relative log file
    fallback = here / "log" / "access.log"
    try:
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.touch(exist_ok=True)
    except Exception:
        pass
    return fallback

LOG_PATH = resolve_log_path()

# Time window for analysis (seconds)
WINDOW_SECONDS = 300  # 5 minutes

# Score threshold for raising an alert
SCORE_THRESHOLD = 6

# Minimum time between alerts for the same IP (seconds)
ALERT_COOLDOWN = 300  # 5 minutes

# Request-rate threshold (per second) considered "high"
HIGH_RATE_THRESHOLD = 1.0  # >1 req/sec averaged over WINDOW_SECONDS

# Threshold for "many different paths" probing
MANY_PATHS_THRESHOLD = 20

# Optional: Discord webhook for alerts (leave empty to disable)
DISCORD_WEBHOOK_URL = ""  # e.g. "https://discord.com/api/webhooks/...."

# Optional: ntfy for alerts (leave NTFY_TOPIC empty to disable)
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "AK-Leer-129845")

# Suspicious path patterns (regex)
SUSPICIOUS_PATTERNS = [
    r"/\.git",
    r"/admin",
    r"/wp-admin",
    r"/xmlrpc\.php",
    r"/cgi-bin",
    r"/actuator",
    r"/webui",
    r"/luci",
    r"/phpmyadmin",
    r"/\.env",
    r"/config\.php",
    r"/\.htaccess",
]

# Things that often show up in probes or fuzzing
SUSPICIOUS_SUBSTRINGS = [
    "%25",       # encoded %
    "%2e",       # encoded .
    "%2f",       # encoded /
    "../",       # path traversal
    ";stok=",    # luci/routers
    "XDEBUG_SESSION_START",
]


# =========================
# LOG PARSING
# =========================

# Example line:
# 77.160.5.117 - - [06/Nov/2025 15:44:24] "GET / HTTP/1.1" 200 -
WERKZEUG_LINE_RE = re.compile(
    r'(?P<ip>\S+) '          # IP
    r'\S+ \S+ '              # - -
    r'\[(?P<date>.+?)\] '    # [date]
    r'"(?P<method>\S+) '     # "GET
    r'(?P<path>\S+) '        # /something
    r'(?P<protocol>[^"]+)" ' # HTTP/1.1"
    r'(?P<status>\d{3}) '    # 200
    r'(?P<size>\S+)'         # -
)


def parse_werkzeug_line(line: str) -> Dict[str, Any] | None:
    m = WERKZEUG_LINE_RE.search(line)
    if not m:
        return None
    try:
        status = int(m.group("status"))
    except ValueError:
        status = 0
    return {
        "ip": m.group("ip"),
        "date_raw": m.group("date"),
        "method": m.group("method"),
        "path": m.group("path"),
        "protocol": m.group("protocol"),
        "status": status,
        "size": m.group("size"),
    }


# =========================
# SUSPICION LOGIC
# =========================

def is_suspicious_path(path: str) -> bool:
    if any(re.search(pat, path) for pat in SUSPICIOUS_PATTERNS):
        return True
    if any(sub in path for sub in SUSPICIOUS_SUBSTRINGS):
        return True
    if len(path) > 150:  # extremely long URLs are often malicious or fuzzing
        return True
    return False


def compute_score(events: List[Dict[str, Any]]) -> tuple[int, Dict[str, Any]]:
    """
    Compute a suspicion score for an IP based on recent events.
    Returns (score, stats) where stats gives some context for alerts.
    """
    if not events:
        return 0, {}

    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Filter events to current window (should already be done, but be safe)
    events = [e for e in events if e["ts"] >= window_start]
    if not events:
        return 0, {}

    total = len(events)
    statuses = [e["status"] for e in events]
    paths = [e["path"] for e in events]
    unique_paths = len(set(paths))

    # Compute basic stats
    four_xx = sum(1 for s in statuses if 400 <= s < 500)
    five_xx = sum(1 for s in statuses if s >= 500)
    suspicious_paths = sum(1 for e in events if e["suspicious_path"])
    suspicious_recent = events[-1]["suspicious_path"]

    duration = max(1.0, max(e["ts"] for e in events) - min(e["ts"] for e in events))
    req_rate = total / duration

    score = 0

    # Rule 1: Many suspicious paths
    if suspicious_paths >= 1:
        score += 3
    if suspicious_paths >= 3:
        score += 2

    # Rule 2: High error rate
    if four_xx + five_xx >= 5:
        score += 2
    if five_xx >= 1:
        score += 2

    # Rule 3: High request rate
    if req_rate > HIGH_RATE_THRESHOLD:
        score += 3
    elif req_rate > HIGH_RATE_THRESHOLD / 2:
        score += 1

    # Rule 4: Many different paths (probing)
    if unique_paths >= MANY_PATHS_THRESHOLD:
        score += 3
    elif unique_paths >= MANY_PATHS_THRESHOLD // 2:
        score += 1

    # Rule 5: latest event was clearly suspicious
    if suspicious_recent:
        score += 2

    stats = {
        "total": total,
        "four_xx": four_xx,
        "five_xx": five_xx,
        "suspicious_paths": suspicious_paths,
        "unique_paths": unique_paths,
        "req_rate": req_rate,
        "last_path": events[-1]["path"],
        "last_status": events[-1]["status"],
    }

    return score, stats


# =========================
# ALERTING
# =========================

def send_discord_alert(ip: str, score: int, stats: Dict[str, Any]):
    if not DISCORD_WEBHOOK_URL:
        return

    data = {
        "content": (
            f"⚠️ Suspicious activity detected\n"
            f"**IP:** {ip}\n"
            f"**Score:** {score}\n"
            f"**Requests (window):** {stats['total']}\n"
            f"**4xx:** {stats['four_xx']} | **5xx:** {stats['five_xx']}\n"
            f"**Unique paths:** {stats['unique_paths']}\n"
            f"**Req rate:** {stats['req_rate']:.2f} req/s\n"
            f"**Last path:** `{stats['last_path']}` (status {stats['last_status']})"
        )
    }

    def _worker():
        try:
            req = urllib.request.Request(
                DISCORD_WEBHOOK_URL,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            # Silent fail for webhook errors
            pass

    threading.Thread(target=_worker, daemon=True).start()


def send_ntfy_alert(ip: str, score: int, stats: Dict[str, Any]):
    """
    Send a concise alert to ntfy (phone/app/browser).
    """
    print("sending message")
    if not NTFY_TOPIC:
        return

    message = (
        f"[ALERT] Suspicious activity\n"
        f"IP: {ip}\n"
        f"Score: {score}\n"
        f"Reqs: {stats['total']} | 4xx: {stats['four_xx']} | 5xx: {stats['five_xx']}\n"
        f"Unique paths: {stats['unique_paths']} | Rate: {stats['req_rate']:.2f} req/s\n"
        f"Last: {stats['last_path']} (status {stats['last_status']})"
    )

    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"

    def _worker():
        try:
            req = urllib.request.Request(
                url,
                data=message.encode("utf-8"),
                headers={
                    "Title": "Flask suspicious traffic",
                    "Priority": "4",  # 1–5 (ntfy-specific)
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            # Silent fail for ntfy errors
            pass

    threading.Thread(target=_worker, daemon=True).start()


def print_alert(ip: str, score: int, stats: Dict[str, Any]):
    now_str = datetime.utcnow().isoformat() + "Z"
    print("=" * 60)
    print(f"[ALERT] {now_str}")
    print(f"IP: {ip}")
    print(f"Score: {score}")
    print(f"Requests in window: {stats['total']}")
    print(f"4xx: {stats['four_xx']} | 5xx: {stats['five_xx']}")
    print(f"Unique paths: {stats['unique_paths']}")
    print(f"Req rate: {stats['req_rate']:.2f} req/s")
    print(f"Last path: {stats['last_path']} (status {stats['last_status']})")
    print("=" * 60)


# =========================
# TAILING LOG FILE
# =========================

def tail_file(path: Path):
    """
    Generator that yields new lines as they are appended to a file.
    Very basic tail -F style behavior.
    """
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)  # go to end of file
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            yield line


def main():
    if not LOG_PATH.exists():
        print(f"[ERROR] Log file does not exist: {LOG_PATH}")
        return

    # ip -> list of events, each event: {"ts", "path", "status", "suspicious_path"}
    ip_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    last_alert_time: Dict[str, float] = {}

    print(f"[INFO] Monitoring log: {LOG_PATH}")
    print(f"[INFO] Window: {WINDOW_SECONDS}s, Score threshold: {SCORE_THRESHOLD}")

    for line in tail_file(LOG_PATH):
        parsed = parse_werkzeug_line(line)
        if not parsed:
            continue

        ip = parsed["ip"]
        path = parsed["path"]
        status = parsed["status"]
        now = time.time()

        event = {
            "ts": now,
            "path": path,
            "status": status,
            "suspicious_path": is_suspicious_path(path),
        }

        # Add event
        ip_events[ip].append(event)

        # Drop old events outside window
        cutoff = now - WINDOW_SECONDS
        ip_events[ip] = [e for e in ip_events[ip] if e["ts"] >= cutoff]

        # Compute score
        score, stats = compute_score(ip_events[ip])

        # Check alert conditions
        if score >= SCORE_THRESHOLD:
            last = last_alert_time.get(ip, 0)
            if now - last >= ALERT_COOLDOWN:
                last_alert_time[ip] = now
                print_alert(ip, score, stats)
                send_discord_alert(ip, score, stats)
                send_ntfy_alert(ip, score, stats)


if __name__ == "__main__":
    main()
