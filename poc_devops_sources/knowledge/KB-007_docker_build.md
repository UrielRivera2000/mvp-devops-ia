---
doc_id: KB-007
title: Runbook PoC - Fallos de Docker build
type: runbook
technology: Docker / CI/CD
category: CI/CD / Build
synthetic: true
---
# no space left on device
Revisar espacio del runner, crecimiento de capas/cache y procedimiento autorizado de mantenimiento.

# COPY/build context
Confirmar ruta, build context, `.dockerignore` y existencia del artefacto previo al build.

# Guardrail
No limpiar disco ni eliminar imágenes desde el PoC.
