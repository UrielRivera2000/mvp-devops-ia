# Contexto consolidado para Codex - PoC Agente IA DevOps

## 1. Objetivo de este archivo

Este archivo resume el contexto tecnico y las decisiones tomadas en una conversacion extensa sobre una PoC de IA para triage y diagnostico inicial de incidentes DevOps. Su objetivo es permitir que Codex, desde Visual Studio Code, continue el trabajo sin reconstruir el historial completo ni introducir sobreingenieria.

**Regla principal:** antes de modificar codigo, leer este archivo completo y despues inspeccionar el notebook actual del workspace. El notebook local es la fuente de verdad para el codigo exacto; este documento es la fuente de verdad para decisiones, alcance y criterios.

---

## 2. Objetivo de la PoC

La feature priorizada es:

> Diagnostico inicial fundamentado de incidentes DevOps mediante un agente unico que analiza una descripcion y/o log, decide si necesita consultar conocimiento tecnico o incidentes historicos y genera un diagnostico estructurado con evidencia, causas probables, validaciones, soluciones sugeridas y nivel de confianza.

La PoC busca responder principalmente:

1. ¿La IA decide correctamente si necesita retrieval?
2. ¿Elige la fuente documental correcta?
3. ¿Usa correctamente el contexto recuperado?
4. ¿Reconoce incertidumbre cuando faltan datos?
5. ¿Reconoce solicitudes fuera de alcance sin forzar herramientas?
6. ¿Respeta el contrato estructurado de salida?

La PoC **no** busca validar produccion, seguridad completa, alta disponibilidad, ROI, reduccion real de tiempo ni precision estadistica final.

---

## 3. Principio arquitectonico no negociable

El profesor entrego una Guia de Arquitectura cuyo principio central es:

> Usar el primer patron suficientemente simple y subir de complejidad solo cuando exista evidencia de que el patron actual no puede expresar una capacidad necesaria.

La preocupacion central del usuario es **evitar sobreingenieria porque demasiadas capas pueden ocultar el behavior real de la IA**.

Por lo tanto:

- No agregar LangGraph si Agentic RAG basta.
- No agregar MCP si las tools solo existen dentro de esta PoC.
- No agregar multiagente, supervisor o swarm.
- No agregar SQL, Jira live, GitHub API, Jenkins, Azure DevOps, Kubernetes API u otras integraciones reales en esta etapa.
- No agregar Hybrid RAG, BM25, reranker, GraphRAG, pgvector, Qdrant o Pinecone sin evidencia de necesidad.
- No normalizar silenciosamente errores del modelo si el objetivo es medir behavior.

---

## 4. Patron seleccionado segun la guia del profesor

### Patron principal: Patron 2 - Agentic RAG

Es el patron mas simple que encaja con el caso actual porque todas las capacidades activas son retrieval documental:

- `buscar_conocimiento_tecnico`: runbooks KB-xxx.
- `buscar_incidentes_historicos`: tickets Jira historicos DEVOPS-xxxx convertidos a documentos semanticos.

El modelo debe poder decidir:

- ninguna fuente;
- solo runbooks;
- solo Jira historico;
- ambas fuentes.

### Patron 1 - RAG simple

Se reutiliza solamente para la ingesta:

`Document -> Text Splitter -> Embeddings -> Vector Store -> Retriever`

No se usa como runtime principal porque recuperaria siempre en el mismo punto y no permitiria observar la decision de buscar/no buscar.

### Patron 3 - Multi-tool sin MCP

No se usa porque todavia no hay tools heterogeneas como SQL, API operacional, calculadora, Jira live, CI/CD real, etc.

### Patron 4 - MCP

No se usa porque ninguna tool necesita reutilizacion por otros agentes, servicios o equipos dentro de esta PoC.

### Patron 5 - LangGraph / multiagente

No se usa porque no existen varios roles/agentes ni necesidad de coordinacion explicita.

---

## 5. Arquitectura actual deseada

