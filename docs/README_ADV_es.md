# VASS — Documentación Avanzada

## Arquitectura general

VASS es una aplicación modular compuesta por varios componentes independientes que se comunican mediante colas de archivos, señales Qt y llamadas directas.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Orquestador principal               │
│  - Inicialización de componentes                 │
│  - Bucle de escucha/escritura                   │
│  - Gestión de fallback IA                       │
│  - Ejecución de scripts                         │
│  - Watchdog de colas de archivos                │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Eve ││mcp_server│
  │  PySide││Ing. ││Whisp││Rec ││ 15 herr. │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Componentes principales

| Componente | Archivo | Responsabilidad |
|-----------|------|---------------|
| Orquestador | `vass.py` (1313 líneas) | Inicialización, bucle principal, IA, scripts, memoria |
| GUI | `gui.py` (832 líneas) | Ventana PySide6, barras, difuminado, subventanas |
| TTS | `tts_engine.py` (138 líneas) | Kokoro TTS, reproducción de audio, volumen |
| STT | `voice_recognition.py` (133 líneas) | faster-whisper, detección de palabra de activación |
| Intérprete | `script_engine.py` (761 líneas) | Analizador VASScript, evaluador, 26 funciones |
| Eventos | `event_reminder.py` (280 líneas) | Monitor de eventos/programaciones, alertas TTS |
| Comandos | `command_executor.py` (184 líneas) | Coincidencia difusa de patrones, extracción de variables |
| Servidor MCP | `mcp_server/` | Servidor FastMCP, 15 herramientas, ACL basada en IP |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR con preprocesamiento |
| Inactividad | `idle_tracker.py` (67 líneas) | Detección de inactividad multiplataforma |
| Recursos | `resource_monitor.py` (52 líneas) | Control CPU/RAM/GPU/VRAM antes de solicitudes IA |
| Registro | `log_utils.py` (13 líneas) | Rotación de archivos de registro |

---

## Pipeline de audio

```
Micrófono ──► sounddevice (callback) ──► cola de audio ──► Whisper (transcripción)
                                                               │
                    ┌──────────────────────────────────────────┤
                    ▼                                          ▼
         ¿Detección "Erika"?                        Transcripción completa
                    │                                          │
                    ▼                                          ▼
               Pitido (listo para comando)              ¿Coincide commands.ini?
                    │                                  │            │
                    ▼                                  ▼            ▼
             Espera de comando                    Comando    Sin coincid.
                    │                            encontrado
                    ▼                                  │            │
             Transcripción                              ▼            ▼
                    │                          Ejecutar acción  Fallback IA
                    ▼
            Kokoro TTS ──► Altavoces
```

### Detalle del componente de audio

- **Entrada**: `sounddevice.InputStream` con callback a 16000 Hz mono
- **VAD**: webrtcvad para filtrar el silencio
- **Palabra de activación**: Whisper tiny model, busca "erika" en la transcripción
- **Transcripción**: Whisper medium model (configurable) tras confirmación de palabra de activación
- **TTS**: Kokoro `KPipeline(lang_code='i')`, voz `if_sara`, genera WAV mediante nombre UUID
- **Reproducción**: `sounddevice.play()` con evento `_tts_done` para sincronización

---

## VASScript — Lenguaje de scripting

VASScript es un lenguaje de scripting minimalista para automatización de escritorio. Ejecución línea por línea, sin operadores aritméticos, todo es una cadena.

### Funciones disponibles (26 en total)

#### IA y TTS
- `ai(prompt)` — Consulta a la IA, devuelve texto
- `say(texto, velocidad?)` — Síntesis de voz (velocidad: 0.5-1.5)
- `listen(prompt?)` — Graba voz, devuelve transcripción

#### Sistema
- `run(comando)` — Ejecuta PowerShell, devuelve salida
- `wait(segundos)` — Pausa la ejecución
- `exit()` — Termina el script
- `getdatetime()` — Fecha/hora actual "YYYY-MM-DD HH:MM"

