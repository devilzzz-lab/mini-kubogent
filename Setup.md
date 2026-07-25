# Setup — Phase 0: Environment Setup

Run these steps on your laptop to get the local cluster ready.

> Note on cluster naming: examples below use `mini-kubogent` as the cluster
> name for a fresh setup. If you're reusing an existing `kind` cluster
> (e.g. one named `cloudops`), just substitute your actual cluster name in
> every command and node reference (e.g. `cloudops-control-plane` instead
> of `mini-kubogent-control-plane`). Check your cluster name anytime with
> `kind get clusters`.

## Prerequisites

- Docker must be installed and running:
```bash
docker --version
```

## 1. Install `kind`

**macOS**
```bash
brew install kind
```

**Linux**
```bash
[ $(uname -m) = x86_64 ] && curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```

## 2. Install `kubectl`

**macOS**
```bash
brew install kubectl
```

**Linux**
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

## 3. Install Argo CLI

**macOS**
```bash
brew install argo
```

**Linux**
```bash
curl -sLO https://github.com/argoproj/argo-workflows/releases/latest/download/argo-linux-amd64.gz
gunzip argo-linux-amd64.gz
chmod +x argo-linux-amd64
sudo mv argo-linux-amd64 /usr/local/bin/argo
```

> Don't confuse this with `argocd` (ArgoCD) — that's a separate GitOps
> continuous-delivery tool, unrelated to this project. We need the `argo`
> CLI (Argo Workflows) specifically.

## 4. Create the kind cluster

```bash
kind create cluster --name mini-kubogent
kubectl config use-context kind-mini-kubogent
kubectl cluster-info
kubectl get nodes
```

You should see one node in `Ready` state.

> If you have multiple kind clusters or a broken/stale context (e.g. from
> a previous EKS setup), switch explicitly with
> `kubectl config use-context <context-name>` — not `set-context`, which
> only edits a context rather than switching to it. List all contexts with
> `kubectl config get-contexts`.

## 5. Verify Docker containers backing the cluster

```bash
docker ps
```

You'll see a container named `mini-kubogent-control-plane` — that's your "node."

## 6. Install Argo Workflows on the cluster

```bash
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/latest/download/install.yaml --server-side
kubectl get crd | grep argoproj
```

> Use `--server-side`, not a plain `kubectl apply`. The Argo CRDs are large
> enough that a normal `kubectl apply` fails with
> `metadata.annotations: Too long: may not be more than 262144 bytes`,
> because it tries to store the full previous config as an annotation.
> Server-side apply avoids that entirely.

If a pod gets stuck on `ContainerCreating` for a long time, pre-pull the image directly inside the node:
```bash
docker exec -it mini-kubogent-control-plane crictl pull quay.io/argoproj/workflow-controller:v4.0.8
docker exec -it mini-kubogent-control-plane crictl pull quay.io/argoproj/argocli:v4.0.8
```

## 7. Fix RBAC for workflow results (required)

The default install manifest for Argo Workflows v4.0.8 has an RBAC gap:
neither the namespaced `argo-role` nor the `argo-cluster-role` grants
`create` on `workflowtaskresults` — which every workflow pod needs to
report its result. Without this fix, workflows will show
`Status: Error` with `workflowtaskresults.argoproj.io is forbidden`, even
though the actual pod logic runs and completes successfully.

```bash
kubectl create clusterrole workflowtaskresults-access \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=workflowtaskresults.argoproj.io

kubectl create clusterrolebinding workflowtaskresults-binding \
  --clusterrole=workflowtaskresults-access \
  --serviceaccount=argo:default
```

See README.md → Troubleshooting Log for the full root-cause investigation.

## 8. Check Argo is running

```bash
kubectl -n argo get pods
kubectl -n argo get svc
```

Both `argo-server` and `workflow-controller` should show `1/1 Running`.

## 9. Access the Argo UI (optional — disable login for local use)

```bash
kubectl -n argo port-forward svc/argo-server 2746:2746
```

Then open: `https://localhost:2746` (accept the self-signed cert warning).

By default the UI shows a login screen (SSO / client auth token). For a
local learning cluster with no real auth provider configured, disable the
login requirement instead:

```bash
kubectl patch deployment argo-server -n argo --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--auth-mode=server"}]'

kubectl -n argo rollout status deployment/argo-server
```

Restart the port-forward and refresh the page — it should load directly
into the workflow list with no login prompt.

## 10. Smoke test

```bash
argo submit -n argo argo-pipelines/hello-world.yaml --watch
argo logs -n argo @latest
```

Expected: `Status: Succeeded` and log output
`Mini Kubogent pipeline is alive`.

---

✅ Once all pods in the `argo` namespace show `Running` and the smoke test
succeeds, Phase 0 is complete — move on to Phase 1 (Pipeline Orchestration).