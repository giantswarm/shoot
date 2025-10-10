# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
export NAMESPACE=org-giantswam
export CLUSTERNAME=test
kubectl -n "$NAMESPACE" create secret generic kubeconfig-"$CLUSTERNAME" \
  --from-file=kubeconfig.yaml=./kubeconfig.yaml
kubectl -n "$NAMESPACE" create secret generic openai-api-key \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:0.0.0-45c96e2dc13965ecd1939bd27c33870ec3df8547
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME"
```
