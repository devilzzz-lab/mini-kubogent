# Mini Kubogent

A local, hands-on proof of concept built to **study how Aivar's Kubogent AI service works** — implemented on a local `kind` Kubernetes cluster instead of production EKS + GPU infrastructure.

> This is a learning project, not a commercial clone. See [POC.md](./POC.md) for the full motive, plan, and non-goals.

---

## Why This Project Exists

- Kubogent AI is Aivar's product for running enterprise AI/ML workloads on Kubernetes (EKS), with governance, GPU management, and MLOps tooling built in.
- Reading the marketing page alone doesn't teach you how the pieces actually work.
- This project rebuilds the **core mechanics** — pipeline → registry → serving → dashboard — locally.
- Uses the same open-source building blocks Kubogent is likely built on: Argo, MLflow, and native Kubernetes primitives.

## What Kubogent Actually Does

- **Kubogent = Kubernetes + Agent.**
- Turns EKS into a governed platform where a company can fine-tune, register, deploy, and monitor its own AI models on its own infrastructure — instead of calling an external LLM API.
- You bring your AWS account and GPUs; Kubogent configures the platform layer on top: pipelines, registry, dashboard, security, and multi-tenant GPU sharing.

---

## Full Feature List: Kubogent Page vs. This Project

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

## Buildable vs. Conceptual-Only — Summary Table

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

## Tech Stack

- **Cluster** — kind (Kubernetes in Docker)
- **Orchestration** — Argo Workflows
- **Model Registry** — MLflow
- **Serving** — FastAPI + Kubernetes Deployment/Service
- **Dashboard** — Streamlit
- **Governance** — Kubernetes RBAC + simple audit log

---

## Project Phases

- **Phase 0 — Environment Setup**
  👉 Full step-by-step commands: [setup.md](./setup.md)

- **Phase 1 — Pipeline Orchestration (Argo Workflows)**
  - Install Argo Workflows on the cluster
  - Write a Workflow YAML: fetch data → train tiny model → evaluate → log to MLflow
  - Trigger and verify a run via `argo submit`

- **Phase 2 — Model Registry (MLflow)**
  - Deploy MLflow tracking server in-cluster
  - Pipeline logs metrics, parameters, and registers the trained model
  - Verify model version appears in the MLflow UI

- **Phase 3 — Model Serving**
  - Package the registered model into a small FastAPI inference service
  - Deploy as a Kubernetes Deployment + Service
  - Test with a `curl`/Postman request to get a live prediction

- **Phase 4 — Governance Basics**
  - Apply Kubernetes RBAC roles (read-only vs. pipeline-runner)
  - Log every pipeline run (who/when/what model version) to a simple audit log

- **Phase 5 — Dashboard**
  - Live pod/job status (via Kubernetes API)
  - Registered model versions (via MLflow API)
  - A clearly-labeled "simulated" GPU utilization / cost panel

- **Phase 6 — Documentation & Demo Polish**
  - Finalize README + POC
  - Record/demo: run pipeline → show registry update → hit live endpoint → show dashboard

---

## Concepts Not Built Here — Explained for Study

Real Kubogent capabilities that need cloud GPU hardware or enterprise-grade networking a local `kind` cluster can't provide. Documented so they can still be understood and spoken to.

### GPU Partitioning / A100s / MIG
- MIG (Multi-Instance GPU) lets a single physical GPU be split into isolated instances, each with dedicated memory and compute.
- Lets a platform like Kubogent run multiple models/tenants on one GPU without interference.
- Needs real NVIDIA data-center GPUs + the NVIDIA GPU Operator on Kubernetes — can't be simulated on a laptop.

### Multi-Cloud / Zero Vendor Lock-In
- Kubogent is built on Kubernetes-native, open tooling (Argo, MLflow-compatible registries, standard K8s APIs) rather than cloud-proprietary services.
- Same platform config can in theory deploy on EKS, AKS, GKE, or on-prem with minimal changes.
- It's an architectural property of using standard K8s primitives — not something a single demo "runs."

### Service Mesh for AI
- A service mesh (Istio, Linkerd) sits alongside services (usually via sidecars) and handles routing, retries, load balancing, mTLS, and observability — without changing app code.
- For AI workloads: canary-deploying a new model version, routing a % of traffic to it, monitoring latency/errors per version.
- Istio *can* run on `kind`, but is deliberately left out here to keep the POC lightweight; orchestration + registry pieces already demonstrate the same platform-engineering skill.

### Micro-VM Isolation
- Firecracker (used by AWS Lambda/Fargate) or Kata Containers run each workload inside a lightweight VM instead of a standard container.
- Containers share the host kernel; micro-VMs don't — much stronger tenant isolation.
- Needs specific node-level container runtime config; not practical inside Docker-in-Docker (`kind` runs nodes as containers).

### Zero-Latency Scaling
- Marketing term for fast, predictive autoscaling of inference endpoints without cold-start delay.
- Typically implemented via Kubernetes HPA + pre-warmed pod pools, or KEDA event-driven scaling.
- "Zero-latency" pre-warming at scale needs real traffic patterns and cloud infra to demonstrate meaningfully.

### Kubeflow
- Full ML platform for Kubernetes: Jupyter notebook management, Kubeflow Pipelines (built on Argo Workflows), model serving (KServe), hyperparameter tuning (Katib).
- This project uses **Argo Workflows directly** instead of full Kubeflow, since Kubeflow Pipelines itself runs on Argo under the hood.
- Same orchestration mechanics, far less setup overhead — matters on a local cluster.

### Real Cost / Billing Visibility
- Kubogent's dashboard shows real GPU cost tracking against actual AWS billing data.
- No real cloud spend locally, so the dashboard shows illustrative/mocked numbers, clearly labeled as such.

---

## Status

🚧 In progress — see [POC.md](./POC.md) for the motive and plan, and the phase checklist above for current progress.