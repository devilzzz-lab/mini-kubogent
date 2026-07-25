# setup.md — Mini Kubogent

Verified, working command sequence, Phase 0 through Phase 4. Every command
here was actually run successfully in order — see [DEBUG.md](./DEBUG.md)
for the issues hit along the way and why some steps look the way they do.

> Replace `cloudops` below with your actual kind cluster name if different.
> Check with `kind get clusters`. Note: the kind **cluster name** and the
> **kubectl context name** are different — kind always prefixes the
> context with `kind-` (e.g. cluster `cloudops` → context `kind-cloudops`).

---

## Phase 0 — Environment Setup

### Prerequisites
```bash
docker --version
```

### Install tools (macOS)
```bash
brew install kind
brew install kubectl
brew install argo
```
Don't confuse `argo` (Argo Workflows CLI — what we need) with `argocd`
(ArgoCD, a separate GitOps tool — not used in this project).

### Create / select the cluster
```bash
# If creating fresh:
kind create cluster --name cloudops

# Switch to it (use-context, NOT set-context):
kubectl config use-context kind-cloudops
kubectl config current-context   # should print: kind-cloudops

kubectl get nodes                # should show one node, Ready
docker ps                        # should show cloudops-control-plane
```

---

## Phase 1 — Argo Workflows

### Install
```bash
kubectl create namespace argo

kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/latest/download/install.yaml --server-side

kubectl get crd | grep argoproj   # should list 8 argoproj.io CRDs
```

If any pod hangs in `ContainerCreating` for several minutes:
```bash
docker exec -it cloudops-control-plane crictl pull quay.io/argoproj/workflow-controller:v4.0.8
docker exec -it cloudops-control-plane crictl pull quay.io/argoproj/argocli:v4.0.8
```

### Fix RBAC (required — see DEBUG.md #3)
```bash
kubectl create clusterrole workflowtaskresults-access \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=workflowtaskresults.argoproj.io

kubectl create clusterrolebinding workflowtaskresults-binding \
  --clusterrole=workflowtaskresults-access \
  --serviceaccount=argo:default
```

### Verify
```bash
kubectl -n argo get pods
# argo-server and workflow-controller should both show 1/1 Running
```

### (Optional) Disable UI login for local use
```bash
kubectl patch deployment argo-server -n argo --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--auth-mode=server"}]'

kubectl -n argo rollout status deployment/argo-server
```

### Access UI
```bash
kubectl -n argo port-forward svc/argo-server 2746:2746
# open https://localhost:2746 (accept the self-signed cert warning)
```

### Smoke test
```bash
argo submit -n argo argo-pipelines/hello-world.yaml --watch
argo logs -n argo @latest
```
Expected: `Status: Succeeded` and log line
`Mini Kubogent pipeline is alive`.

---

## Phase 2 — MLflow Model Registry

### Build the MLflow image (self-built — see DEBUG.md #7 and #10)
```bash
cd mlflow
docker build -t mini-kubogent/mlflow:latest .
cd ..
```
> Important: the MLflow server must be started with `--serve-artifacts`
> so clients in other pods (like the inference service) can fetch model
> files over HTTP instead of assuming shared local disk. This is already
> set in `mlflow/Dockerfile` — see DEBUG.md #10 if you ever hit
> `CrashLoopBackOff` on the inference service with an `OSError` about a
> missing artifacts path.

### Load into kind and deploy
```bash
kind load docker-image mini-kubogent/mlflow:latest --name cloudops

kubectl apply -f mlflow/mlflow-deployment.yaml
kubectl -n mlflow get pods -w
# wait for mlflow-server to show 1/1 Running
```

### Verify UI
```bash
kubectl -n mlflow port-forward svc/mlflow-server 5000:5000
# open http://localhost:5000
```

---

## Phase 1 (full) — Train & Register Pipeline

### Build the training image
```bash
cd training
docker build -t mini-kubogent/train:latest .
cd ..
```

### Load into kind
```bash
kind load docker-image mini-kubogent/train:latest --name cloudops
```

### Run the pipeline
```bash
argo submit -n argo argo-pipelines/train-iris-model.yaml --watch
argo logs -n argo @latest
```
Expected: training logs, an accuracy/F1 score, and
`Model passed quality gate and was registered in MLflow.`

Check the MLflow UI (still port-forwarded from Phase 2) — you should see
the `mini-kubogent` experiment, the run's metrics, and under "Models" the
registered `mini-kubogent-iris-classifier`, version 1.

---

## Phase 3 — Model Serving

### Build the inference image
```bash
cd inference-service
docker build -t mini-kubogent/inference:latest .
cd ..
```

### Load into kind and deploy
```bash
kind load docker-image mini-kubogent/inference:latest --name cloudops

kubectl apply -f inference-service/deployment.yaml
kubectl -n mlflow get pods -w
# wait for inference-service to show 1/1 Running
```

If it's slow to become ready, check it's actually loading the model:
```bash
kubectl -n mlflow logs -l app=inference-service
# expect: "Loading model from: models:/mini-kubogent-iris-classifier/latest"
#         "Model loaded successfully."
```

