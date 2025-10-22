# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
kubectl -n "$NAMESPACE" create secret generic openai-api-key --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:0.0.0-150327a884cbc5490e7953a3f1dcb03c52455641
export NAMESPACE=org-giantswarm
export CLUSTERNAME=golem
export OTLP_ENDPOINT="http://otlp-gateway.kube-system.svc.cluster.local:4318"
export QUERY="nodes not ready"
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME" "$QUERY"
```

# Otel TUI local
docker run --rm -it -p 4318:4318 --name otel-tui ymtdzzz/otel-tui:latest
