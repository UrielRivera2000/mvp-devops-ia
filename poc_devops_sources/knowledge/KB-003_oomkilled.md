---
doc_id: KB-003
title: Runbook PoC - OOMKilled
type: runbook
technology: Kubernetes
category: Resources / Capacity
synthetic: true
---
# Indicadores
`Reason: OOMKilled`, `Exit Code: 137`, reinicios bajo carga.

# Causas
Límite insuficiente; fuga o crecimiento no acotado; heap sin margen de memoria nativa; carga excepcional.

# Validaciones
Confirmar reason/exit code; comparar requests/limits con consumo; correlacionar reinicios con carga; en Java, revisar heap frente al límite total.

# Guardrail
No modificar recursos automáticamente.
