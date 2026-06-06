# VASS — Assistente de Voz Inteligente

## O que é o VASS

O VASS é um assistente de voz para Windows, macOS e Linux. Responde a comandos de voz, executa scripts, gere eventos e lembretes, e interage com uma IA local ou remota através de uma API compatível com OpenAI.

**Palavra de ativação predefinida:** "Erika"

**Características principais:**
- Reconhecimento de voz via Whisper (faster-whisper)
- Síntese de voz natural via Kokoro TTS
- IA local ou remota (llama.cpp, OpenAI, qualquer servidor compatível)
- Scripting VASScript para automação do ambiente de trabalho
- Gestão de eventos e lembretes
- Servidor MCP com 15 ferramentas para orquestração de IA
- Histórico de conversas
- Suporte a 9 idiomas (italiano, inglês, alemão, francês, espanhol, português, japonês, coreano, chinês)

---

## Requisitos

- **Python 3.13** ou superior
- **Ligação à internet** (para download de modelos e IA remota)
- **GPU NVIDIA recomendada** para IA local (CPU possível mas lenta)
- **Microfone** funcional
- Windows 10+, macOS 12+ ou Linux moderno

---

## Instalação

### Instalação guiada

Descarregue ou clone o projeto, depois entre na pasta e execute o script:

```bash
cd vass
python install.py
```

**Nota:** o procedimento de instalacao guiada ainda e experimental e pode nao funcionar em todos os sistemas. Se encontrar problemas, use a instalacao manual abaixo.

O assistente irá guiá-lo através de:
1. Escolha do idioma
2. Verificação dos pré-requisitos (Python 3.13+, pip)
3. Pasta de destino
4. Configuração de parâmetros (URL IA, modelo, palavra de ativação)
5. Cópia de ficheiros
6. Criação do ambiente virtual Python (.venv)
7. Instalação das dependências pip
8. Criação do ficheiro settings.ini
9. Criação do inicializador

### Instalação manual

```bash
# Clonar ou copiar os ficheiros para a pasta desejada
cd VASS

# Criar ambiente virtual
python -m venv .venv

# Ativar (Windows)
.venv\Scripts\activate
# ou (macOS/Linux)
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Instalar Chromium para Playwright (pesquisas web)
playwright install chromium

# Criar settings.ini (copiar do settings.ini de exemplo)
```

---

## Configuração

O ficheiro `settings.ini` contém todas as definições. Aqui estão as mais importantes:

| Secção | Parâmetro | Descrição |
|---------|-----------|-------------|
| `[locale]` | `language` | Idioma (it/en/de/fr/es/pt/ja/ko/zh) |
| `[ai]` | `url` | URL do servidor IA compatível com OpenAI |
| `[ai]` | `model` | Nome do modelo IA |
| `[ai]` | `system_message` | Personalidade do assistente |
| `[ai]` | `memory_tokens` | Tamanho máximo da memória |
| `[wakeword]` | `wakeword` | Palavra de ativação (padrão: erika) |
| `[wakeword]` | `sensitivity` | Sensibilidade de deteção (0-1) |
| `[tts]` | `volume` | Volume TTS (0-1) |

As definições são recarregadas automaticamente se modificadas enquanto o VASS está em execução.

---

## Utilização diária

### Iniciar

Duplo clique em `vass.bat` (Windows) ou `vass.sh`/`vass.command` (macOS/Linux).

Ou a partir do terminal:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

### Palavra de ativação

A palavra de ativação é **configurável** pelo utilizador no ficheiro `settings.ini` e pode ser qualquer palavra ou frase curta. Por padrão é "**Erika**".

Quando o VASS deteta a palavra de ativação, emite um sinal sonoro para indicar que está pronto para receber o comando. Fale após o sinal.

Exemplos:
- *"Erika"* (aguardar o sinal), depois *"que horas são?"*
- *"Erika"* (aguardar o sinal), depois *"procura as últimas notícias"*
- *"Erika"* (aguardar o sinal), depois *"lembra-me da reunião amanhã às 14h"*

### Modos: Chat e Transcrição

O VASS pode funcionar em dois modos, selecionáveis a partir do menu popup (botão ≡ à direita do botão principal):

