# Run shoot as a Kubernetes Job
```bash
export OPENAI_API_KEY="sk-..."
export NAMESPACE=org-giantswam
export CLUSTERNAME=test
kubectl -n "$NAMESPACE" create secret generic kubeconfig-"$CLUSTERNAME" \
  --from-file=kubeconfig.yaml=./kubeconfig.yaml
kubectl -n "$NAMESPACE" create secret generic openai-api-key \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY"
export IMAGE=gsoci.azurecr.io/giantswarm/shoot:0.0.0-818a3e298ef5e51fbaae2cb5b93ef2b7d592aa3c
bash k8s/run-shoot-job.sh "$NAMESPACE" "$CLUSTERNAME"
```
