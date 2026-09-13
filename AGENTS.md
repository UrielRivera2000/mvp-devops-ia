# AGENTS.md - PoC IA DevOps

## Contexto obligatorio

Antes de editar, lee `CODEX_CONTEXT_POC_IA.md` completo y luego inspecciona el notebook actual del workspace.

## Objetivo

Mantener una PoC simple de **Patron 2 - Agentic RAG** para observar el behavior real de la IA al decidir si usar retrieval tecnico, historico, ambos o ninguno.

## Restricciones

- No agregar LangGraph.
- No agregar MCP.
- No agregar multiagente/supervisor/swarm.
- No agregar Hybrid RAG, BM25, reranker, GraphRAG, pgvector, Qdrant o Pinecone sin evidencia concreta.
- No agregar SQL/API/Jira live/CI-CD real en esta etapa.
- No normalizar silenciosamente tipos invalidos del modelo en el camino `Behavior IA`.
- El sistema protegido es secundario; no debe ocultar un FAIL del modelo.
- El veredicto principal de la PoC se basa en `Behavior IA`.

## Arquitectura actual

`Input -> LLM selecciona retrieval -> Retriever KB/Jira -> LLM final -> Pydantic -> Behavior IA + Sistema protegido`

Cada fuente se recupera como maximo una vez por caso.

## Tool imports

Usar:

```python
from langchain_core.tools import create_retriever_tool
```

No usar `langchain.tools.retriever` ni `langchain_community`.

## Estado actual

- Routing Agentic RAG observado: 3/3 correcto en la ultima ejecucion formal.
- Behavior completo: 2 PASS / 1 FAIL.
- FAIL actual: caso de incertidumbre devolvio `error_detectado=False` cuando Pydantic exige string.
- No escalar arquitectura por este fallo.

## Proximos cambios permitidos

Solo ajustes minimos salvo autorizacion expresa:

1. Prompt: `error_detectado` siempre string; usar `"No determinado"` cuando no haya error.
2. Evaluador: aceptar `No especificada` y `No especificado` como sinonimos de tecnologia desconocida.

Antes de modificar, explica el cambio minimo propuesto. Despues, valida que no aumentaste la complejidad arquitectonica.
