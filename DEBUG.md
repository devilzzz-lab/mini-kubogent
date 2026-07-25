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
> for a local learning cluster. Phase 4 replaces this pattern for actual
> pipeline runs — the training Workflow now runs under its own
> narrowly-scoped `mini-kubogent-runner` service account instead of
> `default`, which is exactly what the "GOVERN" pillar is meant to enforce.

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
> artifact backend) instead of `emptyDir`. This is exactly why the Phase 4
> audit log (below) was deliberately built on a real PVC instead of
> repeating the same `emptyDir` mistake.

---
## Phase 3 notes — Inference Service

<<<PLACEHOLDER>>> (multi-layered Python environment issue)

**Symptom**
The Streamlit dashboard's Pipeline Status, Audit Log, and Cost/GPU tabs
all worked correctly (confirming Kubernetes API and subprocess access were
fine), but Model Registry showed "No registered models yet" even though
`curl http://localhost:5000/api/2.0/mlflow/registered-models/search`
against the same port-forwarded endpoint clearly returned the model.

This took several rounds to fully resolve because it was actually **four
separate, stacked issues** on macOS, each masking the next:

**Layer 1 — `pip`/`pip3`/`python3` pointed at different Python installs.**
`pip install -r requirements.txt --break-system-packages` reported
success, but `python3 -c "import mlflow"` failed with `ModuleNotFoundError`.
`which python3` / `which pip3` showed two entirely different install
locations (Homebrew Python vs. a python.org framework install). Packages
were going into one interpreter; the code was running in another.
**Fix:** use an isolated `venv`, always activate it, and always verify
`which python3` points inside the venv before doing anything else.

**Layer 2 — `venv` defaulted to a too-new Python (3.14).**
A fresh `python3 -m venv .venv` picked up Python 3.14, which has no
`numpy<2` wheels available yet (a hard requirement of `mlflow==2.14.1`),
causing the pinned mlflow install to silently fail and leave a
newer/wrong mlflow version in place instead.
**Fix:** create the venv with an explicit older interpreter:
`/opt/homebrew/bin/python3.12 -m venv .venv`.

**Layer 3 — MLflow client/server version mismatch.**
Even in a clean venv, an unpinned `mlflow>=2.14.1` requirement resolved to
`mlflow 3.14.0`, while the in-cluster MLflow **server** was `2.14.1`
(confirmed in the MLflow UI). MLflow 3.x changed the model registry
API/behavior (deprecating stage-based `latest_versions` in favor of
aliases), so a 3.x client talking to a 2.14.1 server returned an empty
list from `search_registered_models()` / `search_model_versions()` with
**no exception at all** — it looked like "no models" rather than "wrong
client version." Confirmed via a direct diagnostic script printing
`mlflow.__version__` and the actual registry query results.
**Fix:** pin `mlflow==2.14.1` exactly, matching the server. General rule:
an MLflow client talking to a self-hosted server should always be pinned
to the same version as that server — don't rely on `>=`.

**Layer 4 — pinning `mlflow==2.14.1` then conflicted with an unrelated
`pyarrow>=17.0` pin** (`mlflow 2.14.1` requires `pyarrow<16`) — removed
the unnecessary pyarrow pin and let mlflow's own constraint resolve it.

**Layer 5 — modern `setuptools` (83.x) dropped `pkg_resources`,** which
`mlflow==2.14.1` still imports internally (`ModuleNotFoundError: No
module named 'pkg_resources'`), because Python 3.12+ `venv` no longer
bundles `setuptools` and a plain `pip install setuptools` grabs the
latest (`pkg_resources`-free) release.
**Fix:** pin `setuptools<81` in requirements.txt, which still includes
`pkg_resources` (with a deprecation warning, not an error).

**Layer 6 — even after all the above was fixed, the running Streamlit
process still showed stale (empty) results,** because it had already
imported the broken `mlflow` when it first started; Streamlit's
browser-side rerun (pressing `R`) does not restart the underlying Python
process or re-import already-loaded modules.
**Fix:** fully stop (`Ctrl+C`) and restart `streamlit run app.py` after
any environment change, not just refresh the browser tab.

**Layer 7 — `which streamlit` still resolved to a non-venv install**
(`/Library/Frameworks/Python.framework/...`) even with the venv activated
and `which python3`/`which pip3` correctly pointing inside it — the same
PATH-precedence issue as Layer 1, but for the `streamlit` console script
specifically.
**Fix:** never invoke bare `streamlit`; always run it as a module through
the venv's own interpreter: `python3 -m streamlit run app.py`.

**Bonus code bug found along the way:** an earlier workaround (written
while still on the mismatched mlflow 3.x client, before Layer 3 was
diagnosed) switched `load_model_registry()` from a
`search_model_versions(filter_string=...)` query to reading
`rm.latest_versions` directly, to route around what looked like a broken
filter query. That masked the real client/server mismatch and, as a side
effect, only ever showed the single latest model version instead of full
version history. Once the client was correctly pinned to `2.14.1`, the
original filter-based query worked fine and was restored.

**Lesson for next time:** on macOS specifically, always verify `which
python3`, `which pip3`, and `which <any-cli-tool-being-installed>` inside
an activated venv before debugging "why isn't my code seeing this
package" — the vast majority of these symptoms were PATH/interpreter
mismatches, not application bugs, and each one perfectly disguised itself
as the next layer's problem.

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

## Phase 4 notes — Governance (RBAC + Audit Log)

No blocking issues this phase — ran clean on the first submit. Two design
decisions worth recording:

- **Audit log on a PVC, not `emptyDir`.** Given issue #10 above, the audit
  log step was deliberately backed by a `PersistentVolumeClaim`
  (`rbac/audit-pvc.yaml`) from the start, not a per-pod `emptyDir`. An
  audit trail that vanishes when a pod is rescheduled defeats its own
  purpose.
