# ⚡ DevOps Dashboard v2

Real-time Kubernetes monitoring dashboard built with Flask, Redis, Docker, and Kubernetes.

---

## 🗂️ Project Structure

```
devops-dashboard/
├── app.py                        # Flask app — all routes + K8s API calls
├── Dockerfile                    # Multi-stage build, non-root user, HEALTHCHECK
├── docker-compose.yml            # Local dev with Redis health dependency
├── requirements.txt
├── kubeconfig-docker.yaml        # K8s config mounted into Docker container
└── k8s/
    ├── configmap.yaml            # Environment config as K8s ConfigMap
    ├── serviceaccount.yaml       # RBAC — ServiceAccount + Role + RoleBinding
    ├── deployment.yaml           # App deployment: probes, resource limits, rolling update
    ├── redis-deployment.yaml     # Redis with PVC for persistent storage
    ├── service.yaml              # NodePort (app) + ClusterIP (redis)
    ├── hpa.yaml                  # HorizontalPodAutoscaler (CPU + Memory)
    └── networkpolicy.yaml        # Network isolation between pods
```

---

## 🐳 Docker

### Local dev (Docker Compose)
```bash
docker compose up --build
# Visit: http://localhost:5000
```

### Build & push image
```bash
docker build -t youruser/devops-dashboard:v2 .
docker push youruser/devops-dashboard:v2
```

---

## ☸️ Kubernetes (Minikube)

### First-time setup
```bash
minikube start
eval $(minikube docker-env)           # use minikube's Docker daemon
docker build -t youruser/devops-dashboard:v2 .
```

### Deploy everything in order
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/redis-deployment.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/networkpolicy.yaml
```

### Access the dashboard
```bash
minikube service devops-dashboard-service
# or
kubectl port-forward svc/devops-dashboard-service 5000:80
```

### Useful kubectl commands
```bash
kubectl get pods -w                                     # watch pods live
kubectl get hpa                                         # check autoscaler
kubectl describe deployment devops-dashboard            # deployment detail
kubectl logs -l app=devops-dashboard --tail=50          # app logs
kubectl rollout status deployment/devops-dashboard      # rollout progress
kubectl rollout undo deployment/devops-dashboard        # rollback
```

---

## 🔧 What's New in v2

| Feature | Before | After |
|---|---|---|
| Replica Controller | Bug: returned optimistic count before K8s confirmed | Fixed: re-reads deployment post-patch for confirmed count |
| Scale bounds | No UI enforcement | Buttons disabled at min (1) / max (10) |
| Probe endpoints | None | `/healthz` (liveness) + `/readyz` (readiness) |
| K8s probes | None | Liveness + Readiness + Startup probes |
| Resource limits | None | CPU + Memory requests & limits |
| HPA | None | CPU + Memory autoscaling (1–10 replicas) |
| RBAC | ClusterAdmin (implicit) | Minimal Role with only required permissions |
| Dockerfile | Single-stage, root user | Multi-stage build, non-root user |
| Redis | No persistence | PersistentVolumeClaim (1Gi) |
| Service | Random NodePort | Explicit NodePort 30080 |
| NetworkPolicy | None | Ingress/Egress restricted |
| Metrics | CPU + Memory | + Disk, Redis status, uptime formatted |
| K8s Events panel | None | Live event feed (15s refresh) |
| Pod table | 4 columns | + Ready column (x/y containers) |
