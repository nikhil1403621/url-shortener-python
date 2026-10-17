#!/usr/bin/env bash
set -e

# setup-k8s.sh: Sets up all three namespaces (qa, stage, prod) with Postgres, Redis, and App.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 1. Creating Namespaces (qa, stage, prod) ==="
kubectl apply -f "${DIR}/namespaces.yaml"

DOCKER_USER="${DOCKERHUB_USER:-nikhil1403621}"
DOCKER_TOKEN="${DOCKERHUB_TOKEN:-dummytoken}"

echo "=== 2. Configuring Docker Hub Pull Secrets in each Namespace ==="
for ns in qa stage prod; do
  echo "Creating dockerhub secret in namespace ${ns}..."
  kubectl create secret docker-registry dockerhub \
    --docker-username="${DOCKER_USER}" \
    --docker-password="${DOCKER_TOKEN}" \
    --namespace="${ns}" \
    --dry-run=client -o yaml | kubectl apply -f -
done

echo "=== 3. Deploying Workloads to QA ==="
kubectl apply -f "${DIR}/qa/postgres.yaml"
kubectl apply -f "${DIR}/qa/redis.yaml"
kubectl apply -f "${DIR}/qa/app.yaml"

echo "=== 4. Deploying Workloads to STAGE ==="
kubectl apply -f "${DIR}/stage/postgres.yaml"
kubectl apply -f "${DIR}/stage/redis.yaml"
kubectl apply -f "${DIR}/stage/app.yaml"

echo "=== 5. Deploying Workloads to PROD ==="
kubectl apply -f "${DIR}/prod/postgres.yaml"
kubectl apply -f "${DIR}/prod/redis.yaml"
kubectl apply -f "${DIR}/prod/app.yaml"

echo "=== All Kubernetes resources created successfully across qa, stage, and prod! ==="
