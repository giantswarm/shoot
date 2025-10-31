# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
kubectl -n "$NAMESPACE" create secret generic openai-api-key --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:1.1.2-a31a1dde3e8782f00060c0306c33a28744d8f8b8
export NAMESPACE=org-giantswarm
export CLUSTERNAME=golem
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otlp-gateway.kube-system.svc.cluster.local:4318"
export QUERY="nodes not ready"
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME" "$QUERY"
```

# How to push latest image
```
az login
az acr login --name gsoci
docker pull gsoci.azurecr.io/giantswarm/shoot:vX.X.X
docker tag gsoci.azurecr.io/giantswarm/shoot:vX.X.X gsoci.azurecr.io/giantswarm/shoot:latest
docker push gsoci.azurecr.io/giantswarm/shoot:latest
``` 
