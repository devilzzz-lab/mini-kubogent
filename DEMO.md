# DEMO.md — Mini Kubogent, End-to-End Walkthrough

A single script to run the whole TRAIN → GOVERN → SERVE → OBSERVE loop
live, in order, for a demo or interview. Assumes Phase 0-5 are already
set up (see [setup.md](./setup.md) if not).

Total time: ~5 minutes.

---

## 0. Pre-flight — confirm the cluster is up

```bash
kubectl config current-context   # should print: kind-cloudops
kubectl get nodes                # one node, Ready
kubectl -n argo get pods         # argo-server + workflow-controller, Running
kubectl -n mlflow get pods       # mlflow-server + inference-service, Running
```

Start the two port-forwards you'll need, each in its own terminal, and
leave them running for the rest of the demo:
```bash
kubectl -n mlflow port-forward svc/mlflow-server 5000:5000
kubectl -n mlflow port-forward svc/inference-service 8000:8000
```

---

## 1. GOVERN — show the RBAC boundary is real (30 sec)

```bash
# viewer cannot submit a workflow
kubectl auth can-i create workflows.argoproj.io \
  --as=system:serviceaccount:argo:mini-kubogent-viewer -n argo
# -> no

# runner can
kubectl auth can-i create workflows.argoproj.io \
  --as=system:serviceaccount:argo:mini-kubogent-runner -n argo
# -> yes
```
**Talking point:** two ClusterRoles, least-privilege, enforced by
Kubernetes itself — not app-level convention.

---

## 2. TRAIN + GOVERN — run the pipeline (1 min)

```bash
argo submit -n argo argo-pipelines/train-iris-model.yaml --watch
```
Watch it go through `train` → `audit` steps live. Then:
```bash
argo logs -n argo @latest
```
**Talking point:** runs as `mini-kubogent-runner` (not `default`),
trains a RandomForest on Iris, registers the model in MLflow, and fails
the whole run if it doesn't clear the accuracy quality gate
(`MIN_ACCURACY` env var). A final audit step logs the run to a
PVC-backed file regardless of pass/fail (`continueOn: failed`).

---

## 3. Show the registry (30 sec)

Open `http://localhost:5000` (MLflow UI) → **mini-kubogent** experiment
→ show the new run's metrics, then **Models** → show the new version of
`mini-kubogent-iris-classifier`.

**Talking point:** self-built MLflow image, in-cluster, artifact
proxying enabled (`--serve-artifacts`) so any pod can fetch model files
over HTTP instead of assuming shared local disk.

---

## 4. SERVE — hit the live endpoint (30 sec)

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}'
```
Expected:
```json
{"prediction_index":0,"prediction_class":"setosa","model_uri":"models:/mini-kubogent-iris-classifier/latest"}
```
**Talking point:** FastAPI service loads the *latest* registered model
version from MLflow on startup — no manual redeploy needed when a new
version is trained.

---

## 5. Prove the audit trail (30 sec)

```bash
kubectl -n argo run audit-viewer --rm -it --restart=Never --image=busybox \
  --overrides='{"spec":{"containers":[{"name":"audit-viewer","image":"busybox","command":["cat","/audit/audit.log"],"volumeMounts":[{"name":"audit-log","mountPath":"/audit"}]}],"volumes":[{"name":"audit-log","persistentVolumeClaim":{"claimName":"audit-log-pvc"}}]}}'
```
**Talking point:** every run — pass or fail — leaves a durable,
timestamped, who/what record on a PVC, not `emptyDir`, so it survives
pod restarts. This is the compliance trail Kubogent's "GOVERN" pillar
advertises.

---

## 6. OBSERVE — the dashboard (1-2 min)

```bash
cd dashboard
source .venv/bin/activate
python3 -m streamlit run app.py
```
Walk through all 4 tabs at `http://localhost:8501`:
- **Pipeline Status** — the run you just triggered, live from the K8s API
- **Model Registry** — full version history, live from MLflow
- **Audit Log** — the same record you just read via kubectl, now in a UI
- **Cost / GPU** — clearly labeled simulated, explain why (no GPU/billing
  on a laptop) and what it would pull on real EKS (NVIDIA DCGM, AWS Cost
  Explorer)

---

## 7. Close — what this demonstrates vs. what's conceptual-only

Point to the two tables in [README.md](./README.md):
- Full feature list: Kubogent vs. this project
- Buildable vs. conceptual-only summary

**Talking point:** everything demoed above (pipelines, registry, serving,
RBAC, audit log, dashboard) runs on open-source K8s-native tooling
identical in kind to what Kubogent likely uses underneath — the parts
*not* built (GPU partitioning, service mesh, micro-VM isolation,
multi-cloud, real billing) all require cloud GPU hardware or
enterprise networking a laptop genuinely cannot provide, and are
explained conceptually in the README instead of faked.

---

## If something breaks mid-demo

Check [DEBUG.md](./DEBUG.md) — it's a real log of every issue hit while
building this (RBAC gaps, image pull quirks, MLflow client/server version
mismatches, Python environment chaos on macOS, etc.), most likely to
cover whatever just went wrong.