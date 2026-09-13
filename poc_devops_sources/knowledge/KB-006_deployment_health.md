---
doc_id: KB-006
title: Runbook PoC - Deployment ProgressDeadlineExceeded y Helm
type: runbook
technology: Kubernetes / Helm
category: Deployment / Health
synthetic: true
---
# ProgressDeadlineExceeded
Causas: readiness incorrecta, contenedor no Ready, configuración nueva, recursos insuficientes.
Validar conditions, pods del ReplicaSet, readiness/startup probes, puertos y eventos.

# Helm
Ante error de render: identificar template/valor faltante, validar values del ambiente y render no destructivo.

# Guardrail
No rollout, rollback ni upgrade desde el PoC.
