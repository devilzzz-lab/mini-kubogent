# Mini Kubogent

A local, hands-on proof of concept built to **study how Aivar's Kubogent AI
service works** — implemented on a local `kind` Kubernetes cluster instead
of production EKS + GPU infrastructure.

> This is a learning project, not a commercial clone. Where a real
> Kubogent feature needs cloud GPUs, EKS, or enterprise networking that a
> laptop can't provide, it is documented conceptually below instead of
> faked.

---

## Why this project exists

Kubogent AI is Aivar's product for running enterprise AI/ML workloads on
Kubernetes (EKS), with governance, GPU management, and MLOps tooling built
in. Reading their marketing page alone doesn't teach you how the pieces
actually work — so this project rebuilds the *core mechanics* (pipeline →
registry → serving → dashboard) locally, using the same open-source
building blocks Kubogent is very likely built on (Argo, MLflow, Kubernetes
primitives), so the concepts can be demonstrated and explained properly.

## What Kubogent actually does (recap)

Kubogent = **Kubernetes + Agent**. It turns EKS into a governed platform
where a company can fine-tune, register, deploy, and monitor its own AI
models on its own infrastructure — instead of calling an external LLM API.
You bring your AWS account and your GPUs; Kubogent configures the platform
layer on top: pipelines, registry, dashboard, security, and multi-tenant
GPU sharing.

---

## Full feature list on the Kubogent page vs. this project

| # | Kubogent Feature (from aivar.tech) | In this project? | How |
|---|---|---|---|
| 1 | EKS (Kubernetes on AWS) | ⚠️ Simulated | `kind` cluster locally instead of EKS |
| 2 | Cluster Dashboard | ✅ Built | Streamlit dashboard reading K8s + MLflow APIs |
| 3 | Model Workbench (fine-tuning) | ✅ Built (tiny scale) | CPU-only small model training step in pipeline |
| 4 | Model Catalog (registry) | ✅ Built | MLflow tracking + model registry |
| 5 | Pipeline Designer (Argo-backed) | ✅ Built | Argo Workflows (used directly, no visual UI builder) |
| 6 | Zero-Latency Scaling | ❌ Not built | Conceptual only — see below |
| 7 | Intelligent GPU Partitioning | ❌ Not built | Conceptual only — see below |
| 8 | Micro-VM Isolation | ❌ Not built | Conceptual only — see below |
| 9 | Service Mesh for AI | ❌ Not built | Conceptual only — see below |
| 10 | Multi-cloud / zero lock-in | ❌ Not built | Conceptual only — see below |
| 11 | RBAC + audit logs | ✅ Built (basic) | K8s RBAC roles + simple pipeline run log |
| 12 | Kubeflow / MLflow / Argo compatibility | ⚠️ Partial | MLflow + Argo used; Kubeflow explained, not installed |
| 13 | Cost visibility / predictable billing | ⚠️ Mocked | Dashboard shows illustrative numbers, not real billing |

---

## Buildable vs. Conceptual-only — summary table

| Category | Local kind cluster? | Why / why not |
|---|---|---|
| Pipeline orchestration | ✅ Yes | Argo Workflows runs natively on any K8s cluster |
| Model registry | ✅ Yes | MLflow is just a server + DB, cloud-agnostic |
| Model fine-tuning | ✅ Yes (small scale) | CPU-based training of a small model works, just slower |
| Model serving | ✅ Yes | Any container can serve a REST endpoint |
| RBAC + audit logging | ✅ Yes | Native Kubernetes feature, no cloud needed |
| Dashboard | ✅ Yes | Just reads K8s/MLflow APIs |
| GPU partitioning (MIG) | ❌ No | Requires physical NVIDIA GPUs with MIG support |
| Service mesh (Istio) | ❌ No | Technically possible on kind, but out of scope here — see below |
| Micro-VM isolation | ❌ No | Requires Firecracker/Kata + specific node runtime config |
| Multi-cloud portability | ❌ No | Architectural claim, nothing to "run" for one laptop demo |
| Real cost/billing | ❌ No | Needs actual cloud billing APIs |

---

## Project Phases

### Phase 0 — Environment setup
- Install `kind`, `kubectl`, `docker`, `helm`
- Create local cluster: `kind create cluster --name mini-kubogent`

