---
doc_id: KB-002
title: Runbook PoC - CrashLoopBackOff
type: runbook
technology: Kubernetes
category: Runtime / Configuration
synthetic: true
---
# Causas frecuentes
Variable/configuración faltante; Secret o ConfigMap incorrecto; dependencia externa no disponible; entrypoint falla; probe mal configurada.

# Validaciones
Revisar logs actuales y anteriores; identificar exit code; comparar ConfigMaps/Secrets esperados; verificar endpoints y parámetros de arranque; revisar probes si la aplicación sí inicia.

# Guardrail
No reiniciar pods ni modificar ConfigMaps/Secrets.
