#!/usr/bin/env bash
set -euo pipefail

NS=${1:-}
CLUSTER=${2:-}
IMAGE=${IMAGE:-}
if [[ -z "$NS" || -z "$CLUSTER" ]]; then
  echo "usage: $0 <namespace> <clustername>" >&2
  echo "hint: export IMAGE=ghcr.io/you/shoot:latest (or similar)" >&2
  exit 2
fi
if [[ -z "${IMAGE}" ]]; then
  echo "ERROR: IMAGE env var not set (e.g., IMAGE=ghcr.io/you/shoot:latest)" >&2
  exit 2
fi

JOB=shoot-$(date +%s)

# Render and apply the Job
export NAMESPACE="$NS" CLUSTERNAME="$CLUSTER" JOB_NAME="$JOB"
envsubst < k8s/job.shoot.yaml.tpl | kubectl apply -f -

# Wait for completion or failure (20m timeout)
if ! kubectl -n "$NS" wait --for=condition=complete --timeout=1200s job/"$JOB" 2>/dev/null; then
  echo "Job did not complete successfully; showing status and logs" >&2
  kubectl -n "$NS" describe job "$JOB" || true
  # print logs even on failure
  kubectl -n "$NS" logs job/"$JOB" --all-containers=true --tail=-1 || true
  exit 1
fi

# Print logs on success
kubectl -n "$NS" logs job/"$JOB" --all-containers=true --tail=-1


