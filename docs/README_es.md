# VASS — Software asistente de voz

## Qué es VASS

VASS es un asistente de voz para Windows, macOS y Linux. Responde a comandos de voz, ejecuta scripts, gestiona eventos y recordatorios, e interactúa con una IA local o remota a través de una API compatible con OpenAI.

**Palabra de activación predeterminada:** "Erika"

**Características principales:**
- Reconocimiento de voz via Whisper (faster-whisper) con noise floor adaptativo
- Síntesis de voz natural via Kokoro TTS con cadena de reserva de 4 niveles
- IA local o remota (llama.cpp, OpenAI, cualquier servidor compatible)
- Scripting VASScript para automatización de escritorio con 25+ funciones
- Gestión de eventos y operaciones con editor GUI
- Temporizador multilingüe por voz (5 simultáneos)
- Servidor MCP con 21 herramientas para orquestación IA
- Memoria permanente con clasificación y resumen automáticos
- Visor de historial con acciones por mensaje
- Soporte 9 idiomas
- Protección contra desbordamiento de contexto
- Selección de dispositivo de audio (entrada/salida)
- Llamada de herramientas multi-turno para tareas IA complejas


---

## Requisitos

- **Python 3.13** o superior
- **Servidor IA** (llama.cpp o compatible con OpenAI) ya instalado y configurado en el sistema. VASS puede iniciar automáticamente llama.cpp si está configurado, pero **NO instala llama.cpp ni descarga modelos de IA**: debes obtenerlos por separado.
- **Conexión a internet** (para descarga de modelos e IA remota)
- **GPU NVIDIA recomendada** para IA local (CPU posible pero lenta)
- **Micrófono** funcional
- Windows 10+, macOS 12+ o Linux moderno

---

## Instalación

### Instalación guiada

Descarga o clona el proyecto, luego entra en la carpeta y ejecuta el script:

```bash
cd vass
python install.py
```

