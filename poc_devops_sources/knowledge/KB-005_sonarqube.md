---
doc_id: KB-005
title: Runbook PoC - SonarQube Quality Gate y cobertura
type: runbook
technology: SonarQube / CI/CD
category: CI/CD / Quality
synthetic: true
---
# Quality Gate
Identificar condición exacta; distinguir cobertura de bugs/vulnerabilidades; no deshabilitar el gate como solución.

# Cobertura 0
Confirmar que tests generan lcov/jacoco; verificar rutas configuradas; comprobar que el scanner importó el reporte.

# Resultado
Distinguir cobertura realmente baja de un problema de importación del reporte.
