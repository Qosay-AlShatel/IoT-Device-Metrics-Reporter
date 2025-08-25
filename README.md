# IoT Device Metrics Reporter

A minimal system where Linux-based IoT devices collect **system** and **network** metrics and report them to a central **Monitoring Server**. The project includes:
- One **host agent** (runs via `systemd` on the VM)
- One **containerized agent** (runs via Docker)
- A **Flask** monitoring server (Dockerized) with a simple auto-refreshing web dashboard

The dashboard shows current metrics and online/offline status for each device.

---

## Features

- **Agent (Python, stdlib only)**  
  - Collects: Device ID, Uptime, CPU%, Mem%, Disk%, Load Average  
  - Network: Default Interface, IP, MAC, RX/TX Bytes, RX/TX Packets  
  - Posts JSON to the server on a fixed interval

- **Monitoring Server (Flask)**  
  - `POST /metrics` to ingest device payloads  
  - `GET /` HTML dashboard (auto-refreshes via `GET /devices`)  
  - `GET /devices` JSON used by the dashboard  
  - `GET /health` health probe  
  - Online/offline computed from last-seen vs. report interval

- **Containerization**  
  - Dockerfiles for server and agent  
  - Docker Compose for orchestration (server + container agent)

---

## Project Structure

iot-metrics/
├─ agent/
│ ├─ agent.py
│ └─ Dockerfile
├─ server/
│ ├─ app.py
│ ├─ templates/
│ │ └─ index.html
│ └─ Dockerfile
└─ docker-compose.yml


---

## Prerequisites

- Ubuntu 22.04 (or similar Linux)
- Docker Engine
- Docker Compose v2 (`docker compose version` should work)

> If using Compose v1, replace `docker compose` with `docker-compose`.

---

## Quick Start (server + one container agent)

```bash
# From the project root
docker compose up -d --build

# Check server health
curl -s http://localhost:8000/health
# → {"status":"ok"}

# Open the dashboard in a browser:
# http://localhost:8000


Services started

server → Flask server exposed on localhost:8000

agent → containerized device agent posting metrics periodically

Containers are configured with restart: always so they come back after reboot (once Docker starts).

Host Agent (systemd)

Install the host-side agent as a Linux service (second agent):

# Copy the agent to a stable location
sudo mkdir -p /opt/metrics-agent
sudo cp ./agent/agent.py /opt/metrics-agent/
sudo chmod +x /opt/metrics-agent/agent.py

# Create and enable the service
sudo tee /etc/systemd/system/metrics-agent.service > /dev/null <<'EOF'
[Unit]
Description=IoT Metrics Agent (host)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/metrics-agent/agent.py \
  --server http://localhost:8000 \
  --interval 10 \
  --device-id HOST-001
WorkingDirectory=/opt/metrics-agent
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now metrics-agent

# Verify
systemctl status metrics-agent --no-pager

Open the dashboard again—you should see HOST-001 (host) and ctr-001 (container) online.

Configuration

Agent flags

--server (default: http://localhost:8000)

--interval seconds (default: 10)

--device-id (default: derived from machine-id or hostname)

Online/Offline logic

A device is Online if it reported within roughly 2 × interval; otherwise Offline.

Endpoints

POST /metrics → device payload (JSON)

GET / → HTML dashboard (auto-refreshing)

GET /devices → JSON for the dashboard’s table refresh

GET /health → {"status":"ok"}

Troubleshooting

Docker permissions
Add your user to the docker group and reload membership:

sudo usermod -aG docker $USER
newgrp docker

Port 8000 already in use
Stop old processes or containers using that port:

pkill -f "python server/app.py" || true
docker compose down --remove-orphans
docker compose up -d --build

Agents not visible
Check logs and health:

docker compose logs -f server
docker compose logs -f agent
curl -s http://localhost:8000/health

After reboot

Containers: restart: always brings them back once Docker starts.

Host agent: systemd service auto-starts on boot.

Notes

Agent uses only Linux facilities (/proc, /sys, ip) and Python standard library.

The server keeps the latest device state in memory (no DB required).

The dashboard auto-refreshes every 5 seconds.
