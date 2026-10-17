#!/usr/bin/env bash
set -e

# rollout-demo.sh: Demonstrates the live rolling update and image verification in QA.

APP_NAME="url-shortener-app"
NAMESPACE="qa"

echo "=== Step 1: Triggering Rollout Restart ==="
kubectl rollout restart deployment/${APP_NAME} -n ${NAMESPACE}

echo "=== Step 2: Waiting for Rollout Status to Complete ==="
kubectl rollout status deployment/${APP_NAME} -n ${NAMESPACE}

echo "=== Step 3: Verifying Running Image in Namespace ${NAMESPACE} ==="
kubectl get pods -n ${NAMESPACE} -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}'

echo "=== Step 4: Verifying Image ID Digest ==="
FIRST_POD=$(kubectl get pods -n ${NAMESPACE} -l app=${APP_NAME} -o jsonpath='{.items[0].metadata.name}')
echo "Inspecting Pod: ${FIRST_POD}"
kubectl describe pod "${FIRST_POD}" -n ${NAMESPACE} | grep -i "image id"