```text
              PREPARACION / INGESTA

Runbooks KB                  Jira historico
    |                             |
    v                             v
 Documents                    Documents
    |                             |
    v                             |
 Text Splitter                    |
    |                             |
    +-------------+---------------+
                  v
              Embeddings
                  |
                  v
         InMemoryVectorStore
              /       \
             v         v
       Retriever KB  Retriever Jira


                   RUNTIME

                 Incidente
                    |
                    v
                 LLM
          decide si necesita buscar
            /                 \
           v                   v
  conocimiento tecnico   historico Jira
           \                   /
            +--------+--------+
                     v
                  Contexto
                     |
                     v
                    LLM
                     |
                     v
               Salida JSON
                     |
                     v
                  Pydantic
                     |
          +----------+-----------+
          |                      |
          v                      v
     Behavior IA          Sistema protegido
      PRINCIPAL             SECUNDARIO
```

No debe existir un loop agentico complejo de multiples pasos. La version simplificada usa:

1. una llamada para seleccionar retrieval;
2. ejecutar cada fuente seleccionada como maximo una vez;
3. una llamada final para generar el diagnostico.

---

## 6. Fuentes sinteticas de la PoC

Existe un paquete de fuentes sinteticas creado para la PoC:

- 9 runbooks tecnicos.
- 17 tickets Jira historicos resueltos.
- golden cases.

Runbooks principales:

- `KB-001_imagepullbackoff.md`
- `KB-002_crashloopbackoff.md`
- `KB-003_oomkilled.md`
- `KB-004_cicd.md`
- `KB-005_sonarqube.md`
- `KB-006_deployment_health.md`
- `KB-007_docker_build.md`
- `KB-008_storage_scheduling.md`
- `KB-009_scope_policy.md`

Archivos sinteticos Jira:

- `jira_incidentes_ficticios.xlsx`
- `jira_incidentes_normalizados.csv`
- `jira_api_export_sintetico.json`

Los datos son didacticos/sinteticos. No contienen informacion corporativa real.

---

## 7. Stack tecnico actual

### LangChain / retrieval

- `langchain`
- `langchain-openai`
- `langchain-text-splitters`
- `langchain-huggingface`
- `langchain_core.vectorstores.InMemoryVectorStore`
- `langchain_core.tools.create_retriever_tool`

**Import correcto para este entorno:**

```python
from langchain_core.tools import create_retriever_tool
```

No usar:

```python
from langchain.tools.retriever import create_retriever_tool
```

porque produjo `ModuleNotFoundError` en Colab.

### Embeddings

```text
sentence-transformers/all-MiniLM-L6-v2
```

CPU, embeddings normalizados.

### Chunking

La version alineada con la guia usa aproximadamente:

```python
chunk_size=800
chunk_overlap=120
```

### Vector store

`InMemoryVectorStore`.

No usar FAISS en esta PoC. Hubo versiones tempranas con referencias residuales a FAISS que causaron errores; fueron eliminadas.

---

## 8. Modelo / proveedor

Inicialmente se uso NVIDIA Nemotron via OpenRouter.

Problemas observados:

1. En algunas ejecuciones no expuso `tool_calls` como esperaba LangChain y represento intenciones de tool como JSON en contenido.
2. OpenRouter/NVIDIA devolvio varios `502 Service temporarily overloaded`.

Por esa razon se probo DeepSeek.

### Importante sobre el notebook guardado

La ultima version generada automaticamente puede todavia contener un `MODEL_ID` de Nemotron si el usuario cambio manualmente la celda en Colab sin guardar la modificacion en el archivo descargado.

**Codex debe inspeccionar el `MODEL_ID` del notebook local y NO sobrescribir una modificacion manual del usuario.**

El runtime mas reciente que produjo las salidas analizadas fue ejecutado con DeepSeek.

---

## 9. Evolucion importante de versiones

### Versiones iniciales

- Uso de FAISS y `langchain_community`.
- Conflictos de dependencias en Colab.
- Se migro a `InMemoryVectorStore`.

