FROM python:3.11-slim

RUN pip install --no-cache-dir mlflow==2.14.1

EXPOSE 5000

ENTRYPOINT ["mlflow", "server", \
    "--host=0.0.0.0", \
    "--port=5000", \
    "--backend-store-uri=sqlite:////mlflow-data/mlflow.db", \
    "--default-artifact-root=/mlflow-data/artifacts"]