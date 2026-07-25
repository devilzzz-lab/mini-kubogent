"""
Mini Kubogent - Inference Service

Loads the latest registered version of the Iris classifier from MLflow
and serves predictions over a simple REST API. This is the "SERVE" use
case from the Kubogent page - a self-hosted model endpoint your own
applications call directly, instead of an external LLM API.
"""

import os
import mlflow
import mlflow.pyfunc
from fastapi import FastAPI
from pydantic import BaseModel, Field

MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://mlflow-server.mlflow.svc.cluster.local:5000"
)
MODEL_NAME = os.environ.get("MODEL_NAME", "mini-kubogent-iris-classifier")
MODEL_STAGE_OR_VERSION = os.environ.get("MODEL_VERSION", "latest")

IRIS_CLASSES = ["setosa", "versicolor", "virginica"]

app = FastAPI(title="Mini Kubogent Inference Service")

model = None
loaded_model_uri = None


class IrisFeatures(BaseModel):
    sepal_length: float = Field(..., example=5.1)
    sepal_width: float = Field(..., example=3.5)
    petal_length: float = Field(..., example=1.4)
    petal_width: float = Field(..., example=0.2)


@app.on_event("startup")
def load_model():
    global model, loaded_model_uri
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    if MODEL_STAGE_OR_VERSION == "latest":
        model_uri = f"models:/{MODEL_NAME}/latest"
    else:
        model_uri = f"models:/{MODEL_NAME}/{MODEL_STAGE_OR_VERSION}"

    print(f"Loading model from: {model_uri}")
    model = mlflow.pyfunc.load_model(model_uri)
    loaded_model_uri = model_uri
    print("Model loaded successfully.")


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None, "model_uri": loaded_model_uri}


@app.get("/model-info")
def model_info():
    return {"model_name": MODEL_NAME, "model_uri": loaded_model_uri}


@app.post("/predict")
def predict(features: IrisFeatures):
    row = [[
        features.sepal_length,
        features.sepal_width,
        features.petal_length,
        features.petal_width,
    ]]
    pred = model.predict(row)
    class_index = int(pred[0])
    return {
        "prediction_index": class_index,
        "prediction_class": IRIS_CLASSES[class_index],
        "model_uri": loaded_model_uri,
    }
