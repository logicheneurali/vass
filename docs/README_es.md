# VASS — Software de asistente de voz

## Qué es VASS

VASS es un asistente de voz para Windows, macOS y Linux. Responde a comandos de voz, ejecuta scripts, gestiona eventos y recordatorios, lee y responde correos electrónicos e interactúa con una IA local o remota a través de una API compatible con OpenAI. También aloja un servidor MCP que le da a la IA acceso directo a archivos, navegador, calendario, correo, noticias y herramientas del sistema.

**Palabra de activación predeterminada:** «Erika» (configurable)

**Versión actual:** 0.8.7

**Características principales:**
- Reconocimiento de voz mediante Whisper (faster-whisper) con Silero VAD y suelo de ruido adaptativo
- Síntesis de voz natural mediante Kokoro TTS con una cadena de respaldo de varios pasos
- IA local o remota (llama.cpp, OpenAI, cualquier servidor compatible) con arranque automático opcional de llama.cpp
- Scripting VASScript para automatización de escritorio con más de 70 funciones integradas
- Gestión de eventos y horarios con editor gráfico (recordatorios, procedimientos automatizados)
- Temporizador de cuenta atrás multilingüe (activado por voz, 5 simultáneos)
- Servidor MCP con más de 50 herramientas para la orquestación de la IA (navegador, correo, noticias, calendario, lugares, archivos, sistema)
- Memoria permanente con clasificación automática, resumen e inyección del perfil de usuario
- Cliente de correo integrado: Gmail, IMAP, POP3 con cola, contactos y correos enviados por IA
- Sistema de plugins: plugins internos y externos a través de un socket TCP local
- Centro de notificaciones con enrutamiento por tipo de evento
- Visor del historial de conversaciones con acciones por mensaje
- Soporte de 9 idiomas
- Protección contra desbordamiento del contexto (truncado o resumen por IA)
- Selección de dispositivo de audio (entrada/salida)
- Llamada a herramientas en múltiples turnos para tareas complejas de IA
- Sistema meteorológico con 3 fuentes y base de datos de geolocalización de 200K ciudades
- Comandos de voz con desplazamiento temporal («apagar en 5 minutos»)
- Indicador de actividad de herramientas MCP en tiempo real en la GUI
- Compresión heurística del contexto con soporte de palabras vacías multilingüe
- Conteo de contexto preciso en tokens (tiktoken)
- Entorno aislado de ejecución de scripts con autorización SHA-256 y registro de auditoría
- Puerta de seguridad para herramientas en línea sensibles (consentimiento, límite de frecuencia, registro de auditoría)
- Arranque automático del sistema opcional

---

## Requisitos

- **Python 3.13** o superior
- **Servidor de IA** (llama.cpp o compatible con OpenAI) ya instalado y configurado en el sistema. VASS puede iniciar llama.cpp automáticamente si está configurado, pero **NO instala llama.cpp ni descarga modelos de IA**: debe obtenerlos por separado.
- **Conexión a Internet** (para descargas de modelos TTS/STT y para la IA remota)
- **GPU NVIDIA recomendada** para IA local (la CPU es posible pero lenta)
- **Micrófono en funcionamiento**
- Windows 10+, macOS 12+ o Linux moderno

---

## Instalación

### Instalación gráfica (recomendada)

