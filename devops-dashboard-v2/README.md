# ⚡ DevOps Dashboard v2

Real-time Kubernetes monitoring dashboard built with Flask, Redis, Docker, and Kubernetes.

---

## 🗂️ Project Structure

```
devops-dashboard-v2/
├── app.py                          # Flask app — all routes + K8s API calls
├── Dockerfile                      # Multi-stage build, non-root user, HEALTHCHECK
├── docker-compose.yml              # Local dev with Redis health dependency
├── requirements.txt                # Pinned dependencies
├── .gitignore                      # Keeps kubeconfig out of Git
├── kubeconfig-docker.yaml.template # Safe template — copy & fill with real values
└── k8s/
    ├── configmap.yaml              # Environment config (no NAMESPACE — that's dynamic)
    ├── serviceaccount.yaml         # RBAC — ServiceAccount + Role + RoleBinding
    ├── deployment.yaml             # App deployment: uses ConfigMap via envFrom
    ├── redis-deployment.yaml       # PVC first, then Redis Deployment
    ├── service.yaml                # NodePort (app) + ClusterIP (redis)
    ├── hpa.yaml                    # HPA — requires metrics-server (see setup below)
    └── networkpolicy.yaml          # Proper egress rules incl. kube-apiserver
```

---

## ⚠️ First-Time Setup (Read Before Running Anything)

### Step 1 — Generate your local kubeconfig (DO NOT commit the real file)

```bash
minikube start
cp ~/.kube/config ./kubeconfig-docker.yaml
```

> This file is in `.gitignore`. Never commit it — it has private keys.
> If Minikube restarts and the IP changes, run `cp ~/.kube/config ./kubeconfig-docker.yaml` again.

### Step 2 — Enable Metrics Server (required for HPA to work)

```bash
minikube addons enable metrics-server
```

> Without this, `kubectl get hpa` will show `<unknown>` for CPU/Memory and autoscaling will never trigger.

---

## 🐳 Docker Compose — Local Dev

```bash
docker compose up --build
# Visit: http://localhost:5000
```

> The app mounts `kubeconfig-docker.yaml` to `/app/.kube/config` (non-root user path).
> K8s features work if Minikube is running and the kubeconfig IP is current.

---

## ☸️ Kubernetes (Minikube)

### Build and push image

```bash
eval $(minikube docker-env)
docker build -t yashwonderbiz/devops-dashboard:v2 .
# OR push to Docker Hub:
docker push yashwonderbiz/devops-dashboard:v2
```

### Deploy in order (order matters)

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/redis-deployment.yaml    # PVC is created first inside this file
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/networkpolicy.yaml
```

### Access the dashboard

```bash
minikube service devops-dashboard-service
# OR
kubectl port-forward svc/devops-dashboard-service 5000:80
# Visit: http://localhost:5000
```

### Useful commands

```bash
kubectl get pods -w                                      # watch pods live
kubectl get hpa                                          # check autoscaler (needs metrics-server)
kubectl describe deployment devops-dashboard             # deployment detail
kubectl logs -l app=devops-dashboard --tail=50           # app logs
kubectl rollout status deployment/devops-dashboard       # rollout progress
kubectl rollout undo deployment/devops-dashboard         # rollback
kubectl get events --sort-by='.lastTimestamp'            # cluster events
```

---

## 🔧 Bugs Fixed in This Version

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `kubeconfig-docker.yaml` | Hardcoded Minikube IP breaks on restart | Template provided; generate fresh from `~/.kube/config` |
| 2 | `kubeconfig-docker.yaml` | Real credentials committed to Git | Added to `.gitignore`; template has placeholders |
| 3 | `deployment.yaml` | ConfigMap defined but never used | Now uses `envFrom: configMapRef` |
| 4 | `docker-compose.yml` | Kubeconfig mounted to `/root` but app runs as non-root | Mount changed to `/app/.kube/config`; `KUBECONFIG` env set |
| 5 | `app.py` | Redis connected at module load — no retry | `get_redis()` lazy function retries on each call |
| 6 | `deployment.yaml` | No `KUBECONFIG` env var for local fallback | `KUBECONFIG` respected via `os.environ.get` in app.py |
| 7 | `configmap.yaml` | `NAMESPACE` hardcoded to "default" | Removed; `NAMESPACE` now from `metadata.namespace` fieldRef |
| 8 | `hpa.yaml` | Metrics Server not enabled by default | README now includes `minikube addons enable metrics-server` |
| 9 | `redis-deployment.yaml` | PVC defined after Deployment — pod stays Pending | PVC moved to top of file |
| 10 | `networkpolicy.yaml` | K8s API egress not scoped to kube-system | Added `namespaceSelector: kube-system` with port 443 |
| 11 | `requirements.txt` | No version pins | All packages pinned to specific versions |
| 12 | `requirements.txt` | `requests` library unused | Removed |
| 13 | `README.md` | Missing metrics-server step | Added to setup instructions |
| 14 | `kubeconfig-docker.yaml` | BOM character breaks YAML parsing | Use fresh `cp ~/.kube/config` — no BOM |
