# setup.md — Mini Kubogent

Verified, working command sequence, Phase 0 through Phase 3. Every command
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

---

✅ At this point: `train → register → serve → live prediction` all work
end-to-end on the local cluster. Move on to Phase 4 (governance/RBAC +
audit log) next.

If anything here fails, check [DEBUG.md](./DEBUG.md) first — most issues
that come up repeating this setup have already been hit and documented
there.