#### Pantalla (OCR)
- `screen_search(consulta)` — Busca texto en pantalla, establece `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Clic en coordenadas
- `screen_highlight(x, y, an?, al?, dur?)` — Resalta área

#### Ventanas y teclado
- `setActiveWindow(nombre)` — Activa ventana por proceso/título
- `sendText(texto)` — Escribe texto con retardo humano

#### Eventos
- `addevent(fecha, hora, duracion, descripcion, recur?)` — Añade evento
- `listevents(hasta_fecha)` — Lista eventos (JSON)
- `removeevent(nombre)` — Elimina evento (coincidencia difusa)
- `prettyevents(json)` — Formatea eventos en texto legible

#### Memoria y portapapeles
- `readinfo(id)` — Lee archivo informativo
- `writeinfo(texto)` — Escribe archivo informativo, devuelve ID
- `clipboardget()` — Lee portapapeles
- `clipboardset(texto)` — Escribe portapapeles

#### Condiciones
- `ifcontains(var, subcadena, si_verdadero, si_falso?)` — Contiene subcadena
- `ifempty(var, si_vacio, si_lleno?)` — Verifica si está vacío

#### Utilidades
- `trim(texto)` — Elimina espacios
- `len(texto)` — Longitud de cadena
- `contains(texto, subcadena)` — ¿Contiene? ("True"/"False")
- `equals(a, b)` — ¿Igual? ("True"/"False")

### Variables

```vascript
$nombre = "Fabio"           # Asignación
$edad = "54"                # Todo es cadena
$resultado = ai("Hola")     # Resultado de función
say("¡Hola {$nombre}!")     # Interpolación en cadenas
say("Tienes {$edad} años")  # También con variables
```

**Nota:** VASScript NO admite concatenación con `+`. Usa `{$var}` en cadenas.

### Variables globales de screen_search

`screen_search()` establece estas variables globales para la primera coincidencia:
- `$_sx`, `$_sy` — coordenadas del centro
- `$_sw`, `$_sh` — ancho y alto

---

## Servidor MCP — 15 herramientas

El servidor MCP expone 15 herramientas accesibles a la IA en `http://localhost:9988`.

### Sistema de archivos
- `read_file(ruta)` — Lee archivo dentro de Allowed_root
- `write_file(ruta, contenido)` — Escribe archivo dentro de Allowed_root

### Web
- `browse(url)` — Descarga página (estática, httpx+BeautifulSoup)
- `websearch(consulta)` — Busca en DuckDuckGo mediante Playwright
- `webfetch(url)` — Carga página renderizada con JS mediante Playwright

### Cálculo y tiempo
- `calculate(expresion)` — Evalúa expresiones matemáticas (AST, seguro)
- `current_time()` — Fecha/hora actual
- `disk_space()` — Espacio en disco disponible

### Ejecución
- `execute(comando)` — Ejecuta comandos (lista blanca)
- `script(nombre_script)` — Ejecuta archivo VASScript
- `interact(codigo)` — Ejecuta VASScript en línea

### Memoria y portapapeles
- `readinfo(id)` — Lee archivo informativo
- `writeinfo(texto)` — Escribe archivo informativo
- `clipboardget()` — Lee portapapeles
- `clipboardset(texto)` — Escribe portapapeles

### Autenticación

ACL basada en IP mediante `mcp_server/config/tools.yaml`. Cada herramienta tiene lista blanca/negra. Denegación por defecto.

### Comunicación script → VASS

Las herramientas `script` e `interact` usan IPC basada en archivos:
1. Escriben solicitud en `scripts/exec_queue.json`
2. VASS lee la cola (sondeo 1s)
3. Ejecuta el script
4. Escribe resultado en `scripts/exec_result.json`
5. El cliente MCP lee el resultado

---

## Sistema de memoria

### Estructura

```
Allowed_root/
  memory.json          # Índice: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Entrada única: {"info": "cadena JSON"}
    1780427888604.json
    archive/
      2026-06/          # Archivo mensual
```

### Flujo

1. Cada intercambio IA (usuario+asistente) se guarda como archivo JSON en `memory/`
2. `memory.json` mantiene el seguimiento de los últimos 20 ID
3. Después de 5 guardados, los archivos no referenciados van a `archive/{YYYY-MM}/`
4. Los archivos de más de 6 meses se eliminan
5. Cuando la memoria supera `memory_tokens * 4` bytes, se activa la compresión IA:
   - Los mensajes antiguos son resumidos por la IA
   - El resumen se guarda como entrada `summary_id`
   - Los archivos originales se archivan

---