### Phase 1 — Pipeline orchestration (Argo Workflows)
- Install Argo Workflows on the cluster
- Write a Workflow YAML: fetch data → train tiny model → evaluate → log to MLflow
- Trigger and verify a run via `argo submit`

### Phase 2 — Model registry (MLflow)
- Deploy MLflow tracking server in-cluster
- Pipeline logs metrics, parameters, and registers the trained model
- Verify model version appears in the MLflow UI

### Phase 3 — Model serving
- Package the registered model into a small FastAPI inference service
- Deploy as a Kubernetes Deployment + Service
- Test with a `curl`/Postman request to get a live prediction

### Phase 4 — Governance basics
- Apply Kubernetes RBAC roles (e.g. read-only vs. pipeline-runner roles)
- Log every pipeline run (who/when/what model version) to a simple audit
  log file or table

### Phase 5 — Dashboard
- Build a Streamlit app that shows:
  - Live pod/job status (via Kubernetes API)
  - Registered model versions (via MLflow API)
  - A clearly-labeled "simulated" GPU utilization / cost panel

### Phase 6 — Documentation & demo polish
- Finalize README + POC
- Record/demo: run pipeline → show registry update → hit live endpoint → show dashboard

---

## Concepts NOT built here — explained for study

These are real Kubogent capabilities that require cloud GPU hardware or
enterprise-grade networking that a local `kind` cluster cannot provide.
They're documented here so they can still be understood and spoken to.

### GPU Partitioning / A100s / MIG
Modern NVIDIA GPUs (like the A100) support **MIG (Multi-Instance GPU)**,
which lets a single physical GPU be split into several isolated
GPU-instances, each with its own dedicated memory and compute slice. This
lets a platform like Kubogent run multiple models/tenants on one GPU
without them interfering with each other — much better utilization than
giving one whole GPU to one job. This requires real NVIDIA data-center
GPUs and the NVIDIA GPU Operator on Kubernetes; it cannot be simulated on
a laptop without a compatible GPU.

### Why "Multi-cloud" / "Zero vendor lock-in"
Because Kubogent is built on Kubernetes-native, open tooling (Argo,
MLflow-compatible registries, standard K8s APIs) rather than
cloud-proprietary services, the same platform config can in theory be
deployed on AWS EKS, Azure AKS, GCP GKE, or on-prem clusters with minimal
changes. The claim is architectural — it's not something a single demo
"runs," it's a property of using standard K8s primitives instead of
AWS-only managed services.

### Service Mesh for AI
A service mesh (e.g. **Istio**, **Linkerd**) is a networking layer that
sits alongside your services (usually via sidecar containers) and handles
traffic routing, retries, load balancing, mutual TLS, and observability
between services — without changing application code. For AI workloads,
this is used for things like canary-deploying a new model version,
routing a percentage of traffic to it, and monitoring latency/errors per
model version automatically. Istio *can* run on `kind`, but is deliberately
left out of this POC to keep it lightweight and fast to build; the
orchestration and registry pieces demonstrate the same underlying
platform-engineering skill.

### Micro-VM Isolation
Technologies like **Firecracker** (used by AWS Lambda/Fargate) or **Kata
Containers** run each workload inside a lightweight virtual machine
instead of a standard Linux container. Containers share the host kernel;
micro-VMs don't — giving much stronger security isolation between
tenants, which matters a lot when different customers' fine-tuning jobs
run on the same physical node. This needs a specific container runtime
setup at the node level and isn't practical to demonstrate inside Docker-
in-Docker (`kind` itself runs nodes as containers).

### Zero-Latency Scaling
Marketing term for fast, predictive autoscaling of inference endpoints to
handle demand spikes without cold-start delay — typically implemented via
Kubernetes Horizontal Pod Autoscaler (HPA) combined with pre-warmed pod
pools or KEDA event-driven scaling. Conceptually related to Kubernetes HPA,
but "zero-latency" pre-warming at scale needs real traffic patterns and
cloud infra to demonstrate meaningfully.