> **Nota:** la instalación guiada configura VASS pero **NO instala el servidor IA ni los modelos**.
> Debes tener un servidor compatible con OpenAI ya en ejecución (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> o configurar llama.cpp en los ajustes de VASS (que puede iniciarlo automáticamente).

**Nota:** el procedimiento de instalacion guiada aun es experimental y puede no funcionar en todos los sistemas. Si encuentras problemas, usa la instalacion manual a continuacion.

El asistente te guiará a través de:
1. Selección de idioma
2. Verificación de requisitos previos (Python 3.13+, pip)
3. Carpeta de destino
4. Configuración de parámetros (URL IA, modelo, palabra de activación)
5. Copia de archivos
6. Creación del entorno virtual Python (.venv)
7. Instalación de dependencias pip
8. Creación del archivo settings.ini
9. Creación del lanzador

### Instalación manual

```bash
# Clona o copia los archivos en la carpeta deseada
cd VASS

# Crea el entorno virtual
python -m venv .venv

# Activar (Windows)
.venv\Scripts\activate
# o (macOS/Linux)
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar Chromium para Playwright (búsquedas web)
playwright install chromium

# Crear settings.ini (copiar del ejemplo settings.ini)
```

---

## Configuración

El archivo `settings.ini` contiene todas las configuraciones. Estas son las más importantes:

| Sección | Parámetro | Descripción |
|---------|-----------|-------------|
| `[locale]` | `language` | Idioma (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | URL del servidor IA compatible con OpenAI |
| `[ai]` | `model` | Nombre del modelo IA |
| `[ai]` | `system_message` | Personalidad del asistente |
| `[ai]` | `memory_tokens` | Tamaño máximo de memoria |
| `[wakeword]` | `wakeword` | Palabra de activación (por defecto: erika) |
| `[wakeword]` | `sensitivity` | Sensibilidad de detección (0-1) |
| `[tts]` | `volume` | Volumen TTS (0-1) |

Las configuraciones se recargan automáticamente si se modifican mientras VASS está en ejecución.

---

## Uso diario

### Inicio

Doble clic en `vass.bat` (Windows) o `vass.sh`/`vass.command` (macOS/Linux).

O desde la terminal:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

### Palabra de activación

La palabra de activación es **configurable** por el usuario en el archivo `settings.ini` y puede ser cualquier palabra o frase corta. Por defecto es "**Erika**".

Cuando VASS detecta la palabra de activación, emite un pitido para señalar que está listo para recibir el comando. Hable después del pitido.

Ejemplos:
- *"Erika"* (esperar el pitido), luego *"¿qué tiempo hace?"*
- *"Erika"* (esperar el pitido), luego *"lee las noticias"*
- *"Erika"* (esperar el pitido), luego *"¿qué es la inteligencia artificial?"*
- *"Erika"* (esperar el pitido), luego *"traduce a inglés buenos días a todos"*
- *"Erika"* (esperar el pitido), luego *"receta pasta a la carbonara"*

### Modos: Chat y Transcripción

VASS puede funcionar en dos modos, seleccionables desde el menú emergente (botón ≡ a la derecha del botón principal):

- **Chat** `[C]` — La aplicación reconoce comandos de voz y ejecuta acciones (scripts, comandos del sistema) o interactúa con la IA. La respuesta se lee mediante TTS.
- **Transcripción** `[T]` — En lugar de interpretar comandos, VASS transcribe fielmente lo que el usuario dice después de la palabra de activación (siempre después del pitido). El texto se pega luego en la aplicación activa, convirtiendo VASS en un sistema de dictado de texto.

El modo actual se muestra en el botón principal: `[C]` para Chat, `[T]` para Transcripción. El último modo utilizado se restaura al reiniciar.

### Modo de memoria

Desde el menú GUI o haciendo clic en el botón principal:
- **Full** — La IA recibe el resumen de memoria
- **Limited** — La IA recibe solo el historial reciente
- **None** — Sin contexto histórico

### Comandos de voz

Los comandos se configuran en `commands.ini` (formato INI estándar), también editable mediante el editor GUI (`python commands_editor.py`). Cada línea es un par **frase = acción**: la frase es el patrón a reconocer (puede incluir `{variables}`), la acción es qué ejecutar.

```ini
[general]
busca {termino} = script:busqueda
abre {programa} = start {programa}
buscar en línea {escaped_terms} = start firefox "https://duckduckgo.com?q={escaped_terms}"
qué hora es = script:hora

[system]
apagar sistema = shutdown /s /t 60
bloquear pantalla = rundll32.exe user32.dll,LockWorkStation
```

#### Cómo funciona la coincidencia

1. **Reconocimiento difuso**: no se requiere una coincidencia exacta. VASS compara la frase pronunciada con todos los patrones usando un algoritmo de similitud (`difflib`). El patrón con la puntuación más alta por encima del umbral (por defecto `0.75`, configurable en `settings.ini`) se activa.

2. **Variables `{nombre}`**: capturan las palabras pronunciadas en esa posición. Ejemplo: al decir *"busca gatos en internet"*, el sistema captura `termino = "gatos en internet"`.

3. **Variables escapadas `{escaped_nombre}`**: igual que las variables normales, pero el texto capturado se codifica en URL (los espacios se convierten en `%20`). Útil para búsquedas web.

4. **Fallback a IA**: si ningún comando supera el umbral de similitud, la frase se envía a la IA para una respuesta en lenguaje natural.

#### Alternativas con comas (producto cartesiano)

Puedes especificar múltiples alternativas para cada posición usando comas. Los **espacios** separan posiciones, las **comas** separan alternativas dentro de una posición. VASS genera todas las combinaciones posibles (producto cartesiano).

```ini
# Posición única: alternativas para la preposición
click the,on text {text}
```
Genera 3 patrones: `click the text {text}`, `click on text {text}`, `click text {text}`.

```ini
# Dos posiciones: cada posición tiene sus propias alternativas
aa,xx bb,cc {var}
```
Genera 4 patrones: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Mixto: palabra fija + alternativas
turn on,off {device}
```
Genera 2 patrones: `turn on {device}`, `turn off {device}` (sin espacio entre `on` y `off` → misma posición).

La frase pronunciada se compara con todos los patrones generados. Gana la mejor coincidencia fuzzy.

#### Tipos de acciones

| Prefijo | Ejemplo | Comportamiento |
|---------|---------|----------------|
| `script:` | `script:busqueda` | Ejecuta `scripts/busqueda.vass`. Las variables capturadas se convierten en `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:eventos` | Igual que `script:` (prefijo alternativo) |
| URL | `https://...` | Abierto en el navegador predeterminado |
| Comando | `shutdown /s` | Ejecutado directamente como comando del sistema |

#### Nombres de las secciones

Los nombres de sección como `[general]` y `[system]` son solo categorías organizativas — no afectan a la coincidencia. Lo que importa es la **clave** (la frase a reconocer).

### Crear scripts VASScript

Abre el editor de scripts desde el menú GUI o ejecuta:
```bash
python scripts_editor.py
```

Todos los scripts van en la carpeta `scripts/` con extensión `.vass`.

Consulta el archivo `VASCRIPT_REFERENCE.md` para la referencia completa del lenguaje.

### Eventos y recordatorios

Los eventos se gestionan mediante el archivo `events.json`. Se emite un recordatorio de voz 1 hora antes (configurable).

Las programaciones (procedimientos automatizados) están en `schedule.json` y activan la ejecución de comandos con notificación TTS.

---

## Interfaz GUI

- **Botón principal** — Clic para cambiar estado (listening/paused). Rueda del ratón para volumen. Arrastrar para mover la ventana.
- **Barra de volumen** (verde, arriba) — Muestra el volumen TTS actual
- **Barra multiestado** — Muestra uso de memoria, volumen o progreso del script según el contexto
- **Auto-fade** — La ventana se vuelve semitransparente cuando estás inactivo y en pantalla completa

### Atajos

| Tecla | Acción |
|-------|--------|
| `Ctrl+S` | Guardar (en editores) |
| Clic en botón | Cambiar estado |
| Rueda sobre botón | Ajustar volumen |
| Clic derecho | Menú contextual |
| Botón "Leer" en scripts | Lee el script con TTS |

---

## Solución de problemas

> **Importante:** Esta aplicación depende en gran medida del modelo de IA utilizado. Modelos ineficaces o no adecuados para herramientas MCP pueden comprometer la funcionalidad.

### VASS no se inicia
- Verifica Python 3.13+: `python --version`
- Verifica que `.venv` exista y contenga las dependencias
- Revisa `debug.log` para errores

### El micrófono no funciona
- Verifica que el micrófono esté conectado y no en uso por otras apps
- Revisa los permisos del sistema para el micrófono
- En Windows: Configuración → Privacidad → Micrófono

### La IA no responde
- Verifica que el servidor IA esté funcionando en `http://127.0.0.1:8080/v1`
- Revisa `[ai] url` en `settings.ini`
- Si usas llama.cpp, verifica que el modelo exista en la carpeta `models/`

### El OCR no reconoce el texto en pantalla
- Aumenta el tamaño de fuente o el contraste del texto en pantalla
- EasyOCR funciona mejor con fuentes grandes y alto contraste
- El idioma OCR se adapta automáticamente a la configuración regional

---

## Archivos importantes

| Archivo | Descripción |
|------|-------------|
| `settings.ini` | Configuración principal |
| `commands.ini` | Comandos de voz personalizados |
| `scripts/*.vass` | Tus scripts VASScript |
| `events.json` | Tus eventos y recordatorios |
| `schedule.json` | Procedimientos automatizados |
| `memory.json` | Historial de conversaciones |
| `debug.log` | Registro de depuración |
| `vass.log` | Registro de aplicación |
