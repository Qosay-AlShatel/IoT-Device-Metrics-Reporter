#!/usr/bin/env python3
# Minimal device agent: collect system/network metrics and POST them to the server.
import argparse, json, socket, subprocess, time, urllib.request, urllib.error

def sh(cmd_list):
    # Run a command and return stdout (string)
    return subprocess.check_output(cmd_list, stderr=subprocess.DEVNULL).decode().strip()

def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default

def epoch():
    return int(time.time())

# -------- system metrics --------

def uptime_s():
    # /proc/uptime: "<uptime> <idle>"
    try:
        return float(read("/proc/uptime").split()[0])
    except Exception:
        return 0.0

def loadavg():
    # /proc/loadavg: "x y z ..."
    try:
        a, b, c, *_ = read("/proc/loadavg").split()
        return [float(a), float(b), float(c)]
    except Exception:
        return [0.0, 0.0, 0.0]

def mem_pct():
    # Use MemTotal/MemAvailable from /proc/meminfo
    try:
        mm = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")[0], line.split(":")[1].strip()
                mm[k] = int(v.split()[0])  # kB
        tot = float(mm.get("MemTotal", 1))
        ava = float(mm.get("MemAvailable", 0))
        return round((1.0 - ava / max(tot, 1)) * 100.0, 2)
    except Exception:
        return 0.0

def disk_pct(mount="/"):
    # Parse "Use%" from df -P
    try:
        line = sh(["df", "-P", mount]).splitlines()[1]
        return int(line.split()[4].rstrip("%"))
    except Exception:
        return 0

def _read_proc_stat():
    # Read first "cpu" line from /proc/stat to derive CPU%
    with open("/proc/stat") as f:
        parts = f.readline().split()
    vals = list(map(int, parts[1:])) + [0] * 10
    user, nice, system, idle, iowait, irq, softirq, steal, *_ = vals
    idle_all = idle + iowait
    total = idle_all + user + nice + system + irq + softirq + steal
    return total, idle_all

def cpu_pct(delay=0.5):
    # CPU% from two /proc/stat samples
    try:
        t1, i1 = _read_proc_stat(); time.sleep(delay); t2, i2 = _read_proc_stat()
        td, idl = (t2 - t1), (i2 - i1)
        return round((1 - idl / max(td, 1)) * 100.0, 2)
    except Exception:
        return 0.0

# -------- network metrics --------

def default_iface():
    # Find interface on default route
    try:
        out = sh(["ip", "route", "show", "default"])
        parts = out.split()
        return parts[parts.index("dev") + 1] if "dev" in parts else ""
    except Exception:
        return ""

def ip_of(iface):
    if not iface:
        return ""
    try:
        out = sh(["ip", "-o", "-4", "addr", "show", "dev", iface])
        return out.split()[3].split("/")[0]
    except Exception:
        return ""

def mac_of(iface):
    return read(f"/sys/class/net/{iface}/address", "") if iface else ""

def nic_stats(iface):
    # Kernel counters (ever-increasing totals)
    if not iface:
        return 0, 0, 0, 0
    rb = int(read(f"/sys/class/net/{iface}/statistics/rx_bytes", "0"))
    tb = int(read(f"/sys/class/net/{iface}/statistics/tx_bytes", "0"))
    rp = int(read(f"/sys/class/net/{iface}/statistics/rx_packets", "0"))
    tp = int(read(f"/sys/class/net/{iface}/statistics/tx_packets", "0"))
    return rb, tb, rp, tp

def device_id(prefer=None):
    if prefer:
        return prefer
    mid = read("/etc/machine-id")
    return f"dev-{mid[:12]}" if mid else (socket.gethostname() or "unknown")

# -------- http --------

def post_json(url, payload, timeout=5.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()

def collect(dev_id, interval):
    # Gather one sample
    iface = default_iface()
    rb, tb, rp, tp = nic_stats(iface)
    return {
        "device_id": dev_id,
        "ts": epoch(),
        "interval": interval,
        "system": {
            "uptime_s": round(uptime_s(), 1),
            "cpu_pct": cpu_pct(0.5),
            "mem_pct": mem_pct(),
            "disk_pct": disk_pct("/"),
            "loadavg": loadavg(),
        },
        "network": {
            "iface": iface,
            "ip": ip_of(iface),
            "mac": mac_of(iface),
            "rx_bytes": rb,
            "tx_bytes": tb,
            "rx_packets": rp,
            "tx_packets": tp,
        },
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--device-id", default=None)
    a = ap.parse_args()

    url = a.server.rstrip("/") + "/metrics"
    interval = max(3, a.interval)
    dev = device_id(a.device_id)

    print(f"[agent] start dev={dev} -> {url} every {interval}s")
    while True:
        payload = collect(dev, interval)
        try:
            post_json(url, payload)
            print(f"[agent] sent ts={payload['ts']} cpu={payload['system']['cpu_pct']} mem={payload['system']['mem_pct']}")
            time.sleep(interval)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            # Basic retry on transient network issues
            print(f"[agent] http error: {e}; retrying...")
            for back in (2, 4, 8):
                time.sleep(back)
                try:
                    post_json(url, payload)
                    print(f"[agent] retry ok after {back}s")
                    break
                except Exception:
                    continue
        except Exception as e:
            print(f"[agent] error: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    main()
