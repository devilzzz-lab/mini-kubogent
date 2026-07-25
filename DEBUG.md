# DEBUG.md — Mini Kubogent

Every real issue hit while building this project, with root cause and the
exact fix — kept separate from README.md so the debugging history doesn't
clutter the main docs, but stays available for reference (and is good
interview material: real RBAC/K8s/Argo debugging, not tutorial-following).

---

## 1. `kubectl apply` failed on Argo CRDs — annotation too long

**Symptom**
```
Error from server (Invalid): error when creating ".../install.yaml":
CustomResourceDefinition.apiextensions.k8s.io "workflows.argoproj.io" is invalid:
metadata.annotations: Too long: may not be more than 262144 bytes
```

**Cause**
`kubectl apply` stores the full previous config as a `last-applied-configuration`
annotation for 3-way merges. Argo's CRDs are large enough to exceed
Kubernetes' 262144-byte annotation limit.

**Fix**
Use server-side apply, which doesn't rely on that annotation:
```bash
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/latest/download/install.yaml --server-side
```

---

## 2. Argo pods stuck in `ContainerCreating` for several minutes

**Symptom**
`argo-server` / `workflow-controller` pods stayed `0/1 ContainerCreating`
for 5+ minutes with only a generic `Pulling image "..."` event and no
resolution.

**Cause**
Slow/stalled image pull inside the kind node's containerd — not a hard
failure, just very slow, and `kubectl describe` doesn't show pull progress.

**Fix**
Pull the image directly inside the node container to nudge/verify it:
```bash
docker exec -it <node-name> crictl pull quay.io/argoproj/workflow-controller:v4.0.8
docker exec -it <node-name> crictl pull quay.io/argoproj/argocli:v4.0.8
```
Find `<node-name>` with `docker ps` (e.g. `cloudops-control-plane`).

---

## 3. `workflowtaskresults.argoproj.io is forbidden` — RBAC gap

**Symptom**
Workflow pod logs show the correct output, but the Workflow itself is
marked `Status: Error`:
```
wait: Error (exit code 64): workflowtaskresults.argoproj.io is forbidden:
User "system:serviceaccount:argo:default" cannot create resource
"workflowtaskresults" in API group "argoproj.io" in the namespace "argo"
```

**Cause** (found by inspecting actual role contents)
- `argo-role` (namespaced Role) only grants `leases` and `secrets` — nothing
  about workflows.
- `argo-cluster-role` (ClusterRole) grants `list`, `watch`,
  `deletecollection` on `workflowtaskresults` — but **not `create`**, which
  is exactly what a running pod needs to report its result back.

This is a real gap in the standalone (non-Helm) install manifest for Argo
Workflows v4.0.8.

**Fix**
Create a dedicated ClusterRole with the missing verb and bind it:
```bash
kubectl create clusterrole workflowtaskresults-access \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=workflowtaskresults.argoproj.io

kubectl create clusterrolebinding workflowtaskresults-binding \
  --clusterrole=workflowtaskresults-access \
  --serviceaccount=argo:default
```

> Production note: granting this to the `default` service account is fine
> for a local learning cluster. In a real Kubogent-style production setup,
> each pipeline/tenant would run under its own narrowly-scoped service
> account instead — exactly what the "GOVERN" pillar (Phase 4 here) is
> meant to enforce.

---

## 4. Argo UI stuck on login screen

**Symptom**
`https://localhost:2746` shows a login page asking for SSO or a client
auth token, with no obvious way in for local use.

**Cause**
Argo Server defaults to requiring authentication.

**Fix**
Patch the deployment to run in `--auth-mode=server` (fine for local/demo
use, not for real multi-user production):
```bash
kubectl patch deployment argo-server -n argo --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--auth-mode=server"}]'

kubectl -n argo rollout status deployment/argo-server
```
Restart the port-forward and refresh — no login prompt should appear.

---

## 5. `kubectl config set-context` didn't switch clusters

**Symptom**
```
kubectl config set-context kind-cloudops
kubectl get nodes
# Error in configuration: context was not found for specified context: arn:aws:eks:...
```

**Cause**
`set-context` *modifies* a context's definition; it does not switch the
active context. The current context stayed pointed at a stale EKS entry.

**Fix**
Use `use-context` instead:
```bash
kubectl config use-context kind-cloudops
kubectl config current-context   # should now print kind-cloudops
```
List all contexts anytime with `kubectl config get-contexts`. To fully
remove a stale/broken context:
```bash
kubectl config delete-context <name>
kubectl config delete-cluster <name>
kubectl config delete-user <name>
```

---

## 6. `argocd` vs `argo` confusion

**Symptom**
`argocd version` worked but was unrelated to the project; no `argo` CLI
installed yet.

**Cause**
ArgoCD (`argocd`) and Argo Workflows (`argo`) are two different projects
under the same umbrella. ArgoCD does GitOps continuous delivery; Argo
Workflows does pipeline/job orchestration — which is what this project
needs.

**Fix**
Install the correct CLI:
```bash
brew install argo
argo version
```

---

## 7. MLflow image pull hung indefinitely

