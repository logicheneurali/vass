# VASS — Documentação Avançada

## Arquitetura geral

O VASS é uma aplicação modular composta por vários componentes independentes que comunicam através de filas de ficheiros, sinais Qt e chamadas diretas.

```
┌─────────────────────────────────────────────────┐
│                    vass.py                       │
│              Orquestrador principal              │
│  - Inicialização de componentes                  │
│  - Ciclo de escuta/escrita                      │
│  - Gestão de fallback IA                        │
│  - Execução de scripts                          │
│  - Watchdog de filas de ficheiros               │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
  ┌────────┐┌─────┐┌─────┐┌────┐┌──────────┐
  │  gui.py││TTS  ││STT  ││Eve ││mcp_server│
  │  PySide││Ing. ││Whisp││Lem ││ 15 ferr. │
  └────────┘└─────┘└─────┘└────┘└──────────┘
```

### Componentes principais

| Componente | Ficheiro | Responsabilidade |
|-----------|------|---------------|
| Orquestrador | `vass.py` (1313 linhas) | Inicialização, ciclo principal, IA, scripts, memória |
| GUI | `gui.py` (832 linhas) | Janela PySide6, barras, esbatimento, subjanelas |
| TTS | `tts_engine.py` (138 linhas) | Kokoro TTS, reprodução de áudio, volume |
| STT | `voice_recognition.py` (133 linhas) | faster-whisper, deteção de palavra de ativação |
| Interpretador | `script_engine.py` (761 linhas) | Analisador VASScript, avaliador, 26 funções |
| Eventos | `event_reminder.py` (280 linhas) | Monitor de eventos/agendamentos, alertas TTS |
| Comandos | `command_executor.py` (184 linhas) | Correspondência difusa de padrões, extração de variáveis |
| Servidor MCP | `mcp_server/` | Servidor FastMCP, 15 ferramentas, ACL baseada em IP |
| OCR | `script_engine.py:_preprocess_screen` | EasyOCR com pré-processamento |
| Inatividade | `idle_tracker.py` (67 linhas) | Deteção de inatividade multiplataforma |
| Recursos | `resource_monitor.py` (52 linhas) | Controlo CPU/RAM/GPU/VRAM antes de pedidos IA |
| Registo | `log_utils.py` (13 linhas) | Rotação de ficheiros de registo |

---

## Pipeline de áudio

```
Microfone ──► sounddevice (callback) ──► fila de áudio ──► Whisper (transcrição)
                                                               │
                    ┌──────────────────────────────────────────┤
                    ▼                                          ▼
         Deteção de "Erika"?                        Transcrição completa
                    │                                          │
                    ▼                                          ▼
               Sinal (pronto para comando)                  Coincide commands.ini?
                    │                                  │            │
                    ▼                                  ▼            ▼
             Aguarda comando                       Comando    Sem corres.
                    │                            encontrado
                    ▼                                  │            │
             Transcrição                                ▼            ▼
                    │                          Executar ação   Fallback IA
                    ▼
            Kokoro TTS ──► Altifalantes
```

### Detalhe do componente de áudio

- **Entrada**: `sounddevice.InputStream` com callback a 16000 Hz mono
- **VAD**: webrtcvad para filtrar o silêncio
- **Palavra de ativação**: Whisper tiny model, procura "erika" na transcrição
- **Transcrição**: Whisper medium model (configurável) após confirmação da palavra de ativação
- **TTS**: Kokoro `KPipeline(lang_code='i')`, voz `if_sara`, gera WAV via nome de ficheiro UUID
- **Reprodução**: `sounddevice.play()` com evento `_tts_done` para sincronização

---

## VASScript — Linguagem de scripting

VASScript é uma linguagem de scripting minimalista para automação do ambiente de trabalho. Execução linha a linha, sem operadores aritméticos, tudo é uma string.

### Funções disponíveis (26 no total)

#### IA e TTS
- `ai(prompt)` — Consulta a IA, devolve texto
- `say(texto, velocidade?)` — Síntese de voz (velocidade: 0.5-1.5)
- `listen(prompt?)` — Grava voz, devolve transcrição

#### Sistema
- `run(comando)` — Executa PowerShell, devolve saída
- `wait(segundos)` — Pausa a execução
- `exit()` — Termina o script
- `getdatetime()` — Data/hora atual "YYYY-MM-DD HH:MM"

#### Ecrã (OCR)
- `screen_search(consulta)` — Procura texto no ecrã, define `$_sx`, `$_sy`, `$_sw`, `$_sh`
- `screen_click(x?, y?)` — Clique nas coordenadas
- `screen_highlight(x, y, l?, a?, dur?)` — Destaca área

#### Janelas e teclado
- `setActiveWindow(nome)` — Ativa janela por processo/título
- `sendText(texto)` — Escreve texto com atraso humano

#### Eventos
- `addevent(data, hora, duracao, descricao, recur?)` — Adiciona evento
- `listevents(ate_data)` — Lista eventos (JSON)
- `removeevent(nome)` — Remove evento (correspondência difusa)
- `prettyevents(json)` — Formata eventos em texto legível

