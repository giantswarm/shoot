#!/usr/bin/env bash
set -euo pipefail

NS=${1:-}
CLUSTER=${2:-}
QUERY_ARG=${3:-}
IMAGE=${IMAGE:-}
if [[ -z "$NS" || -z "$CLUSTER" ]]; then
  echo "usage: $0 <namespace> <clustername> [query]" >&2
  echo "hint: export IMAGE=ghcr.io/you/shoot:latest (or similar)" >&2
  exit 2
fi
if [[ -z "${IMAGE}" ]]; then
  echo "ERROR: IMAGE env var not set (e.g., IMAGE=ghcr.io/you/shoot:latest)" >&2
  exit 2
fi

POD=shoot-$(date +%s)

# Render and apply the Pod
if [[ -z "${QUERY_ARG}" ]]; then
  QUERY_ARG="list namespaces"
fi

export NAMESPACE="$NS" CLUSTERNAME="$CLUSTER" POD_NAME="$POD" QUERY="$QUERY_ARG"
envsubst < k8s/job.shoot.yaml.tpl | kubectl apply -f -

# Actively watch for Succeeded or Failed (exit immediately on either), 20m timeout
deadline=$(( $(date +%s) + 1200 ))
while true; do
  # Query phase; tolerate transient lookup errors
  phase=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")

  if [[ "$phase" == "Failed" ]]; then
    echo "Pod failed; showing status and logs" >&2
    kubectl -n "$NS" describe pod "$POD" || true
    kubectl -n "$NS" logs pod/"$POD" --all-containers=true --tail=-1 || true
    exit 1
  fi

  if [[ "$phase" == "Succeeded" ]]; then
    kubectl -n "$NS" logs pod/"$POD" --all-containers=true --tail=-1 || true
    exit 0
  fi

  if [[ $(date +%s) -ge $deadline ]]; then
    echo "Timeout waiting for pod to complete or fail; showing status and logs" >&2
    kubectl -n "$NS" describe pod "$POD" || true
    kubectl -n "$NS" logs pod/"$POD" --all-containers=true --tail=-1 || true
    exit 1
  fi

  sleep 3
done