### Kubeflow
Kubeflow is a full ML platform for Kubernetes — it includes Jupyter
notebook management, **Kubeflow Pipelines** (which is actually built on
top of Argo Workflows), model serving (KServe), and hyperparameter tuning
(Katib). Kubogent's FAQ mentions compatibility with Kubeflow, MLflow, and
Argo. This project uses **Argo Workflows directly** instead of installing
full Kubeflow, since Kubeflow Pipelines itself runs on Argo under the
hood — using Argo directly demonstrates the same orchestration mechanics
with far less setup overhead and resource usage, which matters on a local
cluster.

### Real cost / billing visibility
Kubogent's dashboard shows real GPU cost tracking against actual AWS
billing data. Locally, there's no real cloud spend to track, so the
dashboard here shows illustrative/mocked numbers, clearly labeled as such.

---

## Tech Stack

- **Cluster**: kind (Kubernetes in Docker)
- **Orchestration**: Argo Workflows
- **Model Registry**: MLflow
- **Serving**: FastAPI + Kubernetes Deployment/Service
- **Dashboard**: Streamlit
- **Governance**: Kubernetes RBAC + simple audit log

## Status

🚧 In progress — see POC.md for scope, and phase checklist above for
current progress.

- [x] Phase 0 — kind cluster + Argo Workflows installed
- [x] Phase 1 (partial) — hello-world workflow validated end-to-end
- [x] Phase 1 (full) — train/evaluate/register pipeline (custom Docker image, Argo Workflow)
- [x] Phase 2 — MLflow model registry (self-built image, in-cluster, model registered and versioned)
- [ ] Phase 3 — model serving
- [ ] Phase 4 — governance (RBAC + audit log)
- [ ] Phase 5 — dashboard
- [ ] Phase 6 — docs & demo polish

See [DEBUG.md](./DEBUG.md) for the full log of real issues hit and fixes
applied while building this (RBAC, image pulls, Argo executor quirks,
kubectl context handling, etc.) — kept separate to keep this README
focused on what the project is and how it works.

## Repository Structure

```
mini-kubogent/
├── POC.md              # motive, plan, non-goals
├── README.md            # this file
├── setup.md             # step-by-step environment setup (Phase 0+)
├── DEBUG.md              # full troubleshooting log
├── argo-pipelines/       # Argo Workflow YAMLs
│   ├── hello-world.yaml
│   └── train-iris-model.yaml
├── mlflow/               # MLflow server image + K8s manifests
│   ├── Dockerfile
│   └── mlflow-deployment.yaml
├── training/              # Model Workbench - training container
│   ├── train.py
│   ├── requirements.txt
│   └── Dockerfile
├── inference-service/     # SERVE use case - FastAPI model endpoint
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── deployment.yaml
├── dashboard/              # Cluster Dashboard (Phase 5, in progress)
└── scripts/                # helper scripts
```

## What's Actually Running Right Now

As of Phase 3, the full loop is live on the local kind cluster:

1. **Argo Workflow** (`train-iris-model.yaml`) runs the `training/` container
2. Training container trains a RandomForest on Iris, logs metrics/params to
   **MLflow**, registers the model as `mini-kubogent-iris-classifier`, and
   fails the pipeline if accuracy drops below a quality-gate threshold
3. **MLflow** (self-built image, in-cluster, SQLite-backed) stores the
   experiment run and the model registry
4. **Inference Service** (FastAPI, `inference-service/`) loads the latest
   registered model version from MLflow on startup and serves it via
   `POST /predict`

This mirrors Kubogent's TRAIN → GOVERN → SERVE flow end-to-end, just at
local/CPU/single-node scale instead of EKS + GPU scale.

## Status

🚧 In progress — see [POC.md](./POC.md) for the motive and plan.

- [x] Phase 0 — kind cluster + Argo Workflows installed
- [x] Phase 1 (partial) — hello-world workflow validated end-to-end
- [x] Phase 1 (full) — train/evaluate/register pipeline (custom Docker image, Argo Workflow)
- [x] Phase 2 — MLflow model registry (self-built image, in-cluster, model registered and versioned)
- [x] Phase 3 — model serving (FastAPI inference service, live `/predict` endpoint)
- [ ] Phase 4 — governance (RBAC + audit log)
- [ ] Phase 5 — dashboard
- [ ] Phase 6 — docs & demo polish