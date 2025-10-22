apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    observability.giantswarm.io/tenant: giantswarm
spec:
  backoffLimit: 0
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      restartPolicy: Never
      containers:
        - name: shoot
          image: ${IMAGE}
          imagePullPolicy: IfNotPresent
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            seccompProfile:
              type: RuntimeDefault
          env:
            - name: DEBUG
              value: "true"
            - name: QUERY
              value: "${QUERY}"
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: openai-api-key
                  key: OPENAI_API_KEY
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: "${OTEL_EXPORTER_OTLP_ENDPOINT}"
            - name: OTEL_RESOURCE_ATTRIBUTES
              value: "service.name=shoot"
            - name: KUBECONFIG
              value: /home/app/k8s/kubeconfig.yaml
          volumeMounts:
            - name: kubeconfig
              mountPath: /home/app/k8s
      volumes:
        - name: kubeconfig
          secret:
            secretName: ${CLUSTERNAME}-kubeconfig
            items:
              - key: value
                path: kubeconfig.yaml


