from flask import Flask, request, jsonify, render_template
import time

app = Flask(__name__)

# Latest device state kept in memory: {device_id: {"metrics": {}, "last_seen": int, "interval": int}}
DEVICES = {}
REPORT_INTERVAL_DEFAULT = 10  # seconds

def mark_online_state(now: int, last_seen: int, interval: int) -> bool:
    # Consider a device online if it reported within ~2× its configured interval
    return (now - last_seen) <= (2 * max(interval, REPORT_INTERVAL_DEFAULT))

def human_ago(seconds: int) -> str:
    # Compact "x ago" string for the UI
    if seconds < 60:
        return f"{seconds}s ago"
    mins = seconds // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h {mins % 60}m ago"
    days = hrs // 24
    return f"{days}d ago"

@app.route("/metrics", methods=["POST"])
def metrics():
    # Ingest metrics from agents (JSON)
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    # Minimal schema check
    for k in ("device_id", "ts", "system", "network"):
        if k not in payload:
            return jsonify({"error": f"missing field: {k}"}), 400

    device_id = str(payload["device_id"])
    ts = int(payload["ts"])
    interval = int(payload.get("interval", REPORT_INTERVAL_DEFAULT))

    DEVICES[device_id] = {"metrics": payload, "last_seen": ts, "interval": interval}
    return jsonify({"status": "ok"})

def build_rows():
    # Flatten stored metrics for the dashboard and JSON endpoint
    now = int(time.time())
    rows = []
    for device_id, rec in sorted(DEVICES.items()):
        last_seen = int(rec["last_seen"])
        interval = int(rec.get("interval", REPORT_INTERVAL_DEFAULT))
        online = mark_online_state(now, last_seen, interval)
        m = rec["metrics"]
        sysm = m.get("system", {})
        netm = m.get("network", {})
        rows.append({
            "device_id": device_id,
            "online": online,
            "last_seen": last_seen,
            "last_seen_ago": human_ago(max(0, now - last_seen)),
            "uptime_s": sysm.get("uptime_s"),
            "cpu_pct": sysm.get("cpu_pct"),
            "mem_pct": sysm.get("mem_pct"),
            "disk_pct": sysm.get("disk_pct"),
            "loadavg": sysm.get("loadavg"),
            "iface": netm.get("iface"),
            "ip": netm.get("ip"),
            "mac": netm.get("mac"),
            "rx_bytes": netm.get("rx_bytes"),
            "tx_bytes": netm.get("tx_bytes"),
            "rx_packets": netm.get("rx_packets"),
            "tx_packets": netm.get("tx_packets"),
        })
    return rows, now

@app.route("/")
def index():
    # HTML dashboard
    rows, now = build_rows()
    return render_template("index.html", rows=rows, now=now)

@app.route("/devices")
def devices():
    # JSON used by the auto-refreshing dashboard
    rows, now = build_rows()
    return jsonify(rows=rows, now=now)

@app.route("/health")
def health():
    # Simple health probe
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Bind on all interfaces for Docker; port 8000 per compose
    app.run(host="0.0.0.0", port=8000, debug=True)
