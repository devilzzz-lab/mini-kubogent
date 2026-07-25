# POC — Mini Kubogent

## Motive

- Aivar Innovations' **Kubogent AI** is an enterprise product that turns Kubernetes (on AWS EKS) into a governed platform for training, registering, and serving AI models.
- It combines pipeline orchestration, a model registry, GPU-aware infra, and compliance/governance tooling into one system.
- **Mini Kubogent** is a local, learning-focused proof of concept — the goal is **not** to rebuild Kubogent commercially.
- The goal is to understand, hands-on, how each piece of a platform like Kubogent actually works under the hood.
- Uses a local `kind` (Kubernetes-in-Docker) cluster instead of real EKS + GPUs.
- This is a study project — every real cloud/GPU/enterprise feature that can't run locally is explicitly documented in [README.md](./README.md) instead of faked.

---

## Plan (High Level)

1. Stand up a local Kubernetes cluster with `kind`.
2. Run a pipeline orchestrator (**Argo Workflows**) to simulate the "Pipeline Designer" — fetch data → train a small model → evaluate → register.
3. Run **MLflow** as the "Model Catalog" — track experiments, register model versions.
4. Fine-tune / train a small CPU-friendly model as the "Model Workbench" step, triggered by the Argo pipeline.
5. Serve the trained model via a simple **FastAPI** inference service, deployed as a Kubernetes Deployment + Service — this is the "SERVE" use case from the Kubogent page.
6. Apply basic **RBAC** and a simple **audit log** of every pipeline run — this is the "GOVERN" use case.
7. Build a lightweight **Streamlit dashboard** — the "Cluster Dashboard" — pulling live pod/job status from the Kubernetes API and model info from the MLflow API.
   - Cost/GPU numbers shown here are clearly labeled as simulated, since there is no real billing or GPU hardware locally.
8. Document, in README.md, every Kubogent concept that is **not** built here (GPU partitioning, A100s, micro-VM isolation, service mesh, multi-cloud, Kubeflow) and explain what they are and why they're out of scope for a local kind cluster.

---

## What "Done" Looks Like

- `kind create cluster` boots a working cluster.
- One command runs an Argo Workflow that trains a tiny model and registers it in MLflow.
- The trained model is deployed and reachable via a REST endpoint.
- The dashboard shows the pipeline run, the registered model version, and the live serving pod — end to end, in one demo.
- README.md clearly explains what's real vs. simulated vs. conceptual.

---

## Non-Goals

- No real GPU workloads.
- No real EKS / AWS deployment (kind only).
- No Kubeflow — Argo Workflows used directly, since Kubeflow Pipelines itself runs on Argo underneath, keeping the POC lightweight without losing the concept.
- No Istio / service mesh implementation (documented conceptually only).
- No real cost/billing integration (mocked/labeled numbers only).