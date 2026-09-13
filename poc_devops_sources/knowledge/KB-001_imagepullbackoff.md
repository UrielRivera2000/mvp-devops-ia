---
doc_id: KB-001
title: Runbook PoC - ImagePullBackOff y ErrImagePull
type: runbook
technology: Kubernetes
category: Containers / Registry
synthetic: true
---
# Objetivo
Guiar el diagnóstico inicial de `ImagePullBackOff` o `ErrImagePull` sin ejecutar remediación automática.

# Síntomas
`Failed to pull image`, `unauthorized: authentication required`, tag inexistente, `FailedToRetrieveImagePullSecret`.

# Causas probables
1. Credenciales inválidas o expiradas del registry.
2. `imagePullSecret` inexistente, mal nombrado o no asociado al ServiceAccount.
3. Imagen o tag inexistente.
4. Permisos insuficientes sobre el repositorio.
5. Endpoint del registry incorrecto.

# Validaciones
Confirmar imagen/tag; revisar eventos del pod; verificar existencia/referencia del imagePullSecret; confirmar permisos de lectura del repositorio; recopilar namespace, workload, imagen completa y texto exacto del error.

# Guardrail
No rotar credenciales, editar secrets, borrar pods ni relanzar deployments desde el PoC.