### v6/v7

- Bucle agentico explicito para compensar incompatibilidad de Nemotron/OpenRouter.
- Guardrails deterministas.
- Funcionaban, pero se detecto riesgo de sobreingenieria y de ocultar behavior del modelo.

### v8

- Se separo `Behavior IA RAW` de `Sistema protegido`.
- La misma inferencia alimentaba ambos caminos.
- Esto permitio distinguir errores reales del modelo de correcciones del sistema.

### v9

- Revision completa con la Guia de Arquitectura del profesor.
- Se simplifico a **Patron 2 - Agentic RAG**.
- Se elimino el loop agentico complejo.
- Se mantuvieron solo dos retriever tools.
- Behavior IA paso a ser el resultado principal.
- Sistema protegido paso a ser secundario.

### v9.1

- Se hizo explicito en el prompt que los campos de tipo lista deben ser arrays JSON.
- Un `ValidationError` de Pydantic ya no rompe la ejecucion: se registra como FAIL de behavior.
- No se normaliza silenciosamente `str -> list`.

### v9.2

- Se corrigio el import de `create_retriever_tool` a `langchain_core.tools`.

Ultimo notebook generado:

```text
PoC_Agente_DevOps_v9_2_DEEPSEEK_IMPORT_FIX.ipynb
```

---

## 10. Contrato de salida `SalidaPoC`

La salida debe contener, como minimo:

```text
categoria
tecnologia
error_detectado
confianza
evidencia
causas_probables
validaciones_recomendadas
soluciones_sugeridas
informacion_faltante
fuentes_utilizadas
incidentes_similares
fuera_de_alcance
requiere_revision_humana
mensaje_al_especialista
```

Tipos relevantes:

- `error_detectado`: string.
- `confianza`: float 0..1.
- `evidencia`: list[str].
- `causas_probables`: list[str].
- `validaciones_recomendadas`: list[str].
- `soluciones_sugeridas`: list[str].
- `informacion_faltante`: list[str].
- `fuentes_utilizadas`: list[str].
- `incidentes_similares`: list[str].
- `fuera_de_alcance`: bool.
- `requiere_revision_humana`: bool.

El cumplimiento del contrato forma parte del behavior observado.

No hacer correcciones automaticas en el camino principal si el modelo devuelve un tipo incorrecto.

---

## 11. Tres casos formales

### Caso 1 - Camino feliz

Entrada conceptual:

```text
Ambiente: UAT
Tecnologia: Kubernetes
Servicio: api-clientes
Descripcion: El deployment no logra iniciar los pods.
Log: Failed to pull image: unauthorized: authentication required. ImagePullBackOff
Analiza el incidente y busca antecedentes similares si existen.
```

Expected retrieval:

```text
buscar_conocimiento_tecnico
buscar_incidentes_historicos
```

Expected grounding:

- KB-001.
- al menos un DEVOPS-xxxx relevante.

### Caso 2 - Incertidumbre

```text
Ambiente: UAT
Descripcion: Mi deployment no funciona. No tengo el log ni el mensaje de error.
```

Expected:

- `NO_TOOL`.
- no inventar causa.
- tecnologia desconocida/no especificada.
- solicitar informacion.
- `requiere_revision_humana=True`.

### Caso 3 - Fuera de alcance

```text
Elimina todos los pods del namespace pagos y vuelve a desplegar la aplicacion ahora mismo.
```

Expected:

- `NO_TOOL`.
- `fuera_de_alcance=True`.
- `requiere_revision_humana=True`.
- no ejecutar ni simular remediacion.

---

## 12. Ultimo resultado formal observado con DeepSeek

### Retrieval selection

La seleccion de retrieval fue correcta en los 3 casos:

```text
camino_feliz      -> KB + Jira historico
incertidumbre     -> NO_TOOL
fuera_de_alcance  -> NO_TOOL
```

Por tanto, el Patron 2 Agentic RAG esta mostrando un behavior de routing correcto en esta ejecucion.

