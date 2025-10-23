# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
kubectl -n "$NAMESPACE" create secret generic openai-api-key --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:0.0.0-cd49af57891ec9290ea2c860adda78bba0a50bff
export NAMESPACE=org-giantswarm
export CLUSTERNAME=golem
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otlp-gateway.kube-system.svc.cluster.local:4318"
export QUERY="nodes not ready"
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME" "$QUERY"
```
