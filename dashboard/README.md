 # Mini Kubogent — Cluster Dashboard (Phase 5)

Streamlit app showing live pod/workflow status, the MLflow model registry,
the Phase 4 audit log, and a clearly-labeled simulated GPU/cost panel.

## Run it (local, against the cluster)

```bash
cd dashboard
pip install -r requirements.txt --break-system-packages   # or use a venv

# Needs MLflow reachable at localhost:5000 — keep this running in another terminal:
kubectl -n mlflow port-forward svc/mlflow-server 5000:5000

streamlit run app.py
```

Opens at `http://localhost:8501`.

## What it reads

| Tab | Source | Live or mocked |
|---|---|---|
| Pipeline Status | Kubernetes API (`kubectl` context `kind-cloudops`, `argo` namespace pods) | ✅ Live |
| Model Registry | MLflow tracking API (`localhost:5000` via port-forward) | ✅ Live |
| Audit Log | PVC `audit-log-pvc`, read via a throwaway pod (same pattern as setup.md Phase 4) | ✅ Live |
| Cost / GPU | Static/random values, seeded for stable demo output | ⚠️ Simulated — clearly labeled in the UI |

## Config (env vars, all optional)

- `KUBE_CONTEXT` — default `kind-cloudops`
- `ARGO_NAMESPACE` — default `argo`
- `MLFLOW_TRACKING_URI` — default `http://localhost:5000`
- `AUDIT_PVC_NAME` — default `audit-log-pvc`