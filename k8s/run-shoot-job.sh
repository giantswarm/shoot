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

JOB=shoot-$(date +%s)

# Render and apply the Job
if [[ -z "${QUERY_ARG}" ]]; then
  QUERY_ARG="list namespaces"
fi

export NAMESPACE="$NS" CLUSTERNAME="$CLUSTER" JOB_NAME="$JOB" QUERY="$QUERY_ARG"
envsubst < k8s/job.shoot.yaml.tpl | kubectl apply -f -

# Actively watch for Complete or Failed (exit immediately on either), 20m timeout
deadline=$(( $(date +%s) + 1200 ))
while true; do
  # Query conditions; tolerate transient lookup errors
  complete=$(kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)
  failed=$(kubectl -n "$NS" get job "$JOB" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || true)

  if [[ "$failed" == "True" ]]; then
    echo "Job failed; showing status and logs" >&2
    kubectl -n "$NS" describe job "$JOB" || true
    kubectl -n "$NS" logs job/"$JOB" --all-containers=true --tail=-1 || true
    exit 1
  fi

  if [[ "$complete" == "True" ]]; then
    kubectl -n "$NS" logs job/"$JOB" --all-containers=true --tail=-1 || true
    exit 0
  fi

  if [[ $(date +%s) -ge $deadline ]]; then
    echo "Timeout waiting for job to complete or fail; showing status and logs" >&2
    kubectl -n "$NS" describe job "$JOB" || true
    kubectl -n "$NS" logs job/"$JOB" --all-containers=true --tail=-1 || true
    exit 1
  fi

  sleep 3
done