## Eventos y programaciones

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Reunión de equipo",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=diario, "7d"=semanal, "1m"=mensual, "2h"=cada 2 horas
- `notify`: marca de tiempo de cuándo se envió la notificación

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "Copia de seguridad",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- Como los eventos pero activan la ejecución de comandos
- Notificación TTS al inicio y al final
- Validación de comandos contra patrón seguro (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Dependencias

### Núcleo (13)
| Paquete | Uso |
|-----------|-----|
| `sounddevice` | Entrada/salida de audio |
| `numpy` | Arrays para audio e imágenes |
| `faster-whisper` | Reconocimiento de voz STT |
| `webrtcvad` | Detección de actividad de voz |
| `kokoro` | Síntesis de voz TTS |
| `torch` | Deep learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | Escritura de archivos WAV |
| `openai` | Cliente API compatible con OpenAI |
| `mcp[cli]` | Servidor MCP FastMCP |
| `pynput` | Control de ratón/teclado |
| `PySide6` | GUI Qt6 |
| `keyring` | Administrador de credenciales Windows |
| `httpx` | Cliente HTTP para IA y web |

### Web y OCR (6)
| Paquete | Uso |
|-----------|-----|
| `beautifulsoup4` | Análisis HTML de páginas estáticas |
| `lxml` | Motor XML/HTML rápido |
| `playwright` | Navegador headless para páginas JS |
| `mss` | Capturas de pantalla rápidas |
| `easyocr` | Reconocimiento de texto en pantalla |
| `pillow` | Procesamiento de imágenes |

### Utilidades (5)
| Paquete | Uso |
|-----------|-----|
| `pyyaml` | Configuración del servidor MCP |
| `structlog` | Registro estructurado MCP |
| `uvicorn` | Servidor HTTP MCP |
| `psutil` | Monitoreo de recursos |
| `misaki` | Tokenización Kokoro |
| `dateparser` | Análisis de fechas en lenguaje natural |

---

## Funcionamiento interno

### Modelo de hilos

- **Hilo principal**: GUI Qt (bucle de eventos)
- **Hilo de audio**: callback sounddevice
- **Hilo VASS**: bucle de escucha/transcripción
- **Hilos watchdog**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Efímeros**: reproducción TTS, fallback IA, ejecución de scripts

### Mecanismos de bloqueo

- `_trim_lock` — Protege operaciones de memoria
- `_script_engine_lock` — Protege el motor activo
- `_tts_done` (Event) — Sincroniza fin de TTS
- `state_lock` — Protege el estado de la aplicación

### IPC basada en archivos

**exec_queue.json / exec_result.json**:
- El servidor MCP escribe solicitudes de ejecución de scripts
- VASS sondea (1s), ejecuta, escribe resultado
- Timeout: 60s para scripts de archivo, 120s para en línea

### Watchdogs de archivos

VASS monitorea cambios en:
- `settings.ini` — recarga automática
- `commands.ini` — recarga automática
- `events.json` / `schedule.json` — recálculo de próxima alerta

### Almacenamiento de credenciales

- Windows: Administrador de credenciales de Windows mediante `keyring`
- macOS: Keychain
- Linux: D-Bus Secret Service o archivo
- Usado para: clave API IA, permisos de script VASScript (por función)

### Sistema i18n

- `locales/*.json`: 9 idiomas, 215+ claves cada uno
- Archivo `i18n.py`: búsqueda `t(key, lang)`
- Referencia: `it.json`
- Todos los archivos alineados automáticamente

### Rotación de registros

- `debug.log`: máx. 500 KB → `.1`, `.2`
- `mcp_server/LOG/`: máx. 1 MB → `.1`, `.2`
- Utilidad: `log_utils.py`

---

## Configuración avanzada

### [ai]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | Endpoint API |
| `model` | `Qwen3-8B-Q4_K_M` | Nombre del modelo |
| `api_key` | (vacío) | Clave API (vacío para local) |
| `system_message` | (texto largo) | Prompt del sistema |
| `mcp_server_url` | `http://localhost:9988` | URL del servidor MCP |
| `memory_tokens` | `4000` | Límite de memoria en tokens×4 bytes |
| `blacklist` | `Amara.org,QTTS` | Palabras bloqueadas separadas por coma |

### [tts]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | Motor TTS |
| `volume` | `0.50` | Volumen 0-1 |

### [wakeword]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `wakeword` | `erika` | Palabra de activación |
| `sensitivity` | `0.01` | Sensibilidad 0-1 |

### [resources]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `cpu_max` | `75` | Umbral CPU % |
| `ram_max` | `99` | Umbral RAM % |
| `gpu_max` | `75` | Umbral GPU % |
| `vram_max` | `99` | Umbral VRAM % |
| `resource_timeout` | `30` | Tiempo de espera segundos |

### [llamacpp]
| Parámetro | Descripción |
|-----------|-------------|
| `llama_server_path` | Ruta al ejecutable llama.cpp |
| `llama_server_arguments` | Argumentos de línea de comandos |

### [events]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Antelación del recordatorio en segundos (1 hora) |

### [gui]
| Parámetro | Predeterminado | Descripción |
|-----------|---------|-------------|
| `x`, `y` | auto | Posición de la ventana |
| `width`, `height` | `200`, `32` | Dimensiones de la ventana |
| `font_family` | `Segoe UI` | Fuente GUI |
| `font_size` | `10` | Tamaño de fuente |