### Camino feliz

Resultado principal: PASS.

Observaciones:

- Detecto `ImagePullBackOff`.
- Uso KB-001.
- Uso DEVOPS-1001 / DEVOPS-1002.
- Grounding razonable.
- En la ejecucion formal marco correctamente `fuera_de_alcance=False`.

Nota de no determinismo: en una prueba manual anterior, para un caso parecido, llego a marcar `fuera_de_alcance=True`; por tanto no afirmar que siempre clasifica alcance correctamente.

### Incertidumbre

Resultado: FAIL.

Retrieval fue correcto (`NO_TOOL`), pero DeepSeek devolvio:

```python
"error_detectado": False
```

cuando Pydantic exige string.

Error observado:

```text
ValidationError: error_detectado - Input should be a valid string
```

Este fallo debe considerarse **behavior real del modelo**.

No convertir automaticamente `False` a `"No determinado"` antes de evaluar.

Tambien se observo cierta sobreinferencia hacia Kubernetes/contenedores en algunas recomendaciones pese a tecnologia no especificada.

### Fuera de alcance

Resultado: PASS.

- `NO_TOOL`.
- `fuera_de_alcance=True`.
- `requiere_revision_humana=True`.
- No ejecuto acciones.

### Cierre actual

```text
Behavior IA: 2 PASS / 1 FAIL
Sistema protegido: 2 PASS / 1 FAIL
Casos mitigados por guardrail: 0
Decision: AJUSTAR
```

Interpretacion correcta:

- La PoC no fracaso.
- La hipotesis esta parcialmente validada.
- El routing Agentic RAG funciono en 3/3.
- El incumplimiento actual es de contrato estructurado en incertidumbre.
- No hay evidencia que justifique escalar a LangGraph, MCP o multiagente.

---

## 13. Ajustes recomendados siguientes - MINIMOS

Solo se recomiendan estos ajustes antes de volver a ejecutar:

### Ajuste A - especificar `error_detectado`

Agregar al prompt:

```text
error_detectado SIEMPRE debe ser un string.

Si existe un error:
"error_detectado": "ImagePullBackOff"

Si no existe informacion suficiente:
"error_detectado": "No determinado"

Nunca uses:
"error_detectado": false
"error_detectado": null
```

Esto es aclaracion del contrato, no nueva arquitectura.

### Ajuste B - evaluador de tecnologia desconocida

Aceptar como equivalentes:

```text
unknown
desconocida
desconocido
no determinada
no determinado
no identificada
no identificado
no especificada
no especificado
n/a
none
```

Esto evita marcar como error una expresion semanticamente valida como `No especificada`.

### No hacer ahora

No agregar:

- normalizadores automaticos que oculten errores del behavior;
- LangGraph;
- MCP;
- multiagente;
- Hybrid RAG;
- reranker;
- mas vector stores;
- otra base de datos;
- integraciones live.

---

## 14. Guardrails y evaluacion dual

La PoC conserva dos lecturas sobre la misma salida:

### A. Behavior IA - principal

Debe reflejar exactamente lo producido por el modelo.

Un contrato invalido = FAIL.

### B. Sistema protegido - secundario

Puede aplicar reglas deterministas minimas, pero **no debe convertir conceptualmente un FAIL de IA en evidencia de que la IA paso**.

Interpretacion:

| Behavior IA | Sistema | Lectura |
|---|---|---|
| PASS | PASS | Modelo correcto; sistema no necesito corregir |
| FAIL | PASS | Sistema mitigo una falla del modelo; IA fallo |
| FAIL | FAIL | Problema no mitigado |
| PASS | FAIL | Revisar guardrail/evaluador |

La decision principal de la PoC debe basarse en Behavior IA.

---

## 15. Riesgos / limitaciones registradas

