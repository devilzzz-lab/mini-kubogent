"""
Mini Kubogent - Cluster Dashboard (Phase 5)

Reads LIVE data from three real sources:
  1. Kubernetes API   -> pod / workflow status
  2. MLflow API       -> registered model versions
  3. Audit log PVC     -> who/when/what ran (Phase 4 governance record)

The GPU utilization / cost panel is CLEARLY LABELED as simulated data,
since there's no real GPU hardware or cloud billing on a local kind
cluster.

Run locally against the cluster (see dashboard/README.md for exact steps):
    streamlit run dashboard/app.py
"""

import os
import random
import subprocess

import pandas as pd
import streamlit as st
from kubernetes import client, config
from mlflow.tracking import MlflowClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KIND_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-cloudops")
ARGO_NAMESPACE = os.environ.get("ARGO_NAMESPACE", "argo")
MLFLOW_NAMESPACE = os.environ.get("MLFLOW_NAMESPACE", "mlflow")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
AUDIT_PVC_NAME = os.environ.get("AUDIT_PVC_NAME", "audit-log-pvc")

st.set_page_config(page_title="Mini Kubogent Dashboard", layout="wide")


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
@st.cache_resource
def get_k8s_client():
    config.load_kube_config(context=KIND_CONTEXT)
    return client.CoreV1Api()


def load_pod_status():
    v1 = get_k8s_client()
    pods = v1.list_namespaced_pod(namespace=ARGO_NAMESPACE)
    rows = []
    for pod in pods.items:
        labels = pod.metadata.labels or {}
        rows.append(
            {
                "pod": pod.metadata.name,
                "workflow": labels.get("workflows.argoproj.io/workflow", "-"),
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "started": pod.status.start_time.strftime("%Y-%m-%d %H:%M:%S")
                if pod.status.start_time
                else "-",
            }
        )
    return pd.DataFrame(rows)


def load_model_registry():
    mclient = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    rows = []
    for rm in mclient.search_registered_models():
        # Now that the client version (2.14.1) matches the server version
        # (2.14.1) exactly, the filter-based query works correctly and
        # returns full version history, not just the latest.
        for mv in mclient.search_model_versions(f"name='{rm.name}'"):
            rows.append(
                {
                    "model": rm.name,
                    "version": int(mv.version),
                    "stage": mv.current_stage,
                    "run_id": mv.run_id[:8] + "…",
                    "status": mv.status,
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["model", "version"], ascending=[True, False])
    return df


def load_audit_log():
    """Spin a throwaway pod that mounts the audit PVC, cat the file, capture
    stdout, then let the pod self-delete (same pattern used manually in
    setup.md Phase 4)."""
    overrides = (
        '{"spec":{"containers":[{"name":"audit-viewer","image":"busybox",'
        '"command":["cat","/audit/audit.log"],'
        '"volumeMounts":[{"name":"audit-log","mountPath":"/audit"}]}],'
        f'"volumes":[{{"name":"audit-log","persistentVolumeClaim":'
        f'{{"claimName":"{AUDIT_PVC_NAME}"}}}}]}}}}'
    )
    cmd = [
        "kubectl",
        "-n",
        ARGO_NAMESPACE,
        "--context",
        KIND_CONTEXT,
        "run",
        "audit-viewer-dashboard",
        "--rm",
        "-i",
        "--restart=Never",
        "--image=busybox",
        f"--overrides={overrides}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        lines = [
            line
            for line in result.stdout.splitlines()
            if "," in line and line[0:4].isdigit()
        ]
    except Exception as e:
        return pd.DataFrame(), str(e)

    rows = []
    for line in lines:
        parts = line.split(",")
        entry = {}
        entry["timestamp"] = parts[0]
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                entry[k] = v
        rows.append(entry)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("timestamp", ascending=False)
    return df, None


def load_simulated_gpu_cost():
    """CLEARLY SIMULATED. No real GPU hardware or cloud billing exists on a
    local kind cluster - these numbers exist only to show what the panel
    would look like on real EKS + GPU infra."""
    random.seed(42)  # stable across refreshes for a cleaner demo
    return {
        "gpu_utilization_pct": random.randint(35, 78),
        "gpu_memory_used_gb": round(random.uniform(8, 22), 1),
        "gpu_memory_total_gb": 40,
        "hourly_cost_usd": round(random.uniform(2.10, 4.90), 2),
        "monthly_projected_usd": round(random.uniform(1500, 3500), 0),
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("🧠 Mini Kubogent — Cluster Dashboard")
st.caption(
    "Local kind cluster · standing in for Kubogent's EKS + GPU dashboard. "
    "Everything below is LIVE except the clearly-labeled cost/GPU panel."
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔧 Pipeline Status", "📦 Model Registry", "📝 Audit Log", "💰 Cost / GPU (simulated)"]
)

with tab1:
    st.subheader("Pods in the `argo` namespace")
    try:
        df = load_pod_status()
        if df.empty:
            st.info("No pods found. Run a workflow first: `argo submit -n argo argo-pipelines/train-iris-model.yaml`")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Couldn't reach the Kubernetes API: {e}")

with tab2:
    st.subheader("Registered models (MLflow)")
    try:
        df = load_model_registry()
        if df.empty:
            st.info("No registered models yet. Run the training pipeline first.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(
            f"Couldn't reach MLflow at {MLFLOW_TRACKING_URI}: {e}\n\n"
            "Make sure `kubectl -n mlflow port-forward svc/mlflow-server 5000:5000` is running."
        )

with tab3:
    st.subheader("Governance audit trail (who / when / what ran)")
    df, err = load_audit_log()
    if err:
        st.error(f"Couldn't read the audit log: {err}")
    elif df.empty:
        st.info("Audit log is empty. Run the training pipeline first.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("GPU Utilization & Cost")
    st.warning(
        "⚠️ SIMULATED DATA — this laptop has no GPU and there's no real cloud "
        "billing. On production Kubogent (real EKS + GPU nodes) this panel "
        "would pull actual NVIDIA DCGM metrics and AWS Cost Explorer data."
    )
    metrics = load_simulated_gpu_cost()
    c1, c2, c3 = st.columns(3)
    c1.metric("GPU Utilization", f"{metrics['gpu_utilization_pct']}%")
    c2.metric(
        "GPU Memory",
        f"{metrics['gpu_memory_used_gb']} / {metrics['gpu_memory_total_gb']} GB",
    )
    c3.metric("Hourly Cost", f"${metrics['hourly_cost_usd']}")
    st.metric("Projected Monthly Cost", f"${metrics['monthly_projected_usd']:,.0f}")