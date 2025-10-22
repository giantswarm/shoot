# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
kubectl -n "$NAMESPACE" create secret generic openai-api-key --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:0.0.0-24aa8619017da1fd1d24d6cf1e222dfc2d4f2caf
export NAMESPACE=org-giantswarm
export CLUSTERNAME=golem
export OTLP_ENDPOINT="http://otlp-gateway.kube-system.svc.cluster.local:4318"
export QUERY="nodes not ready"
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME" "$QUERY"
```

# Otel TUI local
docker run --rm -it -p 4318:4318 --name otel-tui ymtdzzz/otel-tui:latest
