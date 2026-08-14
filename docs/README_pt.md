# VASS — Software de assistente de voz

## O que é o VASS

O VASS é um assistente de voz para Windows, macOS e Linux. Ele responde a comandos de voz, executa scripts, gerencia eventos e lembretes, lê e responde e-mails e interage com uma IA local ou remota por meio de uma API compatível com OpenAI. Ele também hospeda um servidor MCP que dá à IA acesso direto a arquivos, navegador, calendário, e-mail, notícias e ferramentas do sistema.

**Palavra de ativação padrão:** "Erika" (configurável)

**Versão atual:** 0.8.7

**Principais recursos:**
- Reconhecimento de voz via Whisper (faster-whisper) com VAD Silero e piso de ruído adaptativo
- Síntese de fala natural via Kokoro TTS com uma cadeia de fallback de múltiplas etapas
- IA local ou remota (llama.cpp, OpenAI, qualquer servidor compatível) com início automático opcional do llama.cpp
- Scripting VASScript para automação de desktop com mais de 70 funções integradas
- Gerenciamento de eventos e agendamentos com editor GUI (lembretes, procedimentos automatizados)
- Temporizador de contagem regressiva multilíngue (ativado por voz, 5 simultâneos)
- Servidor MCP com mais de 50 ferramentas para orquestração de IA (navegador, e-mail, notícias, calendário, lugares, arquivos, sistema)
- Memória permanente com classificação automática, resumo e injeção de perfil do usuário
- Cliente de e-mail integrado: Gmail, IMAP, POP3 com fila, contatos e e-mails enviados por IA
- Sistema de plugins: plugins internos e externos por meio de um socket TCP local
- Centro de notificações com roteamento por tipo de evento
- Visualizador de histórico de conversas com ações por mensagem
- Suporte a 9 idiomas
- Proteção contra estouro de contexto (truncamento ou resumo por IA)
- Seleção de dispositivos de áudio (entrada/saída)
- Chamada de ferramentas em múltiplas etapas para tarefas complexas de IA
- Sistema de clima com 3 fontes e banco de dados de geolocalização de 200 mil cidades
- Comandos de voz com atraso de tempo ("desligar em 5 minutos")
- Indicador de atividade de ferramentas MCP em tempo real na GUI
- Compressão heurística de contexto com suporte multilíngue a stopwords
- Contagem de contexto precisa em tokens (tiktoken)
- Sandbox de execução de scripts com autorização SHA-256 e registro de auditoria
- Portão de segurança para ferramentas online sensíveis (consentimento, limite de taxa, registro de auditoria)
- Início automático opcional do sistema

---

## Requisitos

- **Python 3.13** ou superior
- **Servidor de IA** (llama.cpp ou compatível com OpenAI) já instalado e configurado no sistema. O VASS pode iniciar o llama.cpp automaticamente se configurado, mas **NÃO instala o llama.cpp nem baixa modelos de IA**: você deve obtê-los separadamente.
- **Conexão com a internet** (para downloads de modelos de TTS/STT e IA remota)
- **GPU NVIDIA recomendada** para IA local (CPU é possível, mas lenta)
- **Microfone funcionando**
- Windows 10+, macOS 12+ ou Linux moderno

---

## Instalação

### Instalação gráfica (recomendada)

