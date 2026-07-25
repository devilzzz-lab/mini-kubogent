"""
Mini Kubogent - Model Workbench (training step)

Trains a small, fast scikit-learn classifier (Iris dataset) and logs
parameters, metrics, and the model itself to MLflow. This simulates
Kubogent's "Model Workbench" fine-tuning step, at a scale that runs in
seconds on CPU inside a kind cluster.
"""

import os
import sys
import mlflow
import mlflow.sklearn
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://mlflow-server.mlflow.svc.cluster.local:5000"
)
EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT", "mini-kubogent")

N_ESTIMATORS = int(os.environ.get("N_ESTIMATORS", 50))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", 5))


def main():
    print(f"Connecting to MLflow at {MLFLOW_TRACKING_URI}")
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    print("Loading dataset (Iris)")
    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    with mlflow.start_run() as run:
        print(f"Training RandomForestClassifier "
              f"(n_estimators={N_ESTIMATORS}, max_depth={MAX_DEPTH})")

        mlflow.log_param("n_estimators", N_ESTIMATORS)
        mlflow.log_param("max_depth", MAX_DEPTH)

        model = RandomForestClassifier(
            n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH, random_state=42
        )
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        f1 = f1_score(y_test, preds, average="macro")

        print(f"Accuracy: {acc:.4f}  F1(macro): {f1:.4f}")
        mlflow.log_metric("accuracy", acc)
        mlflow.log_metric("f1_macro", f1)

        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name="mini-kubogent-iris-classifier",
        )

        run_id = run.info.run_id
        print(f"MLflow run_id: {run_id}")

        # Fail the pipeline step if quality gate isn't met (evaluation gate)
        MIN_ACCURACY = float(os.environ.get("MIN_ACCURACY", 0.85))
        if acc < MIN_ACCURACY:
            print(f"FAILED quality gate: accuracy {acc:.4f} < {MIN_ACCURACY}")
            sys.exit(1)

        print("Model passed quality gate and was registered in MLflow.")


if __name__ == "__main__":
    main()
