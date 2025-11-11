# Deployment
```
Replace <cluster_id> and <org-namespace> and deploy on Management Cluster

apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  labels:
    app: shoot
    application.giantswarm.io/team: phoenix
    giantswarm.io/cluster: <cluster_id>
  name: <cluster_id>-shoot
  namespace: org-giantswarm
spec:
  chart:
    spec:
      chart: shoot
      reconcileStrategy: ChartVersion
      sourceRef:
        kind: HelmRepository
        name: <cluster_id>-default-test
      version: 1.1.2
  install:
    createNamespace: true
    remediation:
      retries: -1
  interval: 5m
  kubeConfig:
    secretRef:
      name: <cluster_id>-kubeconfig
  releaseName: <cluster_id>-shoot
  storageNamespace: <org-namespace>
  suspend: false
  targetNamespace: <org-namespace>
  timeout: 15m
  upgrade:
    remediation:
      retries: -1
  valuesFrom:
    - kind: ConfigMap
      name: <cluster_id>-cluster-values
      valuesKey: values
```

# Test
Open a shell in the pod and `curl 127.0.0.1:8000/ --data '{"query": "list namespaces"}'`

# How to push latest image
```
az login
az acr login --name gsoci
docker pull gsoci.azurecr.io/giantswarm/shoot:vX.X.X
docker tag gsoci.azurecr.io/giantswarm/shoot:vX.X.X gsoci.azurecr.io/giantswarm/shoot:latest
docker push gsoci.azurecr.io/giantswarm/shoot:latest
```
