---
doc_id: KB-004
title: Runbook PoC - Fallos comunes de CI/CD
type: runbook
technology: CI/CD
category: CI/CD
synthetic: true
---
# Tests
Ante `There are test failures`: capturar primer test y stacktrace, reproducir, corregir causa; no ocultar el fallo.

# Dependencias
Ante `Could not resolve dependencies`: identificar artefacto, confirmar existencia y revisar repositorio configurado.

# Checkout
Ante `Authentication failed`/401: confirmar repo; tratar tokens como secretos; actualización solo por proceso autorizado.

# Guardrail
No cambiar secrets ni relanzar pipelines.
