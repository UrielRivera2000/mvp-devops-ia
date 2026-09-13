---
doc_id: KB-008
title: Runbook PoC - Pods y PVC Pending
type: runbook
technology: Kubernetes
category: Storage / Scheduling
synthetic: true
---
# PVC Pending
Revisar eventos, StorageClass, tamaño, accessMode y provisión.

# Pod Pending
Revisar scheduler; distinguir recursos insuficientes de taints, affinity o PVC no vinculado; comparar requests con capacidad.

# Guardrail
No modificar nodos, StorageClasses ni requests automáticamente.
