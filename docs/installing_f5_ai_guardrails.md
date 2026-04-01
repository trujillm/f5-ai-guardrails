# Installing F5 AI Guardrails on OpenShift

This guide walks through deploying **F5 AI Guardrails** (powered by Calypso AI) on a Red Hat OpenShift cluster with NVIDIA GPU nodes. It covers operator installation, OpenShift-specific configuration, and integration with a LlamaStack inference endpoint.

Based on the official Red Hat Operator installation baseline and enhanced with validated operational fixes required for successful deployment.

---

## Table of contents

- [Infrastructure requirements](#infrastructure-requirements)
- [Key components and placement](#key-components-and-placement)
- [Step 1: Install prerequisites](#step-1-install-prerequisites)
- [Step 2: Install F5 AI Security Operator](#step-2-install-f5-ai-security-operator)
- [Step 3: Required OpenShift configuration](#step-3-required-openshift-configuration)
- [Step 4: Route configuration](#step-4-route-configuration)
- [Step 5: Prefect Worker RBAC](#step-5-prefect-worker-rbac)
- [Step 6: LlamaStack integration](#step-6-llamastack-integration)
- [Common failure patterns](#common-failure-patterns)

---

## Infrastructure requirements

### CPU node (required)

- 16 vCPUs
- 32 GiB RAM
- x86_64 architecture
- 100 GiB persistent storage

### Worker nodes (per GPU-enabled component)

- 4 vCPUs
- 16 GiB RAM (32 GiB recommended for Red Team)
- 100 GiB persistent storage

### GPU nodes

- Dedicated CUDA-compatible GPU (NVIDIA A40 or equivalent)
- **AI Guardrails Scanner:** Minimum 24 GB VRAM, 100 GiB persistent storage
- **AI Red Team:** Minimum 48 GB VRAM, 200 GiB persistent storage recommended
- GPU must not be shared with other workloads

### Verification

```bash
# Verify nodes
oc get nodes -o wide

# Verify GPU allocatable
oc get node -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'

# Verify storage classes
oc get storageclass
```

---

## Key components and placement

| Component | Namespace | Description |
|-----------|-----------|-------------|
| Operator (controller-manager) | `f5-ai-sec` | Manages all F5 AI Security components via Helm charts |
| Moderator + PostgreSQL | `cai-moderator` | Web UI + API and backing database. CPU + storage; no GPU required |
| Prefect Server + Worker | `prefect` | Workflow orchestration for scans and red-team runs. CPU-based |
| AI Guardrails Scanner | `cai-scanner` | Executes inline scans against the LLM endpoint. Requires GPU |
| AI Red Team Worker | `cai-redteam` | Runs adversarial red-team workloads. Requires GPU |

---

## Step 1: Install prerequisites

### 1.1 Install Node Feature Discovery Operator

1. OpenShift Console → **OperatorHub** → Search `Node Feature Discovery Operator` → **Install**
2. After installation: **Installed Operators** → **Node Feature Discovery** → **Create NodeFeatureDiscovery** → Accept defaults

**Verification:**

```bash
oc get pods -n openshift-nfd
oc get node --show-labels | grep feature.node.kubernetes.io || true
```

### 1.2 Install NVIDIA GPU Operator

1. OpenShift Console → **OperatorHub** → Search `GPU Operator` → **Install**
2. After installation: **Installed Operators** → **NVIDIA GPU Operator** → **Create ClusterPolicy** → Accept defaults

**Verification:**

```bash
oc get pods -n nvidia-gpu-operator
oc describe node <gpu-node> | grep -i nvidia
```

---

## Step 2: Install F5 AI Security Operator

> **Note:** This operator requires pulling containers from an authenticated registry and a valid license. Contact the [F5 AI Security Sales Team](https://www.f5.com/products/get-f5?ls=meta#contactsales) to obtain these before installation.

### 2.1 Create namespace and registry secret

```bash
export DOCKER_USERNAME='<registry-username>'
export DOCKER_PASSWORD='<registry-password>'
export DOCKER_EMAIL='<your-email>'

oc new-project f5-ai-sec

oc create secret docker-registry regcred \
  -n f5-ai-sec \
  --docker-username=$DOCKER_USERNAME \
  --docker-password=$DOCKER_PASSWORD \
  --docker-email=$DOCKER_EMAIL
```

### 2.2 Install operator from OperatorHub

1. OpenShift Console → **OperatorHub** → Search `F5 AI Security Operator`
2. Install into namespace `f5-ai-sec`

**Verification:**

```bash
oc -n f5-ai-sec get pods
# Expected:
# NAME                                      READY   STATUS    RESTARTS   AGE
# controller-manager-6f784bd96d-z6sbh       1/1     Running   1          43s

oc -n f5-ai-sec get csv
# Expected:
# NAME                              DISPLAY                    VERSION   PHASE
# f5-ai-security-operator.v0.4.3   F5 Ai Security Operator    0.4.3     Succeeded

oc -n f5-ai-sec get crd | grep ai.security.f5.com
# Expected:
# securityoperators.ai.security.f5.com
```

### 2.3 Create SecurityOperator custom resource

Apply the following CR. Customize the values marked with `< >`:

```yaml
apiVersion: ai.security.f5.com/v1alpha1
kind: SecurityOperator
metadata:
  name: security-operator-demo
  namespace: f5-ai-sec
spec:
  registryAuth:
    existingSecret: "regcred"
  postgresql:
    enabled: true
    values:
      postgresql:
        auth:
          password: "pass"
  jobManager:
    enabled: true
  moderator:
    enabled: true
    values:
      env:
        CAI_MODERATOR_BASE_URL: https://<your-hostname>
      secrets:
        CAI_MODERATOR_DB_ADMIN_PASSWORD: "pass"
        CAI_MODERATOR_DEFAULT_LICENSE: "<VALID_LICENSE_FROM_F5>"
  scanner:
    enabled: true
  redTeam:
    enabled: true
```

> **Important:**
> - `CAI_MODERATOR_BASE_URL` — set to your cluster's public hostname (e.g., `https://aisec.apps.<cluster-domain>`)
> - `CAI_MODERATOR_DEFAULT_LICENSE` — use the base64 license blob obtained from F5
> - For **external PostgreSQL** (recommended for production), replace `postgresql.enabled: true` with:
>   ```yaml
>   env:
>     CAI_MODERATOR_DB_HOST: <my-external-db-hostname>
>   secrets:
>     CAI_MODERATOR_DB_ADMIN_PASSWORD: <my-external-db-password>
>   ```

**Verification:**

```bash
oc -n f5-ai-sec get securityoperator
oc -n f5-ai-sec get securityoperator security-operator-demo -o yaml | sed -n '/status:/,$p'
```

---

## Step 3: Required OpenShift configuration

### 3.1 Apply required SCC policies

OpenShift's default restricted SCC prevents F5 AI Guardrails components from running. Apply `anyuid` to all relevant service accounts:

```bash
oc adm policy add-scc-to-user anyuid -z cai-moderator-sa -n cai-moderator
oc adm policy add-scc-to-user anyuid -z default           -n cai-moderator
oc adm policy add-scc-to-user anyuid -z default           -n prefect
oc adm policy add-scc-to-user anyuid -z prefect-server    -n prefect
oc adm policy add-scc-to-user anyuid -z prefect-worker    -n prefect
oc adm policy add-scc-to-user anyuid -z cai-scanner       -n cai-scanner
oc adm policy add-scc-to-user anyuid -z cai-redteam-worker -n cai-redteam
```

### 3.2 Force PostgreSQL retry (if stuck at 0/1)

If the PostgreSQL StatefulSet does not become ready after SCC is applied:

```bash
oc -n cai-moderator scale sts/cai-moderator-postgres-cai-postgresql --replicas=0
oc -n cai-moderator scale sts/cai-moderator-postgres-cai-postgresql --replicas=1
```

### 3.3 Restart all components

```bash
oc -n cai-moderator rollout restart deploy
oc -n prefect       rollout restart deploy
oc -n cai-scanner   rollout restart deploy
oc -n cai-redteam   rollout restart deploy
```

### 3.4 Verify all pods

```bash
# PostgreSQL
oc -n cai-moderator get statefulset
oc -n cai-moderator get pods | grep postgres

# Moderator
oc -n cai-moderator get pods | grep cai-moderator

# Scanner
oc -n cai-scanner get pods

# Red Team
oc -n cai-redteam get pods

# Prefect
oc -n prefect get pods

# Services and endpoints
oc -n cai-moderator get svc
oc -n cai-moderator get endpoints
```

---

## Step 4: Route configuration

Create two OpenShift routes to split UI and Auth traffic. Replace `<your-hostname>` with your cluster's public hostname (e.g., `aisec.apps.<cluster-domain>`):

```bash
# UI route — all paths
oc -n cai-moderator create route edge cai-moderator-ui \
  --service=cai-moderator \
  --port=5500 \
  --hostname=<your-hostname> \
  --path=/

# Auth route — /auth path
oc -n cai-moderator create route edge cai-moderator-auth \
  --service=cai-moderator \
  --port=8080 \
  --hostname=<your-hostname> \
  --path=/auth
```

**Verification:**

```bash
oc get route -n cai-moderator
```

**Access the UI:**

```
https://<your-hostname>
Default credentials: admin / pass
```

Update the admin email address on first login.

---

## Step 5: Prefect Worker RBAC

The `prefect-worker` controller watches Kubernetes Pods and Jobs at cluster scope. Without this RBAC, prefect-worker logs show repeated `403 Forbidden` errors. This is required for Red Team and scheduled scan workflows.

```bash
# ClusterRole: allow prefect-worker to watch pods/jobs/events cluster-wide
oc apply -f - <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prefect-worker-watch-cluster
rules:
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["get","list","watch"]
- apiGroups: [""]
  resources: ["pods","pods/log","events"]
  verbs: ["get","list","watch"]
YAML

# Bind to the prefect-worker ServiceAccount
oc apply -f - <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prefect-worker-watch-cluster
subjects:
- kind: ServiceAccount
  name: prefect-worker
  namespace: prefect
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: prefect-worker-watch-cluster
YAML

# Restart prefect-worker
oc -n prefect rollout restart deploy/prefect-worker
```

**Verification:**

```bash
# Confirm RBAC errors have stopped
oc -n prefect logs deploy/prefect-worker --tail=200 | egrep -i 'forbidden|rbac|permission|denied' || echo "OK: no RBAC errors detected"

# Confirm binding exists
oc get clusterrolebinding prefect-worker-watch-cluster
```

---

## Step 6: LlamaStack integration

Configure the F5 AI Guardrails scanner to use the LlamaStack inference endpoint as the target model.

### 6.1 Create an API token

1. Log into the Moderator UI at `https://<your-hostname>`
2. Navigate to **API Tokens**
3. Click **Create Token** and copy the token immediately (shown only once)

### 6.2 Configure the scanner endpoint

In the Moderator UI, configure the scanner to point to the LlamaStack OpenAI-compatible endpoint:

| Field | Value |
|-------|-------|
| Provider | `llamastack` |
| Model | `llama-3-2-1b-instruct-quantized/RedHatAI/Llama-3.2-1B-Instruct-quantized.w8a8` |
| API Key | `dummy` (auth handled by the route/gateway layer) |
| Endpoint | `http://llamastack-http-<namespace>.apps.<cluster-domain>/v1/openai/v1/chat/completions` |

### 6.3 Verify end-to-end

Test a request through the guardrails endpoint:

```bash
curl -sk -X POST https://<your-hostname>/openai/llamastack/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "model": "llama-3-2-1b-instruct-quantized/RedHatAI/Llama-3.2-1B-Instruct-quantized.w8a8",
    "messages": [{"role": "user", "content": "say hi"}],
    "max_tokens": 20
  }'
```

A successful response confirms that requests flow through the guardrails proxy to LlamaStack and back.

---

## Common failure patterns

| # | Symptom | Root Cause | Fix |
|---|---------|------------|-----|
| 1 | PostgreSQL stuck at 0/1 | Missing `anyuid` SCC | [Step 3.1](#31-apply-required-scc-policies) |
| 2 | Prefect logs show `403 Forbidden` | Missing cluster-scope RBAC | [Step 5](#step-5-prefect-worker-rbac) |
| 3 | UI loads blank or black page | Missing `/auth` route | [Step 4](#step-4-route-configuration) |
| 4 | Operator stuck in `Installing` / controller-manager CrashLoopBackOff | Missing SCC permissions for operator SA | Grant SCC ClusterRole — see below |
| 5 | controller-manager OOMKilled | Default 128Mi memory limit insufficient | Patch memory to 512Mi — see below |
| 6 | "Invalid License" after reinstall | Encryption key mismatch in settings table | Clear stale settings — see below |
| 7 | "Internal error" / Keycloak 400 after node outage | PostgreSQL connection pool exhaustion | Terminate idle connections — see below |

### Fix 4: Operator SCC permissions

```bash
cat <<'EOF' | oc apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: f5-ai-security-operator-scc
rules:
- apiGroups: ["security.openshift.io"]
  resources: ["securitycontextconstraints"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: f5-ai-security-operator-scc
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: f5-ai-security-operator-scc
subjects:
- kind: ServiceAccount
  name: controller-manager
  namespace: f5-ai-sec
EOF
oc rollout restart deployment/controller-manager -n f5-ai-sec
```

### Fix 5: controller-manager OOMKilled

```bash
oc patch deployment controller-manager -n f5-ai-sec --type=json \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"512Mi"},
       {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"256Mi"}]'
```

### Fix 6: "Invalid License" after reinstall

```bash
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -d moderator -c "DELETE FROM setting;"
oc rollout restart deployment/cai-moderator -n cai-moderator
```

### Fix 7: Keycloak 400 / connection pool exhaustion

```bash
# Immediate fix
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND pid <> pg_backend_pid();"
oc rollout restart deployment/cai-moderator -n cai-moderator

# Permanent fix (raise max_connections)
oc exec -n cai-moderator cai-moderator-postgres-cai-postgresql-0 -- \
  psql -U postgres -c "ALTER SYSTEM SET max_connections = 200;"
oc rollout restart statefulset/cai-moderator-postgres-cai-postgresql -n cai-moderator
```