Baixe o instalador na [página de Releases](https://github.com/logicheneurali/vass/releases) e execute-o. O assistente instalará Python, VASS, llama.cpp e um modelo de IA automaticamente — nenhuma configuração manual é necessária.

### Instalação guiada

Baixe ou clone o projeto, entre na pasta e execute o script:

```bash
cd vass
python install.py
```

> **Observação:** a instalação guiada configura o VASS, mas **NÃO instala o servidor de IA nem os modelos**.
> Você deve ter um servidor compatível com OpenAI já em execução (llama.cpp, Ollama, LM Studio, Groq, OpenAI, etc.)
> ou configurar o llama.cpp nas configurações do VASS (que pode iniciá-lo automaticamente).

**Observação:** o procedimento de instalação guiada ainda é experimental e pode não funcionar em todos os sistemas. Se encontrar problemas, use o procedimento de instalação manual abaixo.

O assistente vai guiá-lo por:
1. Seleção do idioma
2. Verificação de pré-requisitos (Python 3.13+, pip)
3. Pasta de destino
4. Configuração de parâmetros (URL da IA, modelo, palavra de ativação)
5. Cópia de arquivos
6. Criação do ambiente virtual Python (.venv)
7. Instalação das dependências do pip
8. Criação do arquivo settings.ini
9. Criação do iniciador (launcher)

### Instalação manual

```bash
# Clone ou copie os arquivos para a pasta desejada
cd VASS

# Crie o ambiente virtual
python -m venv .venv

# Ative-o (Windows)
.venv\Scripts\activate
# ou (macOS/Linux)
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

# Instale o Chromium para o Playwright (pesquisas na web)
playwright install chromium

# Crie o arquivo config/settings.ini (copie de config/settings.example.ini)
```

---

## Configuração

Todas as configurações ficam em `config/settings.ini` (o modelo é `config/settings.example.ini`). Aqui estão as mais importantes:

| Seção | Parâmetro | Descrição |
|---------|-----------|-------------|
| `[locale]` | `language` | Idioma (it/en/de/fr/es/pt/ja/ko/zh) |
| `[wakeword]` | `wakeword` | Palavra de ativação (padrão: erika) |
| `[wakeword]` | `sensitivity` | Sensibilidade da detecção da palavra de ativação |
| `[commands]` | `similarity` | Limiar de correspondência difusa de comandos de voz (padrão 0.6) |
| `[commands]` | `word_learning_enabled` | Aprender novas palavras faladas ao longo do tempo (true/false) |
| `[ai]` | `url` | URL do servidor de IA compatível com OpenAI |
| `[ai]` | `model` | Nome do modelo de IA |
| `[ai]` | `system_message` | Personalidade do assistente |
| `[ai]` | `api_key` | Chave da API (armazenada no keyring do sistema, se definida) |
| `[ai]` | `mcp_server_url` | URL do servidor MCP incluído (padrão `http://localhost:9988`) |
| `[ai]` | `memory_tokens` | Tamanho máximo da memória |
| `[ai]` | `context_length` | Máximo de tokens de contexto (0 = automático) |
| `[ai]` | `overflow_strategy` | Tratamento de estouro de contexto: `truncate` ou `summarize` |
| `[ai]` | `allow_ai_scripts` | Permitir que a IA execute scripts VASScript (true/false) |
| `[llamacpp]` | `llama_server_path` | Local do servidor llama.cpp |
| `[llamacpp]` | `llama_autostart` | Iniciar o llama.cpp automaticamente com o VASS (true/false) |
| `[resources]` | `cpu_max`, `ram_max`, `gpu_max`, `vram_max` | Limites de recursos que controlam as operações da IA |
| `[events]` | `reminder_advance` | Segundos antes de um evento em que o lembrete é emitido (padrão 3600) |
| `[audio]` | `input_device`, `output_device` | Seleção de dispositivos de áudio (-1 = padrão do sistema) |
| `[audio]` | `input_volume`, `output_volume` | Níveis de volume de entrada/saída (0-1) |
| `[audio]` | `app_volume` | Volume mestre de TTS (substitui o legado `[tts] volume`) |
| `[google]` | — | Integração com Google Calendar / Gmail / Google Home |
| `[startup]` | `app_autostart` | Iniciar o VASS automaticamente no login (true/false) |
| `[debug]` | `debug_enabled` | Escrever um log detalhado em `log/debug.log` (true/false) |

As configurações são recarregadas automaticamente se modificadas enquanto o VASS está em execução.

---

## Uso diário

### Iniciando

Clique duas vezes em `vass.bat` (Windows) ou em `vass.sh`/`vass.command` (macOS/Linux).

Ou pelo terminal:
```bash
cd VASS
.venv\Scripts\python vass.py    # Windows
.venv/bin/python vass.py         # macOS/Linux
```

> **Observação:** na primeira execução, os modelos de reconhecimento de fala (Whisper) e de síntese de fala (Kokoro) são baixados automaticamente do HuggingFace. A primeira inicialização pode levar vários minutos (~2-4 GB de download). Isso acontece apenas uma vez.

### Palavra de ativação

A palavra de ativação é **configurável** pelo usuário no arquivo `config/settings.ini` e pode ser qualquer palavra ou frase curta. O padrão é "**Erika**".

Quando o VASS detecta a palavra de ativação, ele emite um bipe para sinalizar que está pronto para receber o comando. Fale após o bipe.

Exemplos:
- *"Erika"* (aguarde o bipe) e depois *"qual é o clima?"*
- *"Erika"* (aguarde o bipe) e depois *"leia as últimas notícias"*
- *"Erika"* (aguarde o bipe) e depois *"o que é inteligência artificial?"*
- *"Erika"* (aguarde o bipe) e depois *"traduza para o italiano bom dia a todos"*
- *"Erika"* (aguarde o bipe) e depois *"receita de pasta carbonara"*

### Modos: Chat e Transcrição

O VASS pode operar em dois modos, selecionáveis pelo menu pop-up (botão ≡ à direita do botão principal):

- **Chat** `[C]` — O aplicativo reconhece comandos de voz e executa ações (scripts, comandos do sistema) ou interage com a IA. A resposta é lida via TTS.
- **Transcrição** `[T]` — Em vez de interpretar comandos, o VASS transcreve fielmente o que o usuário diz após a palavra de ativação (sempre depois do bipe). O texto é então colado no aplicativo ativo, transformando o VASS em um sistema de ditado de texto.

O modo atual é exibido no botão principal: `[C]` para Chat, `[T]` para Transcrição. O último modo usado é restaurado na reinicialização.

### Modo de memória

Pelo menu da GUI ou clicando no botão principal:
- **Completo** — A IA recebe o resumo da memória e seu perfil de usuário
- **Limitado** — A IA recebe apenas o histórico recente
- **Nenhum** — Sem contexto histórico

### Comandos de voz

Os comandos são configurados em `config/commands.ini` (formato INI padrão, `frase = ação`), também editáveis pelo editor da GUI (`python src/commands_editor.py`). Arquivos específicos por idioma `config/commands_{lang}.ini` são carregados sobre o arquivo base. Cada linha é um par **frase = ação**: a frase é o padrão a ser reconhecido (pode incluir `{variables}`), a ação é o que deve ser executado.

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

#### Como a correspondência funciona

1. **Reconhecimento difuso**: uma correspondência exata não é necessária. O VASS compara a frase falada com todos os padrões usando um algoritmo de similaridade (`difflib`). O padrão com a maior pontuação acima do limiar (padrão `0.6`, configurável em `config/settings.ini` na seção `[commands] similarity`) é ativado.

2. **Variáveis `{name}`**: capturam as palavras faladas naquela posição. Exemplo: dizer *"pesquise gatos na internet"* captura `term = "gatos na internet"`.

3. **Variáveis escapadas `{escaped_name}`**: iguais às variáveis normais, mas o texto capturado é codificado em URL (espaços viram `%20`). Útil para pesquisas na web.

4. **Comandos com atraso de tempo**: um sufixo `{duration}` (por exemplo, *"desligar em 5 minutos"*) agenda o comando para ser executado após o tempo determinado pelo sistema de temporizador.

5. **Aprendizado de palavras**: se ativado, o VASS registra como você pronuncia as palavras para melhorar o reconhecimento ao longo do tempo.

6. **Fallback para a IA**: se nenhum comando exceder o limiar de similaridade, a frase é enviada à IA para uma resposta em linguagem natural.

#### Alternativas com vírgulas (produto cartesiano)

Você pode especificar múltiplas alternativas para cada posição de palavra usando vírgulas. **Espaços** separam posições de palavras, **vírgulas** separam alternativas dentro de uma posição. O VASS gera todas as combinações possíveis (produto cartesiano).

```ini
# Posição única: alternativas para a preposição
click the,on text {text}
```
Gera 2 padrões: `click the text {text}`, `click on text {text}`.

```ini
# Duas posições: cada posição tem suas próprias alternativas
aa,xx bb,cc {var}
```
Gera 4 padrões: `aa bb {var}`, `aa cc {var}`, `xx bb {var}`, `xx cc {var}` (2x2 = 4).

```ini
# Misto: palavra fixa + alternativas
turn on,off {device}
```
Gera 2 padrões: `turn on {device}`, `turn off {device}` (sem espaço entre `on` e `off` -> mesma posição).

A frase falada é comparada com todos os padrões gerados. A melhor correspondência difusa vence.

#### Tipos de ação

| Prefixo | Exemplo | Comportamento |
|--------|---------|----------|
| `script:` | `script:search` | Executa `scripts/search.vass`. As variáveis capturadas tornam-se `$param1`, `$param2`, etc. |
| `vasscript:` | `vasscript:events` | Igual a `script:` (prefixo alternativo) |
| Comando | `shutdown /s` | Executado diretamente como um comando do sistema |

#### Nomes de seções

Nomes de seções como `[general]` e `[system]` são apenas categorias organizacionais — não afetam a correspondência. A **chave** (a frase a ser reconhecida) é o que importa.

### Criando scripts VASScript

Abra o editor de scripts pelo menu da GUI ou execute:
```bash
python src/scripts_editor.py
```

Todos os scripts vão para a pasta `scripts/` com a extensão `.vass`.

**Autorização**: antes de executar um script novo ou modificado, o VASS exibe um pop-up pedindo permissão. Os scripts são verificados por hash SHA-256 (armazenado no keyring do sistema): se um arquivo de script for modificado depois de autorizado, as permissões são revogadas automaticamente e o pop-up aparecerá novamente na próxima execução. A permissão pode ser concedida por função ou para o script inteiro. Isso garante que nenhum script possa ser executado em sua máquina sem seu consentimento explícito.

Consulte o arquivo [Referência VASCRIPT](../Allowed_root/VASCRIPT_REFERENCE.md) para a referência completa da linguagem.

### Eventos e lembretes

Os eventos são gerenciados pelo arquivo `Allowed_root/events.json`. Um lembrete por voz é emitido 1 hora antes (configurável via `[events] reminder_advance`).

Os agendamentos (procedimentos automatizados) estão em `Allowed_root/schedules.json` e disparam a execução de comandos com notificação TTS. Sinalizadores adicionais: `silent`, `run_on_startup`, `check_already_running`, `wait_for_completion`.

### Sistema de plugins

O VASS expõe um servidor TCP local (`localhost:8765`) que os plugins usam para se comunicar com o aplicativo: TTS, notificações, consultas à IA, itens RSS, chat, UIs declarativas e muito mais. **Plugins internos** (incluídos no VASS) não podem ser removidos; **plugins externos** podem ser ativados, desativados e removidos pela GUI (menu Plugins).

Plugins internos incluídos: pausa automática por ruído, agente proativo, perfil do usuário, leitor RSS, eventos mundiais, bot do Telegram. Plugins externos disponíveis no disco: gerador de imagens, publicador de notícias, visualizador de linha do tempo.

Consulte o guia [PLUGIN_DEV_pt.md](PLUGIN_DEV_pt.md) para o protocolo completo e como criar seus próprios plugins (também disponível em `PLUGIN_DEV_{en,it,de,fr,es,ja,ko,zh}.md`).

### E-mail

Configure uma ou mais contas em Configurações → E-mail (Gmail via OAuth, ou IMAP/POP3 com SSL/TLS simples). Mensagens recebidas são detectadas e notificadas; a IA pode pesquisar, ler, responder, encaminhar e enviar e-mails — mas os e-mails enviados são sempre colocados em uma **fila** que você deve aprovar e enviar pela caixa de saída. Os contatos são armazenados criptografados.

---

## Interface GUI

- **Botão principal** — Clique para mudar o estado (ouvindo/pausado). Roda do mouse para o volume. Arraste para mover a janela.
- **Barra de volume** (verde, no topo) — Mostra o volume atual de TTS
- **Barra de múltiplos estados** — Mostra uso de memória, volume ou progresso de script/atividade dependendo do contexto
- **Centro de notificações** (sino) — Abas por tipo com ações de mensagem e marcar-todas-como-lidas
- **Indicador de ferramentas** — Ícone em tempo real mostrando a ferramenta MCP que a IA está usando
- **Botão do microfone** — Entrada de voz direta no modo chat
- **Menu de plugins** — Gerencie plugins, configurações de plugins e UIs de plugins
- **Diálogo de configurações** — Configuração completa pela GUI (menu Configurações)
- **Esmaecimento automático** — A janela fica semitransparente quando ociosa e em tela cheia
- **Tela de apresentação (splash)** — Progresso do carregamento na inicialização
- **Tema** — Tema compartilhado entre o aplicativo e todos os editores

### Atalhos

| Tecla | Ação |
|-------|--------|
| `Ctrl+S` | Salvar (nos editores) |
| Clique no botão | Mudar o estado |
| Roda no botão | Ajustar o volume |
| Clique direito | Menu de contexto |
| Clique do meio no botão | Sair |

---

## Solução de problemas

> **Importante:** este aplicativo depende fortemente do modelo de IA usado. Modelos ineficazes ou modelos não adequados para o uso de ferramentas MCP podem comprometer a funcionalidade.

### O VASS não inicia
- Verifique o Python 3.13+: `python --version`
- Verifique se `.venv` existe e contém as dependências
- Verifique `log/debug.log` (ative `[debug] debug_enabled = true`) e `log/crash.log`

### O microfone não funciona
- Verifique se o microfone está conectado e não está em uso por outros aplicativos
- Verifique as permissões do sistema para o microfone
- No Windows: Configurações → Privacidade → Microfone

### A IA não responde
- Verifique se o servidor de IA está em execução em `http://127.0.0.1:8080/v1`
- Verifique `[ai] url` em `config/settings.ini`
- Se estiver usando llama.cpp, verifique se o modelo existe e se `[llamacpp] llama_server_path` está correto
- Verifique `log/llamacpp.log` para erros do llama.cpp

### O OCR não reconhece texto na tela
- Aumente o tamanho da fonte ou o contraste do texto na tela
- O EasyOCR funciona melhor com fontes grandes e alto contraste
- O idioma do OCR se adapta automaticamente ao locale configurado

### A IA não consegue usar uma ferramenta
- Algumas ferramentas online exigem seu consentimento (portão de segurança) — verifique o InfoPanel para solicitações pendentes
- Verifique se o servidor MCP está acessível em `http://localhost:9988` (consulte `[ai] mcp_server_url`)
- Verifique `log/mcp_server.log` para erros do MCP

---

## Arquivos importantes

| Arquivo | Descrição |
|------|-------------|
| `config/settings.ini` | Configuração principal |
| `config/commands.ini` | Comandos de voz base (mais `commands_{lang}.ini`) |
| `config/notifications.ini` | Roteamento de notificações por tipo de evento |
| `scripts/*.vass` | Seus scripts VASScript |
| `Allowed_root/events.json` | Seus eventos e lembretes |
| `Allowed_root/schedules.json` | Procedimentos automatizados |
| `Allowed_root/memory.json` | Histórico de conversas e memória |
| `Allowed_root/private_profile.json` | Perfil do usuário injetado no contexto da IA |
| `plugins/` | Plugins internos e externos |
| `log/debug.log` | Log de depuração detalhado (quando ativado) |
| `log/crash.log` | Log de falhas |
| `log/faulthandler.log` | Saída do tratador de falhas |
| `log/llamacpp.log` | Log do servidor llama.cpp |
