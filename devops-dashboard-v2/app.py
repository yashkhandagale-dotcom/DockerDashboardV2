from flask import Flask, jsonify, render_template_string, request
import redis
import psutil
import time
import os
from kubernetes import client, config

app = Flask(__name__)

REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# Load K8s config — gracefully degrade if unavailable (e.g. Docker Compose)
k8s_available = False
try:
    config.load_incluster_config()
    k8s_available = True
except Exception:
    try:
        config.load_kube_config()
        k8s_available = True
    except Exception:
        print("⚠️  No Kubernetes config found — K8s features disabled")

if k8s_available:
    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    autoscaling_v2 = client.AutoscalingV2Api()
else:
    v1 = None
    apps_v1 = None
    autoscaling_v2 = None

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>DevOps Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0d1117; color: #c9d1d9; font-family: "Segoe UI", Arial; min-height: 100vh; }
        .header {
            background: linear-gradient(135deg, #161b22, #1f2937);
            padding: 20px 40px;
            border-bottom: 1px solid #30363d;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-left h1 { color: #58a6ff; font-size: 22px; letter-spacing: 1px; }
        .header-left p { color: #8b949e; font-size: 12px; margin-top: 4px; }
        .live-badge {
            background: #1a3a1a; border: 1px solid #3fb950;
            color: #3fb950; padding: 5px 12px; border-radius: 20px;
            font-size: 12px; display: flex; align-items: center; gap: 6px;
        }
        .live-dot {
            width: 8px; height: 8px; background: #3fb950;
            border-radius: 50%; animation: pulse 1.5s infinite;
        }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }

        .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 24px 40px; }
        .grid-wide { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; padding: 0 40px 24px; }
        .grid-triple { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 0 40px 24px; }
        .grid-full { padding: 0 40px 24px; }

        .card {
            background: #161b22; border: 1px solid #30363d;
            border-radius: 12px; padding: 24px;
            transition: border-color 0.3s; position: relative; overflow: hidden;
        }
        .card:hover { border-color: #58a6ff; }
        .card::before {
            content: ""; position: absolute; top: 0; left: 0; right: 0;
            height: 3px; background: linear-gradient(90deg, #58a6ff, #3fb950);
            opacity: 0; transition: opacity 0.3s;
        }
        .card:hover::before { opacity: 1; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .card-title { color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
        .card-icon { font-size: 20px; }
        .metric { font-size: 48px; font-weight: bold; color: #58a6ff; line-height: 1; }
        .metric.green { color: #3fb950; }
        .metric.yellow { color: #d29922; }
        .metric.red { color: #f85149; }
        .metric-label { color: #8b949e; font-size: 12px; margin-top: 8px; }
        .progress-bar { background: #21262d; border-radius: 4px; height: 6px; margin-top: 12px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; background: linear-gradient(90deg, #58a6ff, #3fb950); }
        .progress-fill.yellow { background: linear-gradient(90deg, #d29922, #f0a020); }
        .progress-fill.red { background: linear-gradient(90deg, #f85149, #ff6b6b); }

        .status-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
        .status-item:last-child { border-bottom: none; }
        .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .dot.green { background: #3fb950; box-shadow: 0 0 6px #3fb950; }
        .dot.red { background: #f85149; box-shadow: 0 0 6px #f85149; }
        .dot.yellow { background: #d29922; box-shadow: 0 0 6px #d29922; }
        .status-name { flex: 1; color: #c9d1d9; }
        .status-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #1a3a1a; color: #3fb950; border: 1px solid #2d5a2d; }
        .status-badge.red { background: #3a1a1a; color: #f85149; border-color: #5a2d2d; }

        .pod-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
        .pod-table th { text-align: left; color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; padding: 8px 12px; border-bottom: 1px solid #30363d; }
        .pod-table td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid #21262d; }
        .pod-table tr:last-child td { border-bottom: none; }
        .pod-table tr:hover td { background: #1f2937; }
        .pod-name { color: #58a6ff; font-family: monospace; font-size: 12px; }
        .pod-running { color: #3fb950; }
        .pod-pending { color: #d29922; }
        .pod-failed { color: #f85149; }

        .scale-controls { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
        .scale-btn { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; transition: all 0.2s; }
        .scale-btn:hover:not(:disabled) { background: #58a6ff; color: #0d1117; border-color: #58a6ff; }
        .scale-btn.red:hover:not(:disabled) { background: #f85149; border-color: #f85149; color: #0d1117; }
        .scale-btn:disabled { opacity: 0.35; cursor: not-allowed; }
        .replica-count { font-size: 40px; font-weight: bold; color: #58a6ff; min-width: 50px; text-align: center; }
        .scale-label { color: #8b949e; font-size: 12px; margin-top: 4px; text-align: center; }
        .scale-feedback { font-size: 12px; color: #3fb950; margin-top: 8px; min-height: 18px; text-align: center; }

        .node-info { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; }
        .node-stat { background: #21262d; border-radius: 8px; padding: 12px; }
        .node-stat-label { color: #8b949e; font-size: 11px; text-transform: uppercase; }
        .node-stat-value { color: #58a6ff; font-size: 16px; font-weight: bold; margin-top: 4px; word-break: break-all; }

        .hpa-bar { background: #21262d; border-radius: 8px; padding: 14px; margin-top: 10px; }
        .hpa-row { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px; }
        .hpa-row:last-child { margin-bottom: 0; }
        .hpa-row span:first-child { color: #8b949e; }
        .hpa-row span:last-child { color: #58a6ff; font-weight: bold; }

        .events-list { max-height: 180px; overflow-y: auto; margin-top: 8px; }
        .event-item { padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 12px; display: flex; gap: 8px; }
        .event-item:last-child { border-bottom: none; }
        .event-time { color: #8b949e; white-space: nowrap; }
        .event-msg { color: #c9d1d9; }
        .event-warn { color: #d29922; }

        .footer { text-align: center; padding: 16px 40px; color: #8b949e; font-size: 12px; border-top: 1px solid #21262d; display: flex; justify-content: space-between; }
    </style>
    <script>
        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                const cpu = parseFloat(data.cpu);
                const mem = parseFloat(data.memory);
                const disk = parseFloat(data.disk);

                setMetric('cpu', cpu, cpu + '%');
                setMetric('memory', mem, mem + '%');
                setMetric('disk', disk, disk + '%');

                document.getElementById('requests').textContent = data.requests;
                document.getElementById('uptime').textContent = formatUptime(data.uptime);
                document.getElementById('timestamp').textContent = 'Last updated: ' + new Date().toLocaleTimeString();

                const redisDot = document.getElementById('redis-dot');
                const redisBadge = document.getElementById('redis-badge');
                if (data.redis_ok) {
                    redisDot.className = 'dot green';
                    redisBadge.textContent = 'CONNECTED';
                    redisBadge.className = 'status-badge';
                } else {
                    redisDot.className = 'dot red';
                    redisBadge.textContent = 'DOWN';
                    redisBadge.className = 'status-badge red';
                }
            } catch(e) { console.error(e); }
        }

        function setMetric(id, pct, label) {
            const cls = pct > 80 ? 'red' : pct > 50 ? 'yellow' : 'green';
            document.getElementById(id).textContent = label;
            document.getElementById(id).className = 'metric ' + cls;
            document.getElementById(id + '-bar').style.width = pct + '%';
            document.getElementById(id + '-bar').className = 'progress-fill ' + (cls !== 'green' ? cls : '');
        }

        function formatUptime(s) {
            if (s < 60) return s + 's';
            if (s < 3600) return Math.floor(s/60) + 'm ' + (s%60) + 's';
            return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
        }

        async function fetchK8s() {
            try {
                const res = await fetch('/api/k8s');
                const data = await res.json();
                const k8sDot = document.getElementById('k8s-dot');
                const k8sBadge = document.getElementById('k8s-badge');

                if (data.error && !data.pods.length) {
                    k8sDot.className = 'dot red';
                    k8sBadge.textContent = 'DOWN';
                    k8sBadge.className = 'status-badge red';
                    document.getElementById('replica-count').textContent = 'N/A';
                    document.getElementById('pod-count').textContent = 'K8s unavailable';
                    document.getElementById('pod-tbody').innerHTML =
                        '<tr><td colspan="5" style="color:#8b949e;text-align:center;">Kubernetes not connected</td></tr>';
                    return;
                }

                k8sDot.className = 'dot green';
                k8sBadge.textContent = 'RUNNING';
                k8sBadge.className = 'status-badge';

                document.getElementById('replica-count').textContent = data.replicas;
                document.getElementById('pod-count').textContent = data.pods.length + ' Pods';

                document.getElementById('btn-down').disabled = data.replicas <= 1;
                document.getElementById('btn-up').disabled = data.replicas >= 10;

                document.getElementById('pod-tbody').innerHTML = data.pods.map(pod => `
                    <tr>
                        <td class="pod-name">${pod.name}</td>
                        <td class="${pod.status === 'Running' ? 'pod-running' : pod.status === 'Pending' ? 'pod-pending' : 'pod-failed'}">${pod.status}</td>
                        <td>${pod.ready}</td>
                        <td>${pod.age}</td>
                        <td>${pod.restarts}</td>
                    </tr>
                `).join('');

                document.getElementById('node-name').textContent = data.node.name || 'N/A';
                document.getElementById('node-status').textContent = data.node.status || 'N/A';
                document.getElementById('node-version').textContent = data.node.version || 'N/A';
                document.getElementById('node-pods').textContent = data.node.pods;

                if (data.hpa) {
                    document.getElementById('hpa-section').style.display = 'block';
                    document.getElementById('hpa-min').textContent = data.hpa.min_replicas;
                    document.getElementById('hpa-max').textContent = data.hpa.max_replicas;
                    document.getElementById('hpa-current').textContent = data.hpa.current_replicas;
                    document.getElementById('hpa-cpu-target').textContent = (data.hpa.cpu_target || '--') + (data.hpa.cpu_target ? '%' : '');
                }
            } catch(e) { console.error(e); }
        }

        async function fetchEvents() {
            try {
                const res = await fetch('/api/events');
                const data = await res.json();
                const list = document.getElementById('events-list');
                if (!data.events || !data.events.length) {
                    list.innerHTML = '<div class="event-item"><span class="event-msg" style="color:#8b949e;">No recent events</span></div>';
                    return;
                }
                list.innerHTML = data.events.map(e => `
                    <div class="event-item">
                        <span class="event-time">${e.time}</span>
                        <span class="${e.type === 'Warning' ? 'event-warn' : 'event-msg'}">[${e.type}] ${e.reason}: ${e.message}</span>
                    </div>
                `).join('');
            } catch(e) { console.error(e); }
        }

        async function scaleDeployment(direction) {
            document.getElementById('btn-up').disabled = true;
            document.getElementById('btn-down').disabled = true;
            const feedback = document.getElementById('scale-feedback');
            feedback.style.color = '#8b949e';
            feedback.textContent = 'Scaling...';
            try {
                const res = await fetch('/api/scale', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction})
                });
                const result = await res.json();
                if (result.error) {
                    feedback.style.color = '#f85149';
                    feedback.textContent = 'Error: ' + result.error;
                } else {
                    feedback.style.color = '#3fb950';
                    feedback.textContent = result.message || ('✓ Scaled to ' + result.replicas + ' replica' + (result.replicas !== 1 ? 's' : ''));
                    document.getElementById('replica-count').textContent = result.replicas;
                }
            } catch(e) {
                feedback.style.color = '#f85149';
                feedback.textContent = 'Network error';
            }
            setTimeout(() => { feedback.textContent = ''; fetchK8s(); }, 2500);
        }

        fetchStats();
        fetchK8s();
        fetchEvents();
        setInterval(fetchStats, 3000);
        setInterval(fetchK8s, 5000);
        setInterval(fetchEvents, 15000);
    </script>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>⚡ DevOps Dashboard</h1>
            <p>Real-time K8s monitoring | Flask + Redis + Docker + Kubernetes</p>
        </div>
        <div class="live-badge"><div class="live-dot"></div>LIVE</div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-header"><span class="card-title">CPU Usage</span><span class="card-icon">🖥️</span></div>
            <div class="metric green" id="cpu">--</div>
            <div class="metric-label">Current processor load</div>
            <div class="progress-bar"><div class="progress-fill" id="cpu-bar" style="width:0%"></div></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Memory Usage</span><span class="card-icon">💾</span></div>
            <div class="metric green" id="memory">--</div>
            <div class="metric-label">RAM utilization</div>
            <div class="progress-bar"><div class="progress-fill" id="memory-bar" style="width:0%"></div></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Disk Usage</span><span class="card-icon">💿</span></div>
            <div class="metric green" id="disk">--</div>
            <div class="metric-label">Storage utilization</div>
            <div class="progress-bar"><div class="progress-fill" id="disk-bar" style="width:0%"></div></div>
        </div>
    </div>

    <div class="grid-wide">
        <div class="card">
            <div class="card-header">
                <span class="card-title">☸️ Live Pod Status</span>
                <span id="pod-count" style="color:#3fb950;font-size:13px;">Loading...</span>
            </div>
            <table class="pod-table">
                <thead>
                    <tr><th>Pod Name</th><th>Status</th><th>Ready</th><th>Age</th><th>Restarts</th></tr>
                </thead>
                <tbody id="pod-tbody">
                    <tr><td colspan="5" style="color:#8b949e;text-align:center;">Loading pods...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header"><span class="card-title">🔄 Replica Controller</span><span class="card-icon">⚙️</span></div>
            <div style="text-align:center;">
                <div class="replica-count" id="replica-count">--</div>
                <div class="scale-label">Current Replicas (min: 1, max: 10)</div>
                <div class="scale-controls" style="justify-content:center;margin-top:20px;">
                    <button class="scale-btn red" id="btn-down" onclick="scaleDeployment('down')">▼ Scale Down</button>
                    <button class="scale-btn" id="btn-up" onclick="scaleDeployment('up')">▲ Scale Up</button>
                </div>
                <div class="scale-feedback" id="scale-feedback"></div>
            </div>

            <div id="hpa-section" style="display:none; margin-top:20px;">
                <div class="card-title" style="margin-bottom:8px;">📈 HorizontalPodAutoscaler</div>
                <div class="hpa-bar">
                    <div class="hpa-row"><span>Min Replicas</span><span id="hpa-min">--</span></div>
                    <div class="hpa-row"><span>Max Replicas</span><span id="hpa-max">--</span></div>
                    <div class="hpa-row"><span>Current Replicas</span><span id="hpa-current">--</span></div>
                    <div class="hpa-row"><span>CPU Target</span><span id="hpa-cpu-target">--</span></div>
                </div>
            </div>

            <div style="margin-top:20px;">
                <div class="card-title" style="margin-bottom:8px;">🌐 Node Info</div>
                <div class="node-info">
                    <div class="node-stat"><div class="node-stat-label">Node Name</div><div class="node-stat-value" id="node-name">--</div></div>
                    <div class="node-stat"><div class="node-stat-label">Status</div><div class="node-stat-value" id="node-status">--</div></div>
                    <div class="node-stat"><div class="node-stat-label">K8s Version</div><div class="node-stat-value" id="node-version">--</div></div>
                    <div class="node-stat"><div class="node-stat-label">Total Pods</div><div class="node-stat-value" id="node-pods">--</div></div>
                </div>
            </div>
        </div>
    </div>

    <div class="grid-triple">
        <div class="card">
            <div class="card-header"><span class="card-title">⏱️ App Uptime</span><span class="card-icon">🕐</span></div>
            <div class="metric green" id="uptime">--</div>
            <div class="metric-label">Time since container started</div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">💚 Services Health</span><span class="card-icon">🔧</span></div>
            <div class="status-item"><div class="dot green"></div><span class="status-name">Flask App</span><span class="status-badge">RUNNING</span></div>
            <div class="status-item"><div class="dot green" id="redis-dot"></div><span class="status-name">Redis</span><span class="status-badge" id="redis-badge">CHECKING</span></div>
            <div class="status-item"><div class="dot yellow" id="k8s-dot"></div><span class="status-name">Kubernetes API</span><span class="status-badge" id="k8s-badge">CHECKING</span></div>
            <div class="status-item"><div class="dot green"></div><span class="status-name">Liveness Probe /healthz</span><span class="status-badge">OK</span></div>
            <div class="status-item"><div class="dot green"></div><span class="status-name">Readiness Probe /readyz</span><span class="status-badge">OK</span></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">📊 Total Requests</span><span class="card-icon">📈</span></div>
            <div class="metric" id="requests">--</div>
            <div class="metric-label">API calls tracked via Redis</div>
        </div>
    </div>

    <div class="grid-full">
        <div class="card">
            <div class="card-header">
                <span class="card-title">📣 Kubernetes Events</span>
                <span style="color:#8b949e;font-size:12px;">Last 15 · refreshes every 15s</span>
            </div>
            <div class="events-list" id="events-list">
                <div class="event-item"><span class="event-msg" style="color:#8b949e;">Loading events...</span></div>
            </div>
        </div>
    </div>

    <div class="footer">
        <span>⚡ DevOps Dashboard | Docker + Kubernetes + Flask + Redis</span>
        <span id="timestamp">Loading...</span>
    </div>
</body>
</html>
'''

start_time = time.time()
DEPLOYMENT_NAME = os.environ.get('DEPLOYMENT_NAME', 'devops-dashboard')
NAMESPACE = os.environ.get('NAMESPACE', 'default')
MIN_REPLICAS = 1
MAX_REPLICAS = 10


@app.route('/healthz')
def healthz():
    """Liveness probe endpoint."""
    return jsonify({'status': 'ok'}), 200


@app.route('/readyz')
def readyz():
    """Readiness probe — checks Redis connectivity."""
    try:
        r.ping()
        return jsonify({'status': 'ready'}), 200
    except Exception as e:
        return jsonify({'status': 'not ready', 'error': str(e)}), 503


@app.route('/')
def index():
    try:
        r.incr('requests')
    except Exception:
        pass
    return render_template_string(HTML)


@app.route('/api/stats')
def stats():
    redis_ok = False
    requests_count = 0
    try:
        r.incr('requests')
        requests_count = int(r.get('requests') or 0)
        redis_ok = True
    except Exception:
        pass
    disk = psutil.disk_usage('/')
    return jsonify({
        'cpu': psutil.cpu_percent(interval=0.5),
        'memory': psutil.virtual_memory().percent,
        'disk': round(disk.percent, 1),
        'requests': requests_count,
        'uptime': round(time.time() - start_time),
        'redis_ok': redis_ok,
    })


@app.route('/api/k8s')
def k8s_info():
    if not k8s_available:
        return jsonify({
            'pods': [], 'replicas': 0, 'hpa': None,
            'node': {'name': 'N/A', 'status': 'N/A', 'version': 'N/A', 'pods': 0},
            'error': 'Kubernetes not available in this environment'
        })
    try:
        pods = v1.list_namespaced_pod(
            namespace=NAMESPACE,
            label_selector=f"app={DEPLOYMENT_NAME}"
        )
        pod_list = []
        for pod in pods.items:
            age_seconds = time.time() - pod.metadata.creation_timestamp.timestamp()
            age_minutes = round(age_seconds / 60)
            container_statuses = pod.status.container_statuses or []
            restarts = sum(cs.restart_count for cs in container_statuses)
            ready_count = sum(1 for cs in container_statuses if cs.ready)
            total_containers = max(len(container_statuses), 1)
            pod_list.append({
                'name': pod.metadata.name[-28:],
                'status': pod.status.phase or 'Unknown',
                'ready': f"{ready_count}/{total_containers}",
                'age': f"{age_minutes}m" if age_minutes < 60 else f"{age_minutes // 60}h{age_minutes % 60}m",
                'restarts': restarts,
            })

        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE
        )
        replicas = deployment.spec.replicas

        nodes = v1.list_node()
        node = nodes.items[0]
        node_conditions = {c.type: c.status for c in (node.status.conditions or [])}
        node_status = 'Ready' if node_conditions.get('Ready') == 'True' else 'NotReady'

        hpa_info = None
        try:
            hpa_list = autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE)
            for hpa in hpa_list.items:
                if hpa.spec.scale_target_ref.name == DEPLOYMENT_NAME:
                    cpu_target = None
                    for metric in (hpa.spec.metrics or []):
                        if metric.type == 'Resource' and metric.resource.name == 'cpu':
                            cpu_target = metric.resource.target.average_utilization
                    hpa_info = {
                        'min_replicas': hpa.spec.min_replicas,
                        'max_replicas': hpa.spec.max_replicas,
                        'current_replicas': hpa.status.current_replicas,
                        'cpu_target': cpu_target,
                    }
                    break
        except Exception:
            pass

        return jsonify({
            'pods': pod_list,
            'replicas': replicas,
            'node': {
                'name': node.metadata.name,
                'status': node_status,
                'version': node.status.node_info.kubelet_version,
                'pods': len(pod_list),
            },
            'hpa': hpa_info,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'pods': [], 'replicas': 0, 'node': {}, 'hpa': None})


@app.route('/api/scale', methods=['POST'])
def scale_deployment():
    """
    Scale the deployment up or down.

    FIX vs original:
    - Renamed from `scale()` to avoid shadowing issues and clarify intent
    - Validates direction input
    - Enforces MIN/MAX replica bounds (1–10)
    - Re-reads the deployment after patching to return confirmed replica count
      (original returned optimistic value before K8s confirmed the patch)
    - Returns structured response with previous count and direction
    """
    if not k8s_available:
        return jsonify({'error': 'Kubernetes not available in this environment'}), 503
    try:
        data = request.get_json()
        if not data or 'direction' not in data:
            return jsonify({'error': 'Missing direction field (up/down)'}), 400
        direction = data['direction']
        if direction not in ('up', 'down'):
            return jsonify({'error': 'direction must be "up" or "down"'}), 400

        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE
        )
        current = deployment.spec.replicas or 1
        delta = 1 if direction == 'up' else -1
        new_replicas = max(MIN_REPLICAS, min(MAX_REPLICAS, current + delta))

        if new_replicas == current:
            limit = 'maximum' if direction == 'up' else 'minimum'
            return jsonify({
                'replicas': current,
                'message': f'Already at {limit} ({current} replica{"s" if current != 1 else ""})'
            })

        deployment.spec.replicas = new_replicas
        apps_v1.patch_namespaced_deployment(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE, body=deployment
        )

        # Re-read to confirm K8s accepted the patch
        updated = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE
        )
        confirmed = updated.spec.replicas

        return jsonify({
            'replicas': confirmed,
            'previous': current,
            'direction': direction,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/events')
def k8s_events():
    """Fetch recent Kubernetes events for the namespace."""
    if not k8s_available:
        return jsonify({'events': []})
    try:
        events = v1.list_namespaced_event(namespace=NAMESPACE, limit=20)
        sorted_events = sorted(
            events.items,
            key=lambda e: (e.last_timestamp or e.event_time or ''),
            reverse=True
        )[:15]
        event_list = []
        for ev in sorted_events:
            ts = ev.last_timestamp or ev.event_time
            time_str = ts.strftime('%H:%M:%S') if ts else 'N/A'
            event_list.append({
                'time': time_str,
                'type': ev.type or 'Normal',
                'reason': ev.reason or '',
                'message': (ev.message or '')[:120],
            })
        return jsonify({'events': event_list})
    except Exception as e:
        return jsonify({'events': [], 'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
