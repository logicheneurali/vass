# VASS — Asistente de Voz Inteligente

## Qué es VASS

VASS es un asistente de voz para Windows, macOS y Linux. Responde a comandos de voz, ejecuta scripts, gestiona eventos y recordatorios, e interactúa con una IA local o remota a través de una API compatible con OpenAI.

**Palabra de activación predeterminada:** "Erika"

**Características principales:**
- Reconocimiento de voz mediante Whisper (faster-whisper)
- Síntesis de voz natural mediante Kokoro TTS
- IA local o remota (llama.cpp, OpenAI, cualquier servidor compatible)
- Scripting VASScript para automatización de escritorio
- Gestión de eventos y recordatorios
- Servidor MCP con 15 herramientas para orquestación de IA
- Historial de conversaciones
- Soporte para 9 idiomas (italiano, inglés, alemán, francés, español, portugués, japonés, coreano, chino)

---

## Requisitos

- **Python 3.13** o superior
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

Di "**Erika**" seguido de tu comando. VASS emite un pitido de confirmación.

Ejemplos:
- *"Erika, ¿qué hora es?"*
- *"Erika, busca las últimas noticias"*
- *"Erika, recuérdame la reunión mañana a las 14"*

### Modo de memoria

Desde el menú GUI o haciendo clic en el botón principal:
- **Full** — La IA recibe el resumen de memoria
- **Limited** — La IA recibe solo el historial reciente
- **None** — Sin contexto histórico

### Comandos de voz

Los comandos se configuran en `commands.ini` en formato INI estándar. La clave es la frase a reconocer, el valor es la acción:

```ini
[general]
busca {termino} = script:busqueda
abre {programa} = start {programa}
últimas noticias = script:noticias
qué hora es = script:hora

[system]
apagar sistema = shutdown /s /t 60
bloquear pantalla = rundll32.exe user32.dll,LockWorkStation
```

- `{termino}`, `{programa}` — variables capturadas desde la voz
- `script:nombrescript` — ejecuta `scripts/nombrescript.vass`
- Prefijo alternativo: `vasscript:`

Si el patrón tiene variables, sus valores se pasan al script como `$param1`, `$param2`, etc.

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