- **`continueOn: failed` on the train step.** Without this, a training run
  that fails the accuracy quality gate (`sys.exit(1)`) would mark the whole
  Workflow `Failed` and Argo would skip the downstream `audit` step
  entirely — meaning failed runs would never make it into the compliance
  record. `continueOn: failed: true` lets the audit step run regardless,
  and it records the real `train-status` (`Succeeded` / `Failed`) in the
  log line, which is closer to how a real governance system needs to
  behave: failures need a paper trail too, not just successes.
- **Outputs wired via files, not stdout parsing.** `train.py` writes
  `accuracy.txt` and `model_version.txt` to `/tmp/outputs/`, and the
  Workflow template picks them up via `outputs.parameters[].valueFrom.path`
  — the standard Argo pattern for passing structured data between steps,
  avoiding fragile log-scraping.

---

## Phase 5 notes — Dashboard (multi-layered Python environment issue)

**Symptom**
The Streamlit dashboard's Pipeline Status, Audit Log, and Cost/GPU tabs
all worked correctly (confirming Kubernetes API and subprocess access were
fine), but Model Registry showed "No registered models yet" even though
`curl http://localhost:5000/api/2.0/mlflow/registered-models/search`
against the same port-forwarded endpoint clearly returned the model.

This took several rounds to fully resolve because it was actually **seven
separate, stacked issues** on macOS, each masking the next:

**Layer 1 — `pip`/`pip3`/`python3` pointed at different Python installs.**
`pip install -r requirements.txt --break-system-packages` reported
success, but `python3 -c "import mlflow"` failed with `ModuleNotFoundError`.
`which python3` / `which pip3` showed two entirely different install
locations (Homebrew Python vs. a python.org framework install). Packages
were going into one interpreter; the code was running in another.
**Fix:** use an isolated `venv`, always activate it, and always verify
`which python3` points inside the venv before doing anything else.

**Layer 2 — `venv` defaulted to a too-new Python (3.14).**
A fresh `python3 -m venv .venv` picked up Python 3.14, which has no
`numpy<2` wheels available yet (a hard requirement of `mlflow==2.14.1`),
causing the pinned mlflow install to silently fail and leave a
newer/wrong mlflow version in place instead.
**Fix:** create the venv with an explicit older interpreter:
`/opt/homebrew/bin/python3.12 -m venv .venv`.

**Layer 3 — MLflow client/server version mismatch.**
Even in a clean venv, an unpinned `mlflow>=2.14.1` requirement resolved to
`mlflow 3.14.0`, while the in-cluster MLflow **server** was `2.14.1`
(confirmed in the MLflow UI). MLflow 3.x changed the model registry
API/behavior (deprecating stage-based `latest_versions` in favor of
aliases), so a 3.x client talking to a 2.14.1 server returned an empty
list from `search_registered_models()` / `search_model_versions()` with
**no exception at all** — it looked like "no models" rather than "wrong
client version." Confirmed via a direct diagnostic script printing
`mlflow.__version__` and the actual registry query results.
**Fix:** pin `mlflow==2.14.1` exactly, matching the server. General rule:
an MLflow client talking to a self-hosted server should always be pinned
to the same version as that server — don't rely on `>=`.

**Layer 4 — pinning `mlflow==2.14.1` then conflicted with an unrelated
`pyarrow>=17.0` pin** (`mlflow 2.14.1` requires `pyarrow<16`) — removed
the unnecessary pyarrow pin and let mlflow's own constraint resolve it.

**Layer 5 — modern `setuptools` (83.x) dropped `pkg_resources`,** which
`mlflow==2.14.1` still imports internally (`ModuleNotFoundError: No
module named 'pkg_resources'`), because Python 3.12+ `venv` no longer
bundles `setuptools` and a plain `pip install setuptools` grabs the
latest (`pkg_resources`-free) release.
**Fix:** pin `setuptools<81` in requirements.txt, which still includes
`pkg_resources` (with a deprecation warning, not an error).

**Layer 6 — even after all the above was fixed, the running Streamlit
process still showed stale (empty) results,** because it had already
imported the broken `mlflow` when it first started; Streamlit's
browser-side rerun (pressing `R`) does not restart the underlying Python
process or re-import already-loaded modules.
**Fix:** fully stop (`Ctrl+C`) and restart `streamlit run app.py` after
any environment change, not just refresh the browser tab.

**Layer 7 — `which streamlit` still resolved to a non-venv install**
(`/Library/Frameworks/Python.framework/...`) even with the venv activated
and `which python3`/`which pip3` correctly pointing inside it — the same
PATH-precedence issue as Layer 1, but for the `streamlit` console script
specifically.
**Fix:** never invoke bare `streamlit`; always run it as a module through
the venv's own interpreter: `python3 -m streamlit run app.py`.

**Bonus code bug found along the way:** an earlier workaround (written
while still on the mismatched mlflow 3.x client, before Layer 3 was
diagnosed) switched `load_model_registry()` from a
`search_model_versions(filter_string=...)` query to reading
`rm.latest_versions` directly, to route around what looked like a broken
filter query. That masked the real client/server mismatch and, as a side
effect, only ever showed the single latest model version instead of full
version history. Once the client was correctly pinned to `2.14.1`, the
original filter-based query worked fine and was restored.

**Lesson for next time:** on macOS specifically, always verify `which
python3`, `which pip3`, and `which <any-cli-tool-being-installed>` inside
an activated venv before debugging "why isn't my code seeing this
package" — the vast majority of these symptoms were PATH/interpreter
mismatches, not application bugs, and each one perfectly disguised itself
as the next layer's problem.