#### Memória e área de transferência
- `readinfo(id)` — Lê ficheiro informativo
- `writeinfo(texto)` — Escreve ficheiro informativo, devolve ID
- `clipboardget()` — Lê área de transferência
- `clipboardset(texto)` — Escreve área de transferência

#### Condições
- `ifcontains(var, substring, se_verdadeiro, se_falso?)` — Contém substring
- `ifempty(var, se_vazio, se_cheio?)` — Verifica se está vazio

#### Utilitários
- `trim(texto)` — Remove espaços
- `len(texto)` — Comprimento da string
- `contains(texto, substring)` — Contém? ("True"/"False")
- `equals(a, b)` — Igual? ("True"/"False")

### Variáveis

```vascript
$nome = "Fabio"            # Atribuição
$idade = "54"              # Tudo é string
$resultado = ai("Olá")     # Resultado de função
say("Olá {$nome}!")        # Interpolação em strings
say("Tens {$idade} anos")  # Também com variáveis
```

**Nota:** VASScript NÃO suporta concatenação com `+`. Use `{$var}` em strings.

### Variáveis globais de screen_search

`screen_search()` define estas variáveis globais para a primeira correspondência:
- `$_sx`, `$_sy` — coordenadas do centro
- `$_sw`, `$_sh` — largura e altura

---

## Servidor MCP — 15 ferramentas

O servidor MCP expõe 15 ferramentas acessíveis à IA em `http://localhost:9988`.

### Sistema de ficheiros
- `read_file(caminho)` — Lê ficheiro dentro de Allowed_root
- `write_file(caminho, conteudo)` — Escreve ficheiro dentro de Allowed_root

### Web
- `browse(url)` — Descarrega página (estática, httpx+BeautifulSoup)
- `websearch(consulta)` — Pesquisa no DuckDuckGo via Playwright
- `webfetch(url)` — Carrega página renderizada com JS via Playwright

### Cálculo e tempo
- `calculate(expressao)` — Avalia expressões matemáticas (AST, seguro)
- `current_time()` — Data/hora atual
- `disk_space()` — Espaço em disco disponível

### Execução
- `execute(comando)` — Executa comandos (lista branca)
- `script(nome_script)` — Executa ficheiro VASScript
- `interact(codigo)` — Executa VASScript inline

### Memória e área de transferência
- `readinfo(id)` — Lê ficheiro informativo
- `writeinfo(texto)` — Escreve ficheiro informativo
- `clipboardget()` — Lê área de transferência
- `clipboardset(texto)` — Escreve área de transferência

### Autenticação

ACL baseada em IP via `mcp_server/config/tools.yaml`. Cada ferramenta tem lista branca/negra. Negação por defeito.

### Comunicação script → VASS

As ferramentas `script` e `interact` usam IPC baseada em ficheiros:
1. Escrevem pedido em `scripts/exec_queue.json`
2. VASS lê a fila (sondagem 1s)
3. Executa o script
4. Escreve resultado em `scripts/exec_result.json`
5. O cliente MCP lê o resultado

---

## Sistema de memória

### Estrutura

```
Allowed_root/
  memory.json          # Índice: {"history": [id1, id2], "summary_id": "id3"}
  memory/
    1780394454383.json  # Entrada única: {"info": "string JSON"}
    1780427888604.json
    archive/
      2026-06/          # Arquivo mensal
```

### Fluxo

1. Cada troca IA (utilizador+assistente) é guardada como ficheiro JSON em `memory/`
2. `memory.json` mantém o registo dos últimos 20 IDs
3. Após 5 gravações, os ficheiros não referenciados vão para `archive/{YYYY-MM}/`
4. Arquivos com mais de 6 meses são eliminados
5. Quando a memória excede `memory_tokens * 4` bytes, a compressão IA é ativada:
   - As mensagens antigas são resumidas pela IA
   - O resumo é guardado como entrada `summary_id`
   - Os ficheiros originais são arquivados

---

## Eventos e agendamentos

### events.json
```json
{
  "events": [{
    "date": "2026-06-15",
    "time": "14:30",
    "duration": 60,
    "description": "Reunião de equipa",
    "recur": "7d",
    "notify": "2026-06-15 13:30:00"
  }]
}
```
- `recur`: "1d"=diário, "7d"=semanal, "1m"=mensal, "2h"=a cada 2 horas
- `notify`: carimbo de data/hora de quando a notificação foi enviada

### schedule.json
```json
{
  "schedules": [{
    "date": "2026-06-05",
    "time": "08:00",
    "duration": 5,
    "description": "Backup",
    "recur": "1d",
    "command": "powershell",
    "arguments": "-File backup.ps1"
  }]
}
```
- Como os eventos mas acionam a execução de comandos
- Notificação TTS no início e no fim
- Validação de comandos contra padrão seguro (`.exe`, `.bat`, `.ps1`, `.py`, `.cmd`, `.vbs`)

---

## Dependências

