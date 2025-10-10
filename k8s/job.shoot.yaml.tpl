apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
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
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: openai-api-key
                  key: OPENAI_API_KEY
            - name: KUBECONFIG
              value: /app/kubeconfig.yaml
          volumeMounts:
            - name: kubeconfig
              mountPath: /app/kubeconfig.yaml
              subPath: kubeconfig.yaml
      volumes:
        - name: kubeconfig
          secret:
            secretName: kubeconfig-${CLUSTERNAME}
            items:
              - key: kubeconfig.yaml
                path: kubeconfig.yaml