### Test the live endpoint
```bash
kubectl -n mlflow port-forward svc/inference-service 8000:8000
```
In another terminal:
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}'
```
Expected response:
```json
{"prediction_index":0,"prediction_class":"setosa","model_uri":"models:/mini-kubogent-iris-classifier/latest"}
```

✅ At this point: `train → register → serve → live prediction` all work
end-to-end on the local cluster.

---

## Phase 4 — Governance (RBAC + Audit Log)

### Apply the RBAC roles
```bash
kubectl apply -f rbac/viewer-role.yaml
kubectl apply -f rbac/pipeline-runner-role.yaml
```
This creates two ClusterRoles, each bound to its own ServiceAccount in the
`argo` namespace:
- `mini-kubogent-viewer` — read-only (pods, workflows, deployments)
- `mini-kubogent-runner` — can submit/watch/delete workflows

### Verify least-privilege actually holds
```bash
# viewer should NOT be able to submit workflows
kubectl auth can-i create workflows.argoproj.io \
  --as=system:serviceaccount:argo:mini-kubogent-viewer -n argo
# expect: no

# runner SHOULD be able to
kubectl auth can-i create workflows.argoproj.io \
  --as=system:serviceaccount:argo:mini-kubogent-runner -n argo
# expect: yes
```

### Create the audit log PVC
```bash
kubectl apply -f rbac/audit-pvc.yaml
```

### Rebuild the training image (now writes accuracy/model_version output files)
```bash
cd training
docker build -t mini-kubogent/train:latest .
cd ..
kind load docker-image mini-kubogent/train:latest --name cloudops
```

### Run the pipeline (train + audit steps, runs as mini-kubogent-runner)
```bash
argo submit -n argo argo-pipelines/train-iris-model.yaml --watch
argo logs -n argo @latest
```
Expected: training logs as before, plus a final `log-audit` step printing
the audit line it just wrote, e.g.:
```
2026-07-25T10:04:04Z,sa=mini-kubogent-runner,workflow=train-iris-model-kxpkj,status=Succeeded,model_version=2,accuracy=1.0000
```

### Read the full audit trail anytime
```bash
kubectl -n argo run audit-viewer --rm -it --restart=Never --image=busybox \
  --overrides='{"spec":{"containers":[{"name":"audit-viewer","image":"busybox","command":["cat","/audit/audit.log"],"volumeMounts":[{"name":"audit-log","mountPath":"/audit"}]}],"volumes":[{"name":"audit-log","persistentVolumeClaim":{"claimName":"audit-log-pvc"}}]}}'
```
This spins up a throwaway pod that mounts the same PVC, cats the log, and
deletes itself — the log itself persists on the PVC regardless.

---

✅ At this point: RBAC roles are enforced and every pipeline run — success
or quality-gate failure — leaves a durable audit record. Move on to
Phase 5 (Streamlit dashboard) next.

If anything here fails, check [DEBUG.md](./DEBUG.md) first — most issues
that come up repeating this setup have already been hit and documented
there.

---

## Phase 5 — Cluster Dashboard (Streamlit)

Runs **locally** on your laptop (not deployed in-cluster), reading live
data from the Kubernetes API, MLflow, and the audit log PVC.

### Set up an isolated Python environment

Use a `venv` — don't rely on bare `pip`/`python3`, since on macOS these
can silently point at different Python installs depending on how many
you have (Homebrew, python.org, Xcode CLT, etc). See DEBUG.md #11 for the
full story if you hit anything odd here.

```bash
cd dashboard

# use Python 3.12 explicitly - mlflow==2.14.1 requires numpy<2, which has
# no wheels for very new Python versions (3.13/3.14) yet
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python3 --version   # confirm: Python 3.12.x
```

### Install dependencies

```bash
pip install -r requirements.txt --only-binary=:all:
```

`mlflow` is pinned to `==2.14.1` to **exactly match the MLflow server
version** running in-cluster — a mismatched client (e.g. pip resolving to
MLflow 3.x) will silently return zero registered models even though the
REST API works fine, since MLflow 3.x changed the registry API.

### Verify the environment before running the app

```bash
python3 -c "
import mlflow
print('mlflow version:', mlflow.__version__)
from mlflow.tracking import MlflowClient
c = MlflowClient(tracking_uri='http://localhost:5000')
models = c.search_registered_models()
print('models found:', len(models))
"
```
Expect `mlflow version: 2.14.1` and `models found: 1` (assuming MLflow
port-forward below is already running and at least one training run has
completed).

### Run it

Keep MLflow port-forwarded in its own terminal:
```bash
kubectl -n mlflow port-forward svc/mlflow-server 5000:5000
```

In another terminal, **inside the activated venv**, launch Streamlit
through the venv's Python explicitly — a bare `streamlit` command can
resolve to a different (non-venv) install on macOS, same PATH trap as
`pip`/`python3`:
```bash
cd dashboard
source .venv/bin/activate
python3 -m streamlit run app.py
```

Opens at `http://localhost:8501`. Four tabs:
- **Pipeline Status** — live pods in the `argo` namespace
- **Model Registry** — full MLflow version history
- **Audit Log** — the Phase 4 governance trail (same throwaway-pod
  pattern used manually above)
- **Cost / GPU** — clearly labeled simulated

See `dashboard/README.md` for config env vars (cluster context, MLflow
URI, etc).

---

✅ At this point: the full TRAIN → GOVERN → SERVE → OBSERVE loop is live
and observable end-to-end. Move on to Phase 6 (docs & demo polish) next.