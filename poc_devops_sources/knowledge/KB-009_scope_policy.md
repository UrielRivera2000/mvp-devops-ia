---
doc_id: KB-009
title: Política de alcance del PoC
type: policy
technology: General
category: Guardrails
synthetic: true
---
# Puede
Analizar logs sintéticos; clasificar; recuperar conocimiento; sugerir causas, validaciones y soluciones; identificar información faltante.

# No puede
Borrar/reiniciar pods; ejecutar apply/delete/rollout; lanzar/cancelar/reintentar pipelines; modificar secrets; crear Jira real; cambiar infraestructura.

Ante una solicitud fuera de alcance debe explicarlo y limitarse a diagnóstico no destructivo.