Descargue el instalador de la [página de versiones](https://github.com/logicheneurali/vass/releases) y ejecútelo. El asistente instalará Python, VASS, llama.cpp y un modelo de IA automáticamente, sin necesidad de configuración manual.

### Instalación guiada

Descargue o clone el proyecto, entre en la carpeta y ejecute el script:

```bash
cd vass
python install.py
```

> **Nota:** la instalación guiada configura VASS pero **NO instala el servidor de IA ni los modelos**.
> Debe tener ya en ejecución un servidor compatible con OpenAI (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> o configurar llama.cpp en los ajustes de VASS (que puede iniciarlo automáticamente).

**Nota:** el procedimiento de instalación guiada sigue siendo experimental y puede no funcionar en todos los sistemas. Si encuentra problemas, utilice el procedimiento de instalación manual que se indica a continuación.

El asistente le guiará a través de:
1. Selección de idioma
2. Comprobación de requisitos (Python 3.13+, pip)
3. Carpeta de destino
4. Configuración de parámetros (URL de la IA, modelo, palabra de activación)
5. Copia de archivos
6. Creación del entorno virtual de Python (.venv)
7. Instalación de dependencias de pip
8. Creación del archivo settings.ini
9. Creación del lanzador

### Instalación manual

```bash
# Clone o copie los archivos a la carpeta deseada
cd VASS

# Cree el entorno virtual
python -m venv .venv

# Actívelo (Windows)
.venv\Scripts\activate
# o (macOS/Linux)
source .venv/bin/activate

# Instale las dependencias
pip install -r requirements.txt

# Instale Chromium para Playwright (búsquedas web)
playwright install chromium

# Cree config/settings.ini (cópielo de config/settings.example.ini)
```

---

## Configuración

Todos los ajustes se encuentran en `config/settings.ini` (la plantilla es `config/settings.example.ini`). Estos son los más importantes:

| Sección | Parámetro | Descripción |
|---------|-----------|-------------|
| `[locale]` | `language` | Idioma (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Palabra de activación (por defecto: erika) |
| `[wakeword]` | `sensitivity` | Sensibilidad de detección de la palabra de activación |
| `[commands]` | `similarity` | Umbral de coincidencia aproximada de comandos de voz (por defecto 0.6) |
| `[commands]` | `word_learning_enabled` | Aprender nuevas palabras habladas con el tiempo (true/false) |
| `[ai]` | `url` | URL del servidor de IA compatible con OpenAI |
| `[ai]` | `model` | Nombre del modelo de IA |
| `[ai]` | `system_message` | Personalidad del asistente |
| `[ai]` | `api_key` | Clave de API (se almacena en el llavero del sistema si se define) |
| `[ai]` | `mcp_server_url` | URL del servidor MCP incluido (por defecto `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Tamaño máximo de la memoria |
| `[ai]` | `context_length` | Máximo de tokens de contexto (0 = automático) |
| `[ai]` | `overflow_strategy` | Gestión del desbordamiento de contexto: `truncate` o `summarize` |
| `[ai]` | `allow_ai_scripts` | Permitir que la IA ejecute scripts VASScript (true/false) |
| `[llamacpp]` | `llama_server_path` | Ubicación del servidor llama.cpp |
| `[llamacpp]` | `llama_autostart` | Iniciar llama.cpp automáticamente con VASS (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Límites de recursos que condicionan las operaciones de la IA |
| `[events]` | `reminder_advance` | Segundos antes de un evento en que se emite el recordatorio (por defecto 3600) |
| `[audio]` | `input_device`, `output_device` | Selección de dispositivo de audio (-1 = predeterminado del sistema) |
| `[audio]` | `input_volume`, `output_volume` | Niveles de volumen de entrada/salida (0-1) |
| `[audio]` | `app_volume` | Volumen maestro del TTS (sustituye al obsoleto `[tts] volume`) |
| `[google]` | — | Integración con Google Calendar / Gmail / Google Home |
| `[startup]` | `app_autostart` | Iniciar VASS automáticamente al iniciar sesión (true/false) |
| `[debug]` | `debug_enabled` | Escribir un registro detallado en `log/debug.log` (true/false) |

Los ajustes se recargan automáticamente si se modifican mientras VASS está en ejecución.

---

## Uso diario

### Inicio

Haga doble clic en `vass.bat` (Windows) o en `vass.sh`/`vass.command` (macOS/Linux).

O desde la terminal:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Nota:** en el primer arranque, los modelos de reconocimiento de voz (Whisper) y de síntesis de voz (Kokoro) se descargan automáticamente de HuggingFace. El primer inicio puede tardar varios minutos (descarga de ~2-4 GB). Esto solo ocurre una vez.

### Palabra de activación

La palabra de activación es **configurable** por el usuario en el archivo `config/settings.ini` y puede ser cualquier palabra o frase corta. El valor predeterminado es «**Erika**».

Cuando VASS detecta la palabra de activación, emite un pitido para indicar que está listo para recibir el comando. Hable después del pitido.

Ejemplos:
- *«Erika»* (espere el pitido) y luego *«¿qué tiempo hace?»*
- *«Erika»* (espere el pitido) y luego *«lee las últimas noticias»*
- *«Erika»* (espere el pitido) y luego *«¿qué es la inteligencia artificial?»*
- *«Erika»* (espere el pitido) y luego *«traduce al italiano buenos días a todos»*
- *«Erika»* (espere el pitido) y luego *«receta de pasta carbonara»*

### Modos: Chat y Transcripción

VASS puede funcionar en dos modos, seleccionables desde el menú emergente (botón ≡ a la derecha del botón principal):

- **Chat** `[C]` — La aplicación reconoce comandos de voz y realiza acciones (scripts, comandos del sistema) o interactúa con la IA. La respuesta se lee mediante TTS.
- **Transcripción** `[T]` — En lugar de interpretar comandos, VASS transcribe fielmente lo que el usuario dice después de la palabra de activación (siempre después del pitido). El texto se pega a continuación en la aplicación activa, convirtiendo a VASS en un sistema de dictado de texto.

El modo actual se muestra en el botón principal: `[C]` para Chat, `[T]` para Transcripción. El último modo utilizado se restaura al reiniciar.

### Modo de memoria

Desde el menú de la GUI o haciendo clic en el botón principal:
- **Completo** — La IA recibe el resumen de la memoria y su perfil de usuario
- **Limitado** — La IA recibe solo el historial reciente
- **Ninguno** — Sin contexto histórico

### Comandos de voz

Los comandos se configuran en `config/commands.ini` (formato INI estándar, `frase = acción`), también editables a través del editor gráfico (`python src/commands_editor.py`). Los archivos específicos por idioma `config/commands_{lang}.ini` se cargan además del archivo base. Cada línea es un par **frase = acción**: la frase es el patrón a reconocer (puede incluir `{variables}`), la acción es lo que se ejecuta.

```ini
[general]
search {term} = script:search
open {program} = start {program}
search online {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
what time is it = script:datetime

[system]
shutdown system = shutdown /s /t 60
lock screen = rundll32.exe user32.dll,LockWorkStation
```

#### Cómo funciona la coincidencia

1. **Reconocimiento difuso**: no se requiere una coincidencia exacta. VASS compara la frase hablada con todos los patrones mediante un algoritmo de similitud (`difflib`). El patrón con la puntuación más alta por encima del umbral (por defecto `0.6`, configurable en `config/settings.ini` en `[commands] similarity`) se activa.

2. **Variables `{name}`**: capturan las palabras habladas en esa posición. Ejemplo: decir *«busca gatos en internet»* captura `term = "gatos en internet"`.

3. **Variables escapadas `{escaped_name}`**: igual que las variables normales, pero el texto capturado se codifica en URL (los espacios se convierten en `%20`). Útil para búsquedas web.

4. **Comandos con desplazamiento temporal**: un sufijo `{duration}` (p. ej. *«apagar en 5 minutos»*) programa el comando para que se ejecute transcurrido el tiempo indicado mediante el sistema de temporizadores.

5. **Aprendizaje de palabras**: si está activado, VASS registra cómo pronuncia las palabras para mejorar el reconocimiento con el tiempo.

6. **Respaldo de la IA**: si ningún comando supera el umbral de similitud, la frase se envía a la IA para obtener una respuesta en lenguaje natural.

#### Alternativas con comas (producto cartesiano)

Puede especificar varias alternativas para cada posición de palabra usando comas. Los **espacios** separan posiciones de palabras; las **comas** separan alternativas dentro de una posición. VASS genera todas las combinaciones posibles (producto cartesiano).

```ini
# Posición única: alternativas para la preposición
click the,on text {text}
```
Genera 2 patrones: `click the text {text}`, `click on text {text}`.

```ini
# Dos posiciones: cada posición tiene sus propias alternativas
aa,xx bb,cc {var}
```
Genera 4 patrones: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Mixto: palabra fija + alternativas
turn on,off {device}
```
Genera 2 patrones: `turn on {device}`, `turn off {device}` (sin espacio entre `on` y `off` -> misma posición).

La frase hablada se compara con todos los patrones generados. Gana la mejor coincidencia difusa.

#### Tipos de acción

| Prefijo | Ejemplo | Comportamiento |
|--------|---------|----------|
| `script:` | `script:search` | Ejecuta `scripts/search.vass`. Las variables capturadas se convierten en `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:events` | Igual que `script:` (prefijo alternativo) |
| Comando | `shutdown /s` | Se ejecuta directamente como comando del sistema |

#### Nombres de secciones

Los nombres de sección como `[general]` y `[system]` son solo categorías organizativas; no afectan a la coincidencia. Lo que importa es la **clave** (la frase a reconocer).

### Crear scripts VASScript

Abra el editor de scripts desde el menú de la GUI o ejecute:
```bash
python src/scripts_editor.py
```

Todos los scripts van en la carpeta `scripts/` con extensión `.vass`.

**Autorización**: antes de ejecutar un script nuevo o modificado, VASS muestra una ventana emergente pidiendo permiso. Los scripts se verifican mediante hash SHA-256 (almacenado en el llavero del sistema): si un archivo de script se modifica después de haber sido autorizado, los permisos se revocan automáticamente y la ventana emergente volverá a aparecer en la siguiente ejecución. El permiso puede concederse por función o para todo el script. Esto garantiza que ningún script pueda ejecutarse en su equipo sin su consentimiento explícito.

Consulte el archivo [Referencia de VASCRIPT](../Allowed_root/VASCRIPT_REFERENCE.md) para conocer la referencia completa del lenguaje.

### Eventos y recordatorios

Los eventos se gestionan a través del archivo `Allowed_root/events.json`. Se emite un recordatorio por voz con 1 hora de antelación (configurable mediante `[events] reminder_advance`).

Los horarios (procedimientos automatizados) están en `Allowed_root/schedules.json` y activan la ejecución de comandos con notificación por TTS. Marcadores adicionales: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Sistema de plugins

VASS expone un servidor TCP local (`localhost:8765`) que los plugins usan para comunicarse con la aplicación: TTS, notificaciones, consultas de IA, elementos RSS, chat, UIs declarativas y más. Los **plugins internos** (incluidos con VASS) no se pueden eliminar; los **plugins externos** pueden activarse, desactivarse y eliminarse desde la GUI (menú Plugins).

Plugins internos incluidos: pausa automática por ruido, agente proactivo, perfil de usuario, lector RSS, eventos mundiales, bot de Telegram. Plugins externos disponibles en disco: generador de imágenes, publicador de noticias, visor de cronologías.

Consulte la guía [PLUGIN_DEV_es.md](PLUGIN_DEV_es.md) para conocer el protocolo completo y cómo crear sus propios plugins (también disponible en `PLUGIN_DEV_{en,it,de,fr,pt,ja,ko,zh}.md`).

### Correo electrónico

Configure una o varias cuentas en Ajustes → Correo (Gmail mediante OAuth, o IMAP/POP3 con SSL/TLS simple). Los mensajes entrantes se detectan y se notifican; la IA puede buscar, leer, responder, reenviar y enviar correos, pero los correos enviados siempre se colocan en una **cola** que usted debe aprobar y enviar desde la bandeja de salida. Los contactos se almacenan cifrados.

---

## Interfaz gráfica (GUI)

- **Botón principal** — Haga clic para cambiar de estado (escuchando/en pausa). Rueda del ratón para el volumen. Arrastre para mover la ventana.
- **Barra de volumen** (verde, en la parte superior) — Muestra el volumen actual del TTS
- **Barra multiestado** — Muestra el uso de memoria, el volumen o el progreso de scripts/actividad según el contexto
- **Centro de notificaciones** (campana) — Pestañas por tipo con acciones de mensaje y marcar todo como leído
- **Indicador de herramientas** — Icono en tiempo real que muestra la herramienta MCP que usa la IA
- **Botón de micrófono** — Entrada de voz directa en el modo chat
- **Menú de plugins** — Gestione plugins, ajustes de plugins y UIs de plugins
- **Cuadro de diálogo de ajustes** — Configuración completa desde la GUI (menú Ajustes)
- **Atenuación automática** — La ventana se vuelve semitransparente cuando está inactiva y en pantalla completa
- **Pantalla de bienvenida** — Progreso de carga al iniciar
- **Tema** — Tema compartido entre la aplicación y todos los editores

### Atajos

| Tecla | Acción |
|-------|--------|
| `Ctrl+S` | Guardar (en los editores) |
| Clic en el botón | Cambiar estado |
| Rueda sobre el botón | Ajustar el volumen |
| Clic derecho | Menú contextual |
| Clic central en el botón | Salir |

---

## Solución de problemas

> **Importante:** esta aplicación depende en gran medida del modelo de IA utilizado. Los modelos ineficaces o no adecuados para el uso de herramientas MCP pueden comprometer la funcionalidad.

### VASS no arranca
- Compruebe Python 3.13+: `python --version`
- Verifique que `.venv` existe y contiene las dependencias
- Consulte `log/debug.log` (active `[debug] debug_enabled = true`) y `log/crash.log`

### El micrófono no funciona
- Verifique que el micrófono está conectado y no lo está usando otra aplicación
- Compruebe los permisos del sistema para el micrófono
- En Windows: Ajustes → Privacidad → Micrófono

### La IA no responde
- Verifique que el servidor de IA está en ejecución en `http://127.0.0.1:8080/v1`
- Compruebe `[ai] url` en `config/settings.ini`
- Si usa llama.cpp, verifique que el modelo existe y que `[llamacpp] llama_server_path` es correcto
- Consulte `log/llamacpp.log` para ver los errores de llama.cpp

### OCR no reconoce el texto de la pantalla
- Aumente el tamaño de fuente o el contraste del texto en pantalla
- EasyOCR funciona mejor con fuentes grandes y alto contraste
- El idioma del OCR se adapta automáticamente a la configuración regional

### La IA no puede usar una herramienta
- Algunas herramientas en línea requieren su consentimiento (puerta de seguridad) — compruebe el panel de información para ver las solicitudes pendientes
- Verifique que el servidor MCP es accesible en `http://localhost:9988` (consulte `[ai] mcp_server_url`)
- Consulte `log/mcp_server.log` para ver los errores de MCP

---

## Archivos importantes

| Archivo | Descripción |
|------|-------------|
| `config/settings.ini` | Configuración principal |
| `config/commands.ini` | Comandos de voz base (más `commands_{lang}.ini`) |
| `config/notifications.ini` | Enrutamiento de notificaciones por tipo de evento |
| `scripts/*.vass` | Sus scripts VASScript |
| `Allowed_root/events.json` | Sus eventos y recordatorios |
| `Allowed_root/schedules.json` | Procedimientos automatizados |
| `Allowed_root/memory.json` | Historial de conversaciones y memoria |
| `Allowed_root/private_profile.json` | Perfil de usuario inyectado en el contexto de la IA |
| `plugins/` | Plugins internos y externos |
| `log/debug.log` | Registro de depuración detallado (cuando está activado) |
| `log/crash.log` | Registro de bloqueos |
| `log/faulthandler.log` | Salida del controlador de fallos |
| `log/llamacpp.log` | Registro del servidor llama.cpp |
