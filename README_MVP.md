# DevOps Triage MVP

Primer vertical slice del MVP para triage y diagnóstico inicial de incidentes DevOps.

## Qué incluye

- Servicio Python sin dependencias externas nuevas.
- Frontend web estático, responsive y orientado a revisión humana.
- Endpoint `POST /api/analyze`.
- Endpoint `POST /api/feedback` con persistencia local en `runtime/feedback.jsonl`.
- Endpoint `GET /api/health`.
- Dos retrievers separados sobre las fuentes autorizadas:
  - runbooks técnicos;
  - histórico Jira sintético.
- Routing seguro: cero o una consulta por fuente.
- Contrato de diagnóstico con `error_detectado` siempre como string.
- Sanitización de secretos, bloqueo de solicitudes de prompt injection y ausencia de ejecución de comandos.
- Evidencia, fuentes, traza y revisión humana obligatoria.

## Ejecución

Desde esta carpeta:

```powershell
python app.py
```

Abrir `http://127.0.0.1:8000`.

El directorio de fuentes puede cambiarse sin editar código:

```powershell
$env:MVP_SOURCES_DIR = 'C:\ruta\a\poc_devops_sources'
python app.py
```

El repositorio incluye una copia del corpus sintético en `poc_devops_sources/`. Si no existe la carpeta hermana usada en el entorno local, la aplicación utiliza automáticamente ese corpus incluido.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Evaluación del golden dataset

```powershell
python evaluation.py --repetitions 3
```

El reporte conserva routing, veredicto RAW, veredicto protegido y un aviso si el dataset tiene menos de 30 casos. Actualmente las fuentes contienen únicamente 3 casos.

## Conector GitHub Actions

El endpoint de lectura es `POST /api/analyze/github-actions` y requiere `owner`, `repository` y `run_id`. El token nunca viaja desde el navegador:

```powershell
$env:GITHUB_READ_TOKEN = 'token-de-solo-lectura'
python app.py
```

El adaptador solo consulta metadata de workflow, jobs y logs; rechaza repositorios inválidos, limita el tamaño de respuestas y redacta secretos en logs. La prueba real requiere un repositorio y token autorizados.

### Workflow demo para probar el conector

El archivo `.github/workflows/triage-demo-failure.yml` crea, bajo ejecución manual, un fallo sintético `ImagePullBackOff`. No cambia infraestructura ni usa secretos. Para probarlo:

1. Publica el repositorio con la carpeta `.github/workflows`.
2. En GitHub abre `Actions` → `DevOps Triage - Incidente demo` → `Run workflow`.
3. Copia el Run ID de la ejecución fallida.
4. En la aplicación selecciona `GitHub Actions` e introduce el owner, `mvp-devops-ia` y ese Run ID.
5. Mantén `GITHUB_READ_TOKEN` únicamente en la sesión del servidor o como secreto del entorno; nunca lo agregues al repositorio.

El workflow `.github/workflows/ci.yml` ejecuta las pruebas Python y valida el JavaScript en cada push, pull request o ejecución manual. No instala dependencias del proyecto.

## Proveedor LLM opt-in

El adaptador de OpenRouter está implementado en `provider.py`, pero permanece apagado por defecto. Para activarlo deben existir una clave fuera del código y una decisión explícita del entorno:

```powershell
$env:MVP_LLM_PROVIDER = 'openrouter'
$env:OPENROUTER_API_KEY = '...'
$env:MVP_LLM_MODEL = 'openai/gpt-5'
python app.py
```

El agente realiza una llamada de routing y otra de diagnóstico. Python conserva la allowlist de tools, ejecuta como máximo una recuperación por fuente, valida el JSON estrictamente y devuelve `503` si el proveedor falla. No hay fallback silencioso del proveedor a otro modelo.

Para la validación real del Paso 4, configura las variables en tu máquina y ejecuta el MVP desde esa misma sesión. No pegues valores de tokens en el chat:

```powershell
$env:MVP_LLM_PROVIDER = 'openrouter'
$env:OPENROUTER_API_KEY = 'tu-clave-local'
$env:MVP_LLM_MODEL = 'modelo-aprobado'
$env:GITHUB_READ_TOKEN = 'token-de-solo-lectura'
python app.py
```

La prueba real del proveedor y del conector no se ejecutó en este entorno porque ninguna de esas variables está configurada.

Pydantic está declarado en `requirements.txt`, pero no pudo descargarse en el entorno actual. Mientras tanto, `contracts.py` aplica validación estricta con la librería estándar y rechaza tipos inválidos sin convertirlos.

## Seguridad del primer slice

El modo actual es `local_demo`: no llama a un proveedor LLM, no lee variables de entorno como secretos, no tiene shell, no ejecuta herramientas externas y escucha solo en `127.0.0.1` por defecto.

La entrada y las fuentes se tratan como datos no confiables. Los patrones conocidos de secretos se redactan y las solicitudes para revelar prompts, credenciales o ejecutar acciones mutantes se bloquean. Esto es defensa en profundidad, no una garantía absoluta: antes de exponerlo fuera de localhost deben añadirse autenticación, autorización, gestión de secretos, límites operativos y pruebas de seguridad adicionales.

## Próximo paso pendiente de aprobación

Agregar el adaptador de proveedor/modelo y structured output real únicamente después de definir proveedor, privacidad, credenciales y plataforma CI/CD disponibles. La PoC original permanece sin modificar.