- **Chat** `[C]` — A aplicação reconhece comandos de voz e executa ações (scripts, comandos do sistema) ou interage com a IA. A resposta é lida via TTS.
- **Transcrição** `[T]` — Em vez de interpretar comandos, o VASS transcreve fielmente o que o utilizador diz após a palavra de ativação (sempre após o sinal). O texto é depois colado na aplicação ativa, tornando o VASS um sistema de ditado de texto.

O modo atual é indicado no botão principal: `[C]` para Chat, `[T]` para Transcrição. O último modo utilizado é restaurado ao reiniciar.

### Modo de memória

A partir do menu GUI ou clicando no botão principal:
- **Full** — A IA recebe o resumo da memória
- **Limited** — A IA recebe apenas o histórico recente
- **None** — Sem contexto histórico

### Comandos de voz

Os comandos são configurados em `commands.ini` no formato INI padrão. A chave é a frase a reconhecer, o valor é a ação:

```ini
[general]
procura {termo} = script:pesquisa
abre {programa} = start {programa}
últimas notícias = script:noticias
que horas são = script:hora

[system]
desligar sistema = shutdown /s /t 60
bloquear ecrã = rundll32.exe user32.dll,LockWorkStation
```

- `{termo}`, `{programa}` — variáveis capturadas da voz
- `script:nomescript` — executa `scripts/nomescript.vass`
- Prefixo alternativo: `vasscript:`

Se o padrão tiver variáveis, os seus valores são passados para o script como `$param1`, `$param2`, etc.

### Criar scripts VASScript

Abra o editor de scripts a partir do menu GUI ou execute:
```bash
python scripts_editor.py
```

Todos os scripts vão na pasta `scripts/` com a extensão `.vass`.

Consulte o ficheiro `VASCRIPT_REFERENCE.md` para a referência completa da linguagem.

### Eventos e lembretes

Os eventos são geridos através do ficheiro `events.json`. Um lembrete de voz é emitido 1 hora antes (configurável).

Os agendamentos (procedimentos automatizados) estão em `schedule.json` e acionam a execução de comandos com notificação TTS.

---

## Interface GUI

- **Botão principal** — Clique para alterar o estado (listening/paused). Roda do rato para volume. Arrastar para mover a janela.
- **Barra de volume** (verde, no topo) — Mostra o volume TTS atual
- **Barra multiestado** — Mostra utilização de memória, volume ou progresso do script dependendo do contexto
- **Auto-fade** — A janela torna-se semitransparente quando está inativo e em ecrã completo

### Atalhos

| Tecla | Ação |
|-------|--------|
| `Ctrl+S` | Guardar (nos editores) |
| Clique no botão | Alterar estado |
| Roda sobre o botão | Ajustar volume |
| Clique direito | Menu de contexto |
| Botão "Ler" nos scripts | Lê o script com TTS |

---

## Resolução de problemas

### O VASS não inicia
- Verifique Python 3.13+: `python --version`
- Verifique se `.venv` existe e contém as dependências
- Verifique `debug.log` para erros

### O microfone não funciona
- Verifique se o microfone está ligado e não está a ser usado por outras apps
- Verifique as permissões do sistema para o microfone
- No Windows: Definições → Privacidade → Microfone

### A IA não responde
- Verifique se o servidor IA está em execução em `http://127.0.0.1:8080/v1`
- Verifique `[ai] url` em `settings.ini`
- Se usar llama.cpp, verifique se o modelo existe na pasta `models/`

### O OCR não reconhece o texto no ecrã
- Aumente o tamanho da fonte ou o contraste do texto no ecrã
- EasyOCR funciona melhor com fontes grandes e alto contraste
- O idioma OCR adapta-se automaticamente à localidade configurada

---

## Ficheiros importantes

| Ficheiro | Descrição |
|------|-------------|
| `settings.ini` | Configuração principal |
| `commands.ini` | Comandos de voz personalizados |
| `scripts/*.vass` | Os seus scripts VASScript |
| `events.json` | Os seus eventos e lembretes |
| `schedule.json` | Procedimentos automatizados |
| `memory.json` | Histórico de conversas |
| `debug.log` | Registo de depuração |
| `vass.log` | Registo da aplicação |