### Núcleo (13)
| Pacote | Utilização |
|-----------|-----|
| `sounddevice` | Entrada/saída de áudio |
| `numpy` | Arrays para áudio e imagens |
| `faster-whisper` | Reconhecimento de voz STT |
| `webrtcvad` | Deteção de atividade de voz |
| `kokoro` | Síntese de voz TTS |
| `torch` | Deep learning (Kokoro, Whisper, EasyOCR) |
| `soundfile` | Escrita de ficheiros WAV |
| `openai` | Cliente API compatível com OpenAI |
| `mcp[cli]` | Servidor MCP FastMCP |
| `pynput` | Controlo de rato/teclado |
| `PySide6` | GUI Qt6 |
| `keyring` | Gestor de credenciais Windows |
| `httpx` | Cliente HTTP para IA e web |

### Web e OCR (6)
| Pacote | Utilização |
|-----------|-----|
| `beautifulsoup4` | Análise HTML de páginas estáticas |
| `lxml` | Motor XML/HTML rápido |
| `playwright` | Navegador headless para páginas JS |
| `mss` | Capturas de ecrã rápidas |
| `easyocr` | Reconhecimento de texto no ecrã |
| `pillow` | Processamento de imagens |

### Utilitários (5)
| Pacote | Utilização |
|-----------|-----|
| `pyyaml` | Configuração do servidor MCP |
| `structlog` | Registo estruturado MCP |
| `uvicorn` | Servidor HTTP MCP |
| `psutil` | Monitorização de recursos |
| `misaki` | Tokenização Kokoro |
| `dateparser` | Análise de datas em linguagem natural |

---

## Funcionamento interno

### Modelo de threading

- **Thread principal**: GUI Qt (ciclo de eventos)
- **Thread de áudio**: callback sounddevice
- **Thread VASS**: ciclo de escuta/transcrição
- **Threads watchdog**: `_watch_commands_file`, `_watch_settings_file`, `_watch_script_queue`
- **Efémeros**: reprodução TTS, fallback IA, execução de scripts

### Mecanismos de bloqueio

- `_trim_lock` — Protege operações de memória
- `_script_engine_lock` — Protege o motor ativo
- `_tts_done` (Event) — Sincroniza fim do TTS
- `state_lock` — Protege o estado da aplicação

### IPC baseada em ficheiros

**exec_queue.json / exec_result.json**:
- O servidor MCP escreve pedidos de execução de scripts
- VASS consulta (1s), executa, escreve resultado
- Timeout: 60s para scripts de ficheiro, 120s para inline

### Watchdogs de ficheiros

O VASS monitoriza alterações em:
- `settings.ini` — recarga automática
- `commands.ini` — recarga automática
- `events.json` / `schedule.json` — recálculo do próximo alerta

### Armazenamento de credenciais

- Windows: Gestor de Credenciais do Windows via `keyring`
- macOS: Keychain
- Linux: D-Bus Secret Service ou ficheiro
- Usado para: chave API IA, permissões de script VASScript (por função)

### Sistema i18n

- `locales/*.json`: 9 idiomas, 215+ chaves cada
- Ficheiro `i18n.py`: pesquisa `t(key, lang)`
- Referência: `it.json`
- Todos os ficheiros alinhados automaticamente

### Rotação de registos

- `debug.log`: máx. 500 KB → `.1`, `.2`
- `mcp_server/LOG/`: máx. 1 MB → `.1`, `.2`
- Utilitário: `log_utils.py`

---

## Configuração avançada

### [ai]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `url` | `http://127.0.0.1:8080/v1` | Endpoint API |
| `model` | `Qwen3-8B-Q4_K_M` | Nome do modelo |
| `api_key` | (vazio) | Chave API (vazio para local) |
| `system_message` | (texto longo) | Prompt do sistema |
| `mcp_server_url` | `http://localhost:9988` | URL do servidor MCP |
| `memory_tokens` | `4000` | Limite de memória em tokens×4 bytes |
| `blacklist` | `Amara.org,QTTS` | Palavras bloqueadas separadas por vírgula |

### [tts]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `tts_engine` | `kokoro` | Motor TTS |
| `volume` | `0.50` | Volume 0-1 |

### [wakeword]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `wakeword` | `erika` | Palavra de ativação |
| `sensitivity` | `0.01` | Sensibilidade 0-1 |

### [resources]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `cpu_max` | `75` | Limiar CPU % |
| `ram_max` | `99` | Limiar RAM % |
| `gpu_max` | `75` | Limiar GPU % |
| `vram_max` | `99` | Limiar VRAM % |
| `resource_timeout` | `30` | Tempo limite de espera segundos |

### [llamacpp]
| Parâmetro | Descrição |
|-----------|-------------|
| `llama_server_path` | Caminho do executável llama.cpp |
| `llama_server_arguments` | Argumentos de linha de comando |

### [events]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `reminder_advance` | `3600` | Antecedência do lembrete em segundos (1 hora) |

### [gui]
| Parâmetro | Padrão | Descrição |
|-----------|---------|-------------|
| `x`, `y` | auto | Posição da janela |
| `width`, `height` | `200`, `32` | Dimensões da janela |
| `font_family` | `Segoe UI` | Tipo de letra GUI |
| `font_size` | `10` | Tamanho da letra |