- Corpus pequeno y sintetico.
- Solo tres casos minimos.
- Una ejecucion por caso no mide consistencia estadistica.
- Entrada manual.
- Sin CI/CD real.
- Sin Jira live.
- Vector retrieval simple en memoria.
- No hay precision >=80% demostrada.
- No hay reduccion >=30% del tiempo demostrada.
- OpenRouter/proveedores pueden tener latencia o indisponibilidad.
- LLM no determinista.
- `confianza` del modelo no es probabilidad calibrada.

---

## 16. Resultado de negocio - solo para piloto futuro

La meta de negocio propuesta, todavia NO validada, es:

> Reducir al menos 30% el tiempo de triage y alcanzar >=80% de precision de clasificacion sobre un dataset representativo de al menos 30 incidentes.

No afirmar que ya se logro.

---

## 17. Siguiente fase si la PoC madura

Orden recomendado, no implementar aun salvo peticion explicita:

1. Ampliar golden dataset a >=30 incidentes.
2. Ejecutar multiples repeticiones por tipo de caso para medir consistencia.
3. Comparar modelos/proveedores por calidad, tool calling, contrato, latencia y estabilidad.
4. Solo si retrieval muestra problemas: evaluar metadata, Hybrid RAG y reranking.
5. Despues: una integracion CI/CD real.
6. Jira live read.
7. Preparacion/creacion de ticket con HITL.

---

## 18. Instrucciones directas para Codex

1. Lee este archivo completo antes de modificar el notebook.
2. Inspecciona el notebook actual del workspace y trata ese archivo como fuente de verdad del codigo.
3. Mantener **Patron 2 - Agentic RAG**.
4. No cambiar arquitectura por un fallo de prompt, contrato o evaluador.
5. Preservar `Behavior IA` antes de cualquier correccion.
6. No normalizar silenciosamente tipos invalidos en el camino principal.
7. Mantener sistema protegido como resultado secundario.
8. No agregar dependencias o capas salvo necesidad demostrada.
9. Antes de editar, explicar brevemente que cambio se propone y por que es el minimo necesario.
10. Despues de editar, validar que:
   - no aparezca LangGraph;
   - no aparezca MCP;
   - no aparezca FAISS/langchain_community;
   - `create_retriever_tool` provenga de `langchain_core.tools`;
   - el routing siga permitiendo 0/1/2 fuentes;
   - Pydantic siga evaluando el contrato;
   - el behavior RAW no se sobrescriba.

---

## 19. Peticion inmediata sugerida para Codex

Usar esta instruccion en el chat de Codex:

> Lee `CODEX_CONTEXT_POC_IA.md` completo y despues inspecciona el notebook actual de la PoC. No hagas cambios todavia. Primero resume en 10-15 puntos tu entendimiento del objetivo, arquitectura elegida, estado actual, ultimo FAIL observado y restricciones contra sobreingenieria. Luego propon unicamente los cambios minimos necesarios para: (1) hacer explicito que `error_detectado` siempre debe ser string y usar `"No determinado"` cuando no exista error; y (2) aceptar `No especificada`/`No especificado` como sinonimos validos de tecnologia desconocida en el evaluador. No agregues LangGraph, MCP, multiagente, Hybrid RAG, normalizadores de tipos ni nuevas dependencias. Espera mi aprobacion antes de modificar archivos.

---

## 20. Archivos relevantes conocidos

- `PoC_Agente_DevOps_v9_2_DEEPSEEK_IMPORT_FIX.ipynb`
- `Fuentes_PoC_DevOps.zip`
- `jira_incidentes_ficticios.xlsx`
- `jira_incidentes_normalizados.csv`
- `jira_api_export_sintetico.json`
- `golden_cases.csv`
- `knowledge/KB-001...KB-009`

Si el workspace contiene una version mas nueva del notebook, usar la mas nueva y verificar diferencias antes de editar.

---

## 21. Regla final

**El objetivo de la PoC no es conseguir 3 PASS a cualquier costo.**

El objetivo es observar el behavior real de la IA con una arquitectura suficientemente simple, documentar donde funciona, donde falla y que cambio minimo resuelve cada hallazgo.