**Symptom**
`mlflow-server` pod stuck `ContainerCreating` for 20+ minutes pulling
`ghcr.io/mlflow/mlflow:v2.14.1`; unlike issue #2, a direct `crictl pull`
did not resolve it either.

**Cause**
Unreliable/incorrect external image reference.

**Fix**
Stopped depending on an external MLflow image entirely. Built a minimal
MLflow server image locally instead:
```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir mlflow==2.14.1
EXPOSE 5000
ENTRYPOINT ["mlflow", "server", "--host=0.0.0.0", "--port=5000", \
    "--backend-store-uri=sqlite:////mlflow-data/mlflow.db", \
    "--default-artifact-root=/mlflow-data/artifacts"]
```
Built and loaded the same way as every other image in this project (see
Phase 1/3 build+load steps in setup.md) — more reliable and consistent.

---

## 8. Stuck `Terminating` pods/namespace

**Symptom**
`kubectl delete -f mlflow-deployment.yaml` (or a single pod delete) left
resources stuck in `Terminating` for a long time.

**Fix**
Force-delete first:
```bash
kubectl -n mlflow delete pods --all --grace-period=0 --force
```
If still stuck, the pod has a finalizer blocking cleanup — remove it
directly:
```bash
kubectl -n mlflow patch pod <pod-name> -p '{"metadata":{"finalizers":null}}' --type=merge
```
Same pattern applies to a stuck-terminating namespace if it ever occurs.

---

## 9. Argo: `UNAUTHORIZED` pulling a purely local image

**Symptom**
```
failed to look-up entrypoint/cmd for image "mini-kubogent/train:latest" ...
GET https://index.docker.io/v2/mini-kubogent/train/manifests/latest: UNAUTHORIZED
```
This happened even though the image was already loaded into kind and
`imagePullPolicy: Never` was set.

**Cause**
Argo's default (emissary) executor tries to look up a container image's
`ENTRYPOINT`/`CMD` from its registry manifest before running it — even for
local-only images. Since the image was never pushed anywhere, that lookup
fails against Docker Hub by default.

**Fix**
Specify `command:` explicitly in the Workflow template so Argo never needs
to look anything up from a registry:
```yaml
container:
  image: mini-kubogent/train:latest
  imagePullPolicy: Never
  command: ["python", "train.py"]
```
Applies to any locally-built, never-pushed image used in an Argo
Workflow — always set `command:` explicitly.

---

## 10. Inference service `CrashLoopBackOff` — MLflow artifacts not shared between pods

**Symptom**
`inference-service` pod crashes on startup with:
```
OSError: No such file or directory:
'/mlflow-data/artifacts/1/<run_id>/artifacts/model/.'
```
even though the model shows as registered in the MLflow UI.

**Cause**
The MLflow server was started with a plain local filesystem path as its
artifact root (`--default-artifact-root=/mlflow-data/artifacts`). That
path lives inside the `mlflow-server` pod's own `emptyDir` volume — it is
**not shared with any other pod**. The training container (different pod)
wrote model files there via the tracking API, but the MLflow *client*
running inside `inference-service` (a separate pod, separate filesystem)
tried to read that same local path directly and it simply didn't exist in
its own container.

**Fix**
Enable MLflow's built-in artifact proxying, so clients fetch model files
over HTTP through the tracking server instead of assuming shared local
disk:
```dockerfile
ENTRYPOINT ["mlflow", "server", \
    "--host=0.0.0.0", \
    "--port=5000", \
    "--backend-store-uri=sqlite:////mlflow-data/mlflow.db", \
    "--serve-artifacts", \
    "--artifacts-destination=/mlflow-data/artifacts", \
    "--default-artifact-root=mlflow-artifacts:/"]
```
The `mlflow-artifacts:/` scheme is what tells any MLflow client (training
container, inference service, notebooks, etc.) to route artifact
read/write through the server's HTTP API rather than expecting direct
filesystem access — this is the correct pattern any time the tracking
server and its clients run in different pods/containers/machines.

After rebuilding and redeploying MLflow with this change, retrained the
model (registry data doesn't survive a pod restart since it's on
`emptyDir` — expected for this POC, see note below) and restarted
`inference-service`; it loaded the model successfully on the next attempt.

> Note on persistence: `emptyDir` storage means all MLflow data (runs,
> registered models, artifacts) is lost if the `mlflow-server` pod
> restarts or is rescheduled. That's an accepted limitation for this local
> learning POC. In a real deployment, this would use a `PersistentVolume`
> (or, in production Kubogent-style setups, S3/cloud object storage as the
> artifact backend) instead of `emptyDir`.

---

## Phase 3 notes — Inference Service

Built and deployed the same way as prior images (`docker build` →
`kind load docker-image ... --name cloudops`), with `imagePullPolicy: Never`
and a `readinessProbe` on `/health` so `kubectl get pods` accurately
reflects when the model has actually finished loading from MLflow (model
loading happens on FastAPI startup via `mlflow.pyfunc.load_model`, which
takes a few seconds).

The blocking issue hit here was #10 above (MLflow artifacts not shared
between pods). Once fixed, the full loop worked cleanly:
train → register (Argo + training container) → serve (FastAPI) →
`POST /predict` returns a live prediction.