"""Per-container CPU / memory / health metrics for the Docker Compose stack.

cAdvisor cannot see individual containers on Docker Desktop (WSL2 cgroup layout), so this tiny
exporter reads the Docker Engine API instead and exposes cAdvisor-compatible series, which the
Grafana *Infrastructure health* dashboard uses unchanged:

  container_cpu_usage_seconds_total{container_label_com_docker_compose_service,name}
  container_memory_working_set_bytes{...}
  container_spec_memory_limit_bytes{...}
  container_last_seen{...}                    unix time, for every running container
  container_health_status{...,status}         1 for the current Docker health state
  container_restart_count{...}

Only containers of this Compose project (label com.docker.compose.project) are reported.
Standard library only; mounts /var/run/docker.sock READ-ONLY and is not exposed outside the
internal network.
"""
import http.client
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

SOCK = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
PROJECT = os.environ.get("COMPOSE_PROJECT", "")
PORT = int(os.environ.get("PORT", "9417"))


class _UnixConn(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("docker", timeout=10)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(SOCK)


def _get(path):
    c = _UnixConn()
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        if r.status != 200:
            raise RuntimeError(f"{path}: HTTP {r.status}")
        return json.loads(body)
    finally:
        c.close()


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _sample(c):
    cid = c["Id"]
    st = _get(f"/containers/{cid}/stats?stream=false&one-shot=true")
    ins = _get(f"/containers/{cid}/json")
    mem = st.get("memory_stats") or {}
    stats = mem.get("stats") or {}
    usage = mem.get("usage") or 0
    inactive = stats.get("inactive_file", stats.get("total_inactive_file", 0)) or 0
    health = ((ins.get("State") or {}).get("Health") or {}).get("Status") or "none"
    return {
        "service": (c.get("Labels") or {}).get("com.docker.compose.service", ""),
        "name": (c.get("Names") or ["?"])[0].lstrip("/"),
        "cpu": ((st.get("cpu_stats") or {}).get("cpu_usage") or {}).get("total_usage", 0) / 1e9,
        "mem": max(0, usage - inactive),
        "limit": mem.get("limit") or 0,
        "health": health,
        "restarts": ins.get("RestartCount", 0),
    }


def collect() -> str:
    flt = quote(json.dumps({"label": [f"com.docker.compose.project={PROJECT}"]} if PROJECT else {}))
    containers = _get(f"/containers/json?filters={flt}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for r in pool.map(_safe_sample, containers) if r]
    now = time.time()
    out = [
        "# HELP container_cpu_usage_seconds_total Cumulative CPU time consumed (docker stats).",
        "# TYPE container_cpu_usage_seconds_total counter",
    ]
    lines = {"cpu": [], "mem": [], "limit": [], "seen": [], "health": [], "restarts": []}
    for r in rows:
        lab = f'container_label_com_docker_compose_service="{_esc(r["service"])}",name="{_esc(r["name"])}"'
        lines["cpu"].append(f"container_cpu_usage_seconds_total{{{lab}}} {r['cpu']:.6f}")
        lines["mem"].append(f"container_memory_working_set_bytes{{{lab}}} {r['mem']}")
        lines["limit"].append(f"container_spec_memory_limit_bytes{{{lab}}} {r['limit']}")
        lines["seen"].append(f"container_last_seen{{{lab}}} {now:.3f}")
        for s in ("healthy", "unhealthy", "starting", "none"):
            lines["health"].append(f'container_health_status{{{lab},status="{s}"}} {1 if r["health"] == s else 0}')
        lines["restarts"].append(f"container_restart_count{{{lab}}} {r['restarts']}")
    out += lines["cpu"]
    out += ["# TYPE container_memory_working_set_bytes gauge", *lines["mem"],
            "# TYPE container_spec_memory_limit_bytes gauge", *lines["limit"],
            "# TYPE container_last_seen gauge", *lines["seen"],
            "# TYPE container_health_status gauge", *lines["health"],
            "# TYPE container_restart_count gauge", *lines["restarts"],
            "# TYPE docker_stats_exporter_containers gauge", f"docker_stats_exporter_containers {len(rows)}"]
    return "\n".join(out) + "\n"


def _safe_sample(c):
    try:
        return _sample(c)
    except Exception:  # container vanished between list and stats
        return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/healthz"):
            body, code = b"ok\n", 200
        elif self.path.startswith("/metrics"):
            try:
                body, code = collect().encode(), 200
            except Exception as exc:
                body, code = f"# collection failed: {exc}\n".encode(), 500
        else:
            body, code = b"not found\n", 404
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet: Prometheus scrapes every 15 s
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
