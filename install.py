#!/usr/bin/env python3
"""VASS Installation Wizard — guided setup for Windows, macOS, Linux."""

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Terminal colors ───────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"

LANG = "en"

# ── Translations ──────────────────────────────────────────────────────────────
_lang_names = {
    "it": "Italiano", "en": "English", "de": "Deutsch", "fr": "Francais",
    "es": "Espanol", "pt": "Portugues", "ja": "日本語", "ko": "한국어", "zh": "中文",
}
_lang_choices = ["it", "en", "de", "fr", "es", "pt", "ja", "ko", "zh"]

_T = {
    # -- Welcome
    "welcome_title": {
        "en": "VASS — Installation Wizard",
        "it": "VASS — Installazione Guidata",
        "de": "VASS — Installationsassistent",
        "fr": "VASS — Assistant d'installation",
        "es": "VASS — Asistente de instalacion",
        "pt": "VASS — Assistente de instalacao",
        "ja": "VASS — インストールウィザード",
        "ko": "VASS — 설치 마법사",
        "zh": "VASS — 安装向导",
    },
    "welcome_body": {
        "en": "This wizard will install VASS on your system.",
        "it": "Questo wizard installera VASS sul tuo sistema.",
        "de": "Dieser Assistent installiert VASS auf Ihrem System.",
        "fr": "Cet assistant va installer VASS sur votre systeme.",
        "es": "Este asistente instalara VASS en tu sistema.",
        "pt": "Este assistente instalara o VASS no seu sistema.",
        "ja": "このウィザードはVASSをシステムにインストールします。",
        "ko": "이 마법사는 시스템에 VASS를 설치합니다.",
        "zh": "此向导将在您的系统上安装VASS。",
    },
    "welcome_reqs": {
        "en": "Requirements: Python 3.13+, internet connection, GPU recommended.",
        "it": "Requisiti: Python 3.13+, connessione internet, GPU consigliata.",
        "de": "Voraussetzungen: Python 3.13+, Internetverbindung, GPU empfohlen.",
        "fr": "Requis: Python 3.13+, connexion internet, GPU recommandee.",
        "es": "Requisitos: Python 3.13+, conexion a internet, GPU recomendada.",
        "pt": "Requisitos: Python 3.13+, ligacao a internet, GPU recomendada.",
        "ja": "要件: Python 3.13+、インターネット接続、GPU推奨。",
        "ko": "요구사항: Python 3.13+, 인터넷 연결, GPU 권장.",
        "zh": "要求: Python 3.13+、网络连接、推荐GPU。",
    },
    "press_enter": {
        "en": "Press Enter to begin",
        "it": "Premi Invio per iniziare",
        "de": "Eingabetaste zum Starten",
        "fr": "Appuyez sur Entree pour commencer",
        "es": "Presiona Enter para comenzar",
        "pt": "Pressione Enter para comecar",
        "ja": "Enterキーで開始",
        "ko": "Enter를 눌러 시작",
        "zh": "按回车开始",
    },

    # -- Step titles
    "step_lang": {
        "en": "Language / Lingua",
        "it": "Lingua / Language",
        "de": "Sprache / Language",
        "fr": "Langue / Language",
        "es": "Idioma / Language",
        "pt": "Idioma / Language",
        "ja": "言語 / Language",
        "ko": "언어 / Language",
        "zh": "语言 / Language",
    },
    "step_prereq": {
        "en": "Checking prerequisites",
        "it": "Verifica prerequisiti",
        "de": "Voraussetzungen prufen",
        "fr": "Verification des prerequis",
        "es": "Verificando requisitos",
        "pt": "Verificar pre-requisitos",
        "ja": "前提条件の確認",
        "ko": "필수 조건 확인",
        "zh": "检查先决条件",
    },
    "step_dest": {
        "en": "Destination folder",
        "it": "Cartella di destinazione",
        "de": "Zielordner",
        "fr": "Dossier de destination",
        "es": "Carpeta de destino",
        "pt": "Pasta de destino",
        "ja": "インストール先フォルダ",
        "ko": "대상 폴더",
        "zh": "目标文件夹",
    },
    "step_config": {
        "en": "Configuration parameters",
        "it": "Configurazione parametri",
        "de": "Konfigurationsparameter",
        "fr": "Parametres de configuration",
        "es": "Parametros de configuracion",
        "pt": "Parametros de configuracao",
        "ja": "設定パラメータ",
        "ko": "구성 매개변수",
        "zh": "配置参数",
    },
    "step_copy": {
        "en": "Copying source files",
        "it": "Copia file sorgente",
        "de": "Quelldateien kopieren",
        "fr": "Copie des fichiers source",
        "es": "Copiando archivos fuente",
        "pt": "A copiar ficheiros fonte",
        "ja": "ソースファイルをコピー中",
        "ko": "소스 파일 복사 중",
        "zh": "复制源文件",
    },
    "step_venv": {
        "en": "Creating Python virtual environment",
        "it": "Creazione ambiente virtuale Python",
        "de": "Virtuelle Python-Umgebung erstellen",
        "fr": "Creation de l'environnement virtuel Python",
        "es": "Creando entorno virtual Python",
        "pt": "A criar ambiente virtual Python",
        "ja": "Python仮想環境を作成中",
        "ko": "Python 가상 환경 생성 중",
        "zh": "创建Python虚拟环境",
    },
    "step_pip": {
        "en": "Installing pip dependencies (in virtual environment)",
        "it": "Installazione dipendenze pip (nell'ambiente virtuale)",
        "de": "Pip-Abhangigkeiten installieren (in virtueller Umgebung)",
        "fr": "Installation des dependances pip (dans l'environnement virtuel)",
        "es": "Instalando dependencias pip (en entorno virtual)",
        "pt": "A instalar dependencias pip (no ambiente virtual)",
        "ja": "pip依存関係をインストール中 (仮想環境内)",
        "ko": "pip 종속성 설치 중 (가상 환경 내)",
        "zh": "安装pip依赖 (虚拟环境中)",
    },
    "step_settings": {
        "en": "Generating settings.ini",
        "it": "Generazione settings.ini",
        "de": "settings.ini generieren",
        "fr": "Generation de settings.ini",
        "es": "Generando settings.ini",
        "pt": "A gerar settings.ini",
        "ja": "settings.iniを生成中",
        "ko": "settings.ini 생성 중",
        "zh": "生成settings.ini",
    },
    "step_launcher": {
        "en": "Creating launcher",
        "it": "Creazione lanciatore",
        "de": "Starter erstellen",
        "fr": "Creation du lanceur",
        "es": "Creando lanzador",
        "pt": "A criar lancador",
        "ja": "ランチャーを作成中",
        "ko": "런처 생성 중",
        "zh": "创建启动器",
    },
    "step_summary": {
        "en": "Summary",
        "it": "Riepilogo",
        "de": "Zusammenfassung",
        "fr": "Resume",
        "es": "Resumen",
        "pt": "Resumo",
        "ja": "概要",
        "ko": "요약",
        "zh": "摘要",
    },

    # -- Questions
    "q_lang": {
        "en": "Choose language / Scegli lingua",
        "it": "Scegli lingua / Choose language",
        "de": "Sprache wahlen / Choose language",
        "fr": "Choisir la langue / Choose language",
        "es": "Elegir idioma / Choose language",
        "pt": "Escolher idioma / Choose language",
        "ja": "言語を選択 / Choose language",
        "ko": "언어 선택 / Choose language",
        "zh": "选择语言 / Choose language",
    },
    "q_dest": {
        "en": "Where to install VASS?",
        "it": "Dove installare VASS?",
        "de": "Wo soll VASS installiert werden?",
        "fr": "Ou installer VASS ?",
        "es": "Donde instalar VASS?",
        "pt": "Onde instalar o VASS?",
        "ja": "VASSをどこにインストールしますか？",
        "ko": "VASS를 어디에 설치하시겠습니까?",
        "zh": "VASS安装到哪里？",
    },
    "q_overwrite": {
        "en": "Folder exists. Overwrite files?",
        "it": "La cartella esiste gia. Sovrascrivere i file?",
        "de": "Ordner existiert. Dateien uberschreiben?",
        "fr": "Le dossier existe. Ecraser les fichiers ?",
        "es": "La carpeta ya existe. Sobrescribir archivos?",
        "pt": "A pasta ja existe. Sobrescrever ficheiros?",
        "ja": "フォルダが既に存在します。上書きしますか？",
        "ko": "폴더가 이미 존재합니다. 덮어쓰시겠습니까?",
        "zh": "文件夹已存在。覆盖文件？",
    },
    "q_wake": {
        "en": "Wake word (activation word)",
        "it": "Wake word (parola di attivazione)",
        "de": "Wake-Wort (Aktivierungswort)",
        "fr": "Mot de reveil (mot d'activation)",
        "es": "Wake word (palabra de activacion)",
        "pt": "Wake word (palavra de ativacao)",
        "ja": "ウェイクワード (起動ワード)",
        "ko": "웨이크 워드 (활성화 단어)",
        "zh": "唤醒词 (激活词)",
    },
    "q_model": {
        "en": "AI model (name as it appears in the llama.cpp server)",
        "it": "Modello AI (nome come appare nel server llama.cpp)",
        "de": "KI-Modell (Name wie im llama.cpp-Server)",
        "fr": "Modele IA (nom tel qu'il apparait dans le serveur llama.cpp)",
        "es": "Modelo IA (nombre tal como aparece en el servidor llama.cpp)",
        "pt": "Modelo IA (nome como aparece no servidor llama.cpp)",
        "ja": "AIモデル (llama.cppサーバーでの名前)",
        "ko": "AI 모델 (llama.cpp 서버에서의 이름)",
        "zh": "AI模型 (llama.cpp服务器中的名称)",
    },
    "q_url": {
        "en": "AI server URL (OpenAI-compatible)",
        "it": "URL server AI (OpenAI-compatibile)",
        "de": "KI-Server-URL (OpenAI-kompatibel)",
        "fr": "URL du serveur IA (compatible OpenAI)",
        "es": "URL del servidor IA (compatible OpenAI)",
        "pt": "URL do servidor IA (compativel OpenAI)",
        "ja": "AIサーバーURL (OpenAI互換)",
        "ko": "AI 서버 URL (OpenAI 호환)",
        "zh": "AI服务器URL (OpenAI兼容)",
    },
    "q_apikey": {
        "en": "API key (leave empty for local server)",
        "it": "API key (lasciare vuoto per server locale)",
        "de": "API-Schlussel (leer lassen fur lokalen Server)",
        "fr": "Cle API (laisser vide pour serveur local)",
        "es": "API key (dejar vacio para servidor local)",
        "pt": "Chave API (deixar vazio para servidor local)",
        "ja": "APIキー (ローカルサーバーの場合は空)",
        "ko": "API 키 (로컬 서버의 경우 비워둠)",
        "zh": "API密钥 (本地服务器留空)",
    },
    "q_whisper": {
        "en": "Whisper model size (STT)",
        "it": "Dimensione modello Whisper (STT)",
        "de": "Whisper-Modellgrosse (STT)",
        "fr": "Taille du modele Whisper (STT)",
        "es": "Tamano del modelo Whisper (STT)",
        "pt": "Tamanho do modelo Whisper (STT)",
        "ja": "Whisperモデルサイズ (STT)",
        "ko": "Whisper 모델 크기 (STT)",
        "zh": "Whisper模型大小 (STT)",
    },
    "q_sysmsg": {
        "en": "System message (assistant personality)",
        "it": "Messaggio di sistema (personalita dell'assistente)",
        "de": "Systemnachricht (Assistenten-Personlichkeit)",
        "fr": "Message systeme (personnalite de l'assistant)",
        "es": "Mensaje del sistema (personalidad del asistente)",
        "pt": "Mensagem de sistema (personalidade do assistente)",
        "ja": "システムメッセージ (アシスタントの性格)",
        "ko": "시스템 메시지 (어시스턴트 성격)",
        "zh": "系统消息 (助手个性)",
    },

    # -- Default system messages per language
    "default_sysmsg": {
        "en": "You are a cheerful voice assistant. Always respond in English and concisely.",
        "it": "Sei un allegro assistente vocale. Rispondi sempre in italiano e in modo breve "
              "ma esaustivo, evitando formattazioni complesse. solo testo puro, nessun emoji "
              "o testo html o markdown.",
        "de": "Du bist ein frohlicher Sprachassistent. Antworte immer auf Deutsch und kurz "
              "aber ausfuhrlich, ohne komplexe Formatierung.",
        "fr": "Tu es un assistant vocal joyeux. Reponds toujours en francais de maniere breve "
              "mais exhaustive, sans formatage complexe.",
        "es": "Eres un alegre asistente de voz. Responde siempre en espanol de forma breve "
              "pero exhaustiva, sin formato complejo.",
        "pt": "Es um assistente de voz alegre. Responde sempre em portugues de forma breve "
              "mas exaustiva, sem formatacao complexa.",
        "ja": "あなたは陽気な音声アシスタントです。常に日本語で簡潔に答えてください。",
        "ko": "당신은 쾌활한 음성 비서입니다. 항상 한국어로 간결하게 답변하세요.",
        "zh": "你是一个开朗的语音助手。始终用中文简洁回答。",
    },

    # -- Messages
    "py_ok": {
        "en": "Python {0}.{1}.{2} — OK",
        "it": "Python {0}.{1}.{2} — OK",
    },
    "py_err": {
        "en": "ERROR: Python 3.13+ required. Found {0}.{1}.",
        "it": "ERRORE: Python 3.13+ richiesto. Trovato {0}.{1}.",
        "de": "FEHLER: Python 3.13+ erforderlich. Gefunden {0}.{1}.",
        "fr": "ERREUR: Python 3.13+ requis. Trouve {0}.{1}.",
        "es": "ERROR: Python 3.13+ requerido. Encontrado {0}.{1}.",
        "pt": "ERRO: Python 3.13+ necessario. Encontrado {0}.{1}.",
        "ja": "エラー: Python 3.13+が必要です。見つかったバージョン: {0}.{1}。",
        "ko": "오류: Python 3.13+가 필요합니다. 발견된 버전: {0}.{1}.",
        "zh": "错误: 需要Python 3.13+。找到 {0}.{1}。",
    },
    "pip_ok": {
        "en": "pip available — OK",
        "it": "pip disponibile — OK",
        "de": "pip verfugbar — OK",
        "fr": "pip disponible — OK",
        "es": "pip disponible — OK",
        "pt": "pip disponivel — OK",
        "ja": "pip利用可能 — OK",
        "ko": "pip 사용 가능 — OK",
        "zh": "pip可用 — OK",
    },
    "pip_err": {
        "en": "ERROR: pip not available. Install pip before proceeding.",
        "it": "ERRORE: pip non disponibile. Installa pip prima di proseguire.",
        "de": "FEHLER: pip nicht verfugbar. Installieren Sie pip bevor Sie fortfahren.",
        "fr": "ERREUR: pip non disponible. Installez pip avant de continuer.",
        "es": "ERROR: pip no disponible. Instala pip antes de continuar.",
        "pt": "ERRO: pip nao disponivel. Instale o pip antes de continuar.",
        "ja": "エラー: pipが利用できません。続行する前にpipをインストールしてください。",
        "ko": "오류: pip를 사용할 수 없습니다. 계속하기 전에 pip를 설치하세요.",
        "zh": "错误: pip不可用。请先安装pip再继续。",
    },
    "dest": {
        "en": "Destination: {0}",
        "it": "Destinazione: {0}",
        "de": "Ziel: {0}",
        "fr": "Destination: {0}",
        "es": "Destino: {0}",
        "pt": "Destino: {0}",
        "ja": "インストール先: {0}",
        "ko": "대상: {0}",
        "zh": "目标: {0}",
    },
    "copy_progress": {
        "en": "Copied {0} files...",
        "it": "Copiati {0} file...",
        "de": "{0} Dateien kopiert...",
        "fr": "{0} fichiers copies...",
        "es": "{0} archivos copiados...",
        "pt": "{0} ficheiros copiados...",
        "ja": "{0}ファイルをコピーしました...",
        "ko": "{0}개 파일 복사됨...",
        "zh": "已复制 {0} 个文件...",
    },
    "copy_done": {
        "en": "Copied {0} files out of {1} found.   ",
        "it": "Copiati {0} file su {1} trovati.   ",
        "de": "{0} Dateien von {1} gefundenen kopiert.   ",
        "fr": "{0} fichiers copies sur {1} trouves.   ",
        "es": "{0} archivos copiados de {1} encontrados.   ",
        "pt": "{0} ficheiros copiados de {1} encontrados.   ",
        "ja": "見つかった{1}ファイル中{0}ファイルをコピーしました。   ",
        "ko": "발견된 {1}개 중 {0}개 파일 복사됨.   ",
        "zh": "已复制 {0}/{1} 个文件。   ",
    },
    "source": {
        "en": "Source: {0}",
        "it": "Sorgente: {0}",
        "de": "Quelle: {0}",
        "fr": "Source: {0}",
        "es": "Origen: {0}",
        "pt": "Origem: {0}",
        "ja": "ソース: {0}",
        "ko": "소스: {0}",
        "zh": "源: {0}",
    },
    "venv_creating": {
        "en": "Creating venv in {0} ...",
        "it": "Creazione venv in {0} ...",
        "de": "Venv wird erstellt in {0} ...",
        "fr": "Creation du venv dans {0} ...",
        "es": "Creando venv en {0} ...",
        "pt": "A criar venv em {0} ...",
        "ja": "{0}にvenvを作成中...",
        "ko": "{0}에 venv 생성 중...",
        "zh": "在 {0} 中创建venv...",
    },
    "venv_ok": {
        "en": "Virtual environment created — OK",
        "it": "Ambiente virtuale creato — OK",
        "de": "Virtuelle Umgebung erstellt — OK",
        "fr": "Environnement virtuel cree — OK",
        "es": "Entorno virtual creado — OK",
        "pt": "Ambiente virtual criado — OK",
        "ja": "仮想環境が作成されました — OK",
        "ko": "가상 환경이 생성되었습니다 — OK",
        "zh": "虚拟环境已创建 — OK",
    },
    "venv_fail": {
        "en": "ERROR creating venv:",
        "it": "ERRORE nella creazione del venv:",
        "de": "FEHLER beim Erstellen des venv:",
        "fr": "ERREUR lors de la creation du venv:",
        "es": "ERROR al crear el venv:",
        "pt": "ERRO ao criar o venv:",
        "ja": "venv\u4f5c\u6210\u30a8\u30e9\u30fc:",
        "ko": "venv \uc0dd\uc131 \uc624\ub958:",
        "zh": "\u521b\u5efa venv \u9519\u8bef:",
    },
    "venv_fail_ensurepip": {
        "en": "The venv module needs python3-venv or python3.13-venv package. Install it first.",
        "it": "Il modulo venv richiede il pacchetto python3-venv o python3.13-venv. Installalo prima.",
        "de": "Das venv-Modul benoetigt das Paket python3-venv oder python3.13-venv. Installieren Sie es zuerst.",
        "fr": "Le module venv necessite le paquet python3-venv ou python3.13-venv. Installez-le d'abord.",
        "es": "El modulo venv necesita el paquete python3-venv o python3.13-venv. Instalalo primero.",
        "pt": "O modulo venv precisa do pacote python3-venv ou python3.13-venv. Instale-o primeiro.",
        "ja": "venv\u30e2\u30b8\u30e5\u30fc\u30eb\u306b\u306f python3-venv \u307e\u305f\u306f python3.13-venv \u30d1\u30c3\u30b1\u30fc\u30b8\u304c\u5fc5\u8981\u3067\u3059\u3002\u5148\u306b\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "ko": "venv \ubaa8\ub4c8\uc5d0\ub294 python3-venv \ub610\ub294 python3.13-venv \ud328\ud0a4\uc9c0\uac00 \ud544\uc694\ud569\ub2c8\ub2e4. \uba3c\uc800 \uc124\uce58\ud558\uc138\uc694.",
        "zh": "venv \u6a21\u5757\u9700\u8981 python3-venv \u6216 python3.13-venv \u5305\u3002\u8bf7\u5148\u5b89\u88c5\u3002",
    },
    "cc_warn": {
        "en": "WARNING: No C compiler found. Some packages may need compilation. Install build-essential or gcc.",
        "it": "ATTENZIONE: Nessun compilatore C trovato. Alcuni pacchetti potrebbero richiedere compilazione. Installa build-essential o gcc.",
        "de": "WARNUNG: Kein C-Compiler gefunden. Einige Pakete benoetigen moeglicherweise Kompilierung. Installieren Sie build-essential oder gcc.",
        "fr": "ATTENTION: Aucun compilateur C trouve. Certains paquets peuvent necessiter une compilation. Installez build-essential ou gcc.",
        "es": "ATENCION: No se encontro compilador C. Algunos paquetes pueden necesitar compilacion. Instala build-essential o gcc.",
        "pt": "ATENCAO: Nenhum compilador C encontrado. Alguns pacotes podem precisar de compilacao. Instale build-essential ou gcc.",
        "ja": "\u8b66\u544a: C\u30b3\u30f3\u30d1\u30a4\u30e9\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\u4e00\u90e8\u306e\u30d1\u30c3\u30b1\u30fc\u30b8\u306f\u30b3\u30f3\u30d1\u30a4\u30eb\u304c\u5fc5\u8981\u3067\u3059\u3002build-essential\u307e\u305f\u306fgcc\u3092\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u3057\u3066\u304f\u3060\u3055\u3044\u3002",
        "ko": "\uacbd\uace0: C \ucef4\ud30c\uc77c\ub7ec\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uc77c\ubd80 \ud328\ud0a4\uc9c0\ub294 \ucef4\ud30c\uc77c\uc774 \ud544\uc694\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4. build-essential \ub610\ub294 gcc\ub97c \uc124\uce58\ud558\uc138\uc694.",
        "zh": "\u8b66\u544a: \u672a\u627e\u5230 C \u7f16\u8bd1\u5668\u3002\u67d0\u4e9b\u5305\u53ef\u80fd\u9700\u8981\u7f16\u8bd1\u3002\u8bf7\u5b89\u88c5 build-essential \u6216 gcc\u3002",
    },
    "venv_pip_upgrade": {
        "en": "Upgrading pip in venv...",
        "it": "Aggiornamento pip nel venv...",
        "de": "Pip im venv wird aktualisiert...",
        "fr": "Mise a jour de pip dans le venv...",
        "es": "Actualizando pip en el venv...",
        "pt": "A atualizar pip no venv...",
        "ja": "venv内のpipをアップグレード中...",
        "ko": "venv에서 pip 업그레이드 중...",
        "zh": "升级venv中的pip...",
    },
    "pip_preinstall": {
        "en": "Pre-installing numpy (avoids dependency conflicts)...",
        "it": "Pre-installazione numpy (evita conflitti di dipendenze)...",
        "de": "Vorabinstallation von numpy (vermeidet Abhangigkeitskonflikte)...",
        "fr": "Pre-installation de numpy (evite les conflits de dependances)...",
        "es": "Pre-instalando numpy (evita conflictos de dependencias)...",
        "pt": "Pre-instalando numpy (evita conflitos de dependencias)...",
        "ja": "numpyを事前インストール中（依存関係の競合を回避）...",
        "ko": "numpy 사전 설치 중 (의존성 충돌 방지)...",
        "zh": "预安装 numpy（避免依赖冲突）...",
    },
    "pip_running": {
        "en": "Running: pip install -r requirements.txt (in venv)",
        "it": "Esecuzione: pip install -r requirements.txt (nel venv)",
        "de": "Ausfuhrung: pip install -r requirements.txt (im venv)",
        "fr": "Execution: pip install -r requirements.txt (dans le venv)",
        "es": "Ejecutando: pip install -r requirements.txt (en venv)",
        "pt": "A executar: pip install -r requirements.txt (no venv)",
        "ja": "実行中: pip install -r requirements.txt (venv内)",
        "ko": "실행 중: pip install -r requirements.txt (venv 내)",
        "zh": "运行: pip install -r requirements.txt (venv中)",
    },
    "pip_wait": {
        "en": "(may take several minutes, especially torch...)",
        "it": "(puo richiedere diversi minuti, specialmente torch...)",
        "de": "(kann mehrere Minuten dauern, besonders torch...)",
        "fr": "(peut prendre plusieurs minutes, surtout torch...)",
        "es": "(puede tardar varios minutos, especialmente torch...)",
        "pt": "(pode demorar varios minutos, especialmente torch...)",
        "ja": "(特にtorchのインストールに数分かかることがあります...)",
        "ko": "(특히 torch 설치에 몇 분이 걸릴 수 있습니다...)",
        "zh": "(可能需要几分钟，特别是torch...)",
    },
    "pip_warn": {
        "en": "Warning: pip reported errors. Please check manually.",
        "it": "Attenzione: pip ha riportato errori. Verifica manualmente.",
        "de": "Warnung: pip hat Fehler gemeldet. Bitte manuell prufen.",
        "fr": "Attention: pip a signale des erreurs. Verifiez manuellement.",
        "es": "Atencion: pip ha reportado errores. Verifica manualmente.",
        "pt": "Atencao: o pip reportou erros. Verifique manualmente.",
        "ja": "警告: pipがエラーを報告しました。手動で確認してください。",
        "ko": "경고: pip에서 오류를 보고했습니다. 수동으로 확인하세요.",
        "zh": "警告: pip报告了错误。请手动检查。",
    },
    "pip_fatal": {
        "en": "FATAL: pip installation failed. Cannot continue.",
        "it": "FATALE: installazione pip fallita. Impossibile continuare.",
        "de": "FATAL: pip-Installation fehlgeschlagen. Kann nicht fortfahren.",
        "fr": "FATAL: l'installation pip a echoue. Impossible de continuer.",
        "es": "FATAL: instalacion pip fallida. No se puede continuar.",
        "pt": "FATAL: instalacao pip falhou. Nao e possivel continuar.",
        "ja": "致命的: pipのインストールに失敗しました。続行できません。",
        "ko": "치명적: pip 설치에 실패했습니다. 계속할 수 없습니다.",
        "zh": "致命: pip安装失败。无法继续。",
    },
    "pip_ok_full": {
        "en": "Dependencies installed — OK",
        "it": "Dipendenze installate — OK",
        "de": "Abhangigkeiten installiert — OK",
        "fr": "Dependances installees — OK",
        "es": "Dependencias instaladas — OK",
        "pt": "Dependencias instaladas — OK",
        "ja": "依存関係がインストールされました — OK",
        "ko": "종속성이 설치되었습니다 — OK",
        "zh": "依赖已安装 — OK",
    },
    "step_postcheck": {
        "en": "Verifying installed packages",
        "it": "Verifica pacchetti installati",
        "de": "Uberprufung installierter Pakete",
        "fr": "Verification des paquets installes",
        "es": "Verificando paquetes instalados",
        "pt": "Verificando pacotes instalados",
        "ja": "インストールされたパッケージを確認中",
        "ko": "설치된 패키지 확인 중",
        "zh": "验证已安装的包",
    },
    "check_header_pkg": {
        "en": "Package",
        "it": "Pacchetto",
        "de": "Paket",
        "fr": "Paquet",
        "es": "Paquete",
        "pt": "Pacote",
        "ja": "パッケージ",
        "ko": "패키지",
        "zh": "包",
    },
    "check_header_ver": {
        "en": "Version",
        "it": "Versione",
        "de": "Version",
        "fr": "Version",
        "es": "Version",
        "pt": "Versao",
        "ja": "バージョン",
        "ko": "버전",
        "zh": "版本",
    },
    "check_header_st": {
        "en": "Status",
        "it": "Stato",
        "de": "Status",
        "fr": "Statut",
        "es": "Estado",
        "pt": "Estado",
        "ja": "状態",
        "ko": "상태",
        "zh": "状态",
    },
    "req_not_found": {
        "en": "requirements.txt not found, skipping pip install.",
        "it": "requirements.txt non trovato, salto installazione pip.",
        "de": "requirements.txt nicht gefunden, pip-Installation ubersprungen.",
        "fr": "requirements.txt introuvable, installation pip ignoree.",
        "es": "requirements.txt no encontrado, omitiendo instalacion pip.",
        "pt": "requirements.txt nao encontrado, a saltar instalacao pip.",
        "ja": "requirements.txtが見つかりません。pipインストールをスキップします。",
        "ko": "requirements.txt를 찾을 수 없습니다. pip 설치를 건너뜁니다.",
        "zh": "未找到requirements.txt，跳过pip安装。",
    },
    "settings_ok": {
        "en": "settings.ini created — OK",
        "it": "settings.ini creato — OK",
        "de": "settings.ini erstellt — OK",
        "fr": "settings.ini cree — OK",
        "es": "settings.ini creado — OK",
        "pt": "settings.ini criado — OK",
        "ja": "settings.iniが作成されました — OK",
        "ko": "settings.ini가 생성되었습니다 — OK",
        "zh": "settings.ini已创建 — OK",
    },
    "launcher_ok": {
        "en": "Launcher created: {0} — OK",
        "it": "Lanciatore creato: {0} — OK",
        "de": "Starter erstellt: {0} — OK",
        "fr": "Lanceur cree: {0} — OK",
        "es": "Lanzador creado: {0} — OK",
        "pt": "Lancador criado: {0} — OK",
        "ja": "ランチャーが作成されました: {0} — OK",
        "ko": "런처가 생성되었습니다: {0} — OK",
        "zh": "启动器已创建: {0} — OK",
    },

    # -- Free text
    "req_field": {
        "en": "Required field, try again.",
        "it": "Campo obbligatorio, riprova.",
        "de": "Pflichtfeld, bitte erneut versuchen.",
        "fr": "Champ obligatoire, reessayez.",
        "es": "Campo obligatorio, intenta de nuevo.",
        "pt": "Campo obrigatorio, tente novamente.",
        "ja": "必須フィールドです。再試行してください。",
        "ko": "필수 필드입니다. 다시 시도하세요.",
        "zh": "必填字段，请重试。",
    },
    "invalid_choice": {
        "en": "Invalid choice. Options: {0}",
        "it": "Scelta non valida. Opzioni: {0}",
        "de": "Ungultige Auswahl. Optionen: {0}",
        "fr": "Choix invalide. Options: {0}",
        "es": "Opcion no valida. Opciones: {0}",
        "pt": "Escolha invalida. Opcoes: {0}",
        "ja": "無効な選択です。オプション: {0}",
        "ko": "잘못된 선택입니다. 옵션: {0}",
        "zh": "无效选择。选项: {0}",
    },
    "cancelled": {
        "en": "Installation cancelled.",
        "it": "Installazione annullata.",
        "de": "Installation abgebrochen.",
        "fr": "Installation annulee.",
        "es": "Instalacion cancelada.",
        "pt": "Instalacao cancelada.",
        "ja": "インストールがキャンセルされました。",
        "ko": "설치가 취소되었습니다.",
        "zh": "安装已取消。",
    },
    "cmd_not_found": {
        "en": "Command not found: {0}",
        "it": "Comando non trovato: {0}",
        "de": "Befehl nicht gefunden: {0}",
        "fr": "Commande introuvable: {0}",
        "es": "Comando no encontrado: {0}",
        "pt": "Comando nao encontrado: {0}",
        "ja": "コマンドが見つかりません: {0}",
        "ko": "명령을 찾을 수 없습니다: {0}",
        "zh": "命令未找到: {0}",
    },

    # -- yes/no
    "yes": {"it": "s", "en": "y", "de": "j", "fr": "o", "es": "s", "pt": "s", "ja": "y", "ko": "y", "zh": "y"},
    "no": {"it": "n", "en": "n", "de": "n", "fr": "n", "es": "n", "pt": "n", "ja": "n", "ko": "n", "zh": "n"},

    # -- Summary
    "summary_done": {
        "en": "Installation complete!",
        "it": "Installazione completata!",
        "de": "Installation abgeschlossen!",
        "fr": "Installation terminee!",
        "es": "Instalacion completada!",
        "pt": "Instalacao concluida!",
        "ja": "インストールが完了しました！",
        "ko": "설치가 완료되었습니다!",
        "zh": "安装完成！",
    },
    "summary_folder": {
        "en": "Folder:       {0}",
        "it": "Cartella:       {0}",
    },
    "summary_lang": {
        "en": "Language:     {0}",
        "it": "Lingua:         {0}",
    },
    "summary_wake": {
        "en": "Wake word:    {0}",
        "it": "Wake word:      {0}",
    },
    "summary_model": {
        "en": "Model:        {0}",
        "it": "Modello:        {0}",
    },
    "summary_url": {
        "en": "AI server:    {0}",
        "it": "Server AI:      {0}",
    },
    "summary_whisper": {
        "en": "Whisper:      {0}",
        "it": "Whisper:        {0}",
    },
    "summary_howto": {
        "en": "To start VASS:",
        "it": "Per avviare VASS:",
        "de": "Zum Starten von VASS:",
        "fr": "Pour demarrer VASS:",
        "es": "Para iniciar VASS:",
        "pt": "Para iniciar o VASS:",
        "ja": "VASSを起動するには:",
        "ko": "VASS를 시작하려면:",
        "zh": "启动VASS:",
    },
    "summary_howto_launcher": {
        "en": "double-click {0}",
        "it": "doppio clic su {0}",
        "de": "Doppelklick auf {0}",
        "fr": "double-cliquez sur {0}",
        "es": "doble clic en {0}",
        "pt": "clique duas vezes em {0}",
        "ja": "{0}をダブルクリック",
        "ko": "{0}을(를) 더블클릭",
        "zh": "双击 {0}",
    },
    "summary_howto_terminal": {
        "en": "or from terminal:",
        "it": "oppure da terminale:",
        "de": "oder vom Terminal:",
        "fr": "ou depuis le terminal:",
        "es": "o desde la terminal:",
        "pt": "ou do terminal:",
        "ja": "またはターミナルから:",
        "ko": "또는 터미널에서:",
        "zh": "或从终端:",
    },
    "summary_note": {
        "en": "NOTE:",
        "it": "NOTA BENE:",
        "de": "HINWEIS:",
        "fr": "REMARQUE:",
        "es": "NOTA:",
        "pt": "NOTA:",
        "ja": "注意:",
        "ko": "참고:",
        "zh": "注意:",
    },
    "summary_note_server": {
        "en": "- An OpenAI-compatible server must be running at {0}",
        "it": "- Serve un server OpenAI-compatibile in esecuzione su {0}",
        "de": "- Ein OpenAI-kompatibler Server muss unter {0} laufen",
        "fr": "- Un serveur compatible OpenAI doit etre en cours d'execution sur {0}",
        "es": "- Un servidor compatible OpenAI debe estar ejecutandose en {0}",
        "pt": "- Um servidor compativel OpenAI deve estar em execucao em {0}",
        "ja": "- OpenAI互換サーバーが {0} で実行されている必要があります",
        "ko": "- OpenAI 호환 서버가 {0}에서 실행 중이어야 합니다",
        "zh": "- OpenAI兼容服务器必须在 {0} 运行",
    },
    "summary_note_llama": {
        "en": "- Or install and run llama.cpp separately",
        "it": "- In alternativa, installa e avvia llama.cpp separatamente",
        "de": "- Oder installieren und starten Sie llama.cpp separat",
        "fr": "- Ou installez et lancez llama.cpp separement",
        "es": "- O instala y ejecuta llama.cpp por separado",
        "pt": "- Ou instale e execute o llama.cpp separadamente",
        "ja": "- またはllama.cppを別途インストールして実行してください",
        "ko": "- 또는 llama.cpp를 별도로 설치하고 실행하세요",
        "zh": "- 或者单独安装并运行llama.cpp",
    },
    "summary_note_models": {
        "en": "- TTS (Kokoro) and STT (Whisper) models download automatically",
        "it": "- I modelli TTS (Kokoro) e STT (Whisper) si scaricano",
        "de": "- TTS- (Kokoro) und STT-Modelle (Whisper) werden automatisch heruntergeladen",
        "fr": "- Les modeles TTS (Kokoro) et STT (Whisper) se telechargent automatiquement",
        "es": "- Los modelos TTS (Kokoro) y STT (Whisper) se descargan automaticamente",
        "pt": "- Os modelos TTS (Kokoro) e STT (Whisper) sao descarregados automaticamente",
        "ja": "- TTS (Kokoro) と STT (Whisper) モデルは自動的にダウンロードされます",
        "ko": "- TTS (Kokoro) 및 STT (Whisper) 모델이 자동으로 다운로드됩니다",
        "zh": "- TTS (Kokoro) 和 STT (Whisper) 模型自动下载",
    },
    "summary_note_models2": {
        "en": "  from HuggingFace on first launch (~2-4 GB)",
        "it": "  automaticamente da HuggingFace al primo avvio (~2-4 GB)",
        "de": "  von HuggingFace beim ersten Start (~2-4 GB)",
        "fr": "  depuis HuggingFace au premier lancement (~2-4 Go)",
        "es": "  desde HuggingFace en el primer inicio (~2-4 GB)",
        "pt": "  do HuggingFace no primeiro arranque (~2-4 GB)",
        "ja": "  初回起動時にHuggingFaceから (~2-4 GB)",
        "ko": "  첫 실행 시 HuggingFace에서 (~2-4 GB)",
        "zh": "  首次启动时从HuggingFace下载 (~2-4 GB)",
    },
    "summary_note_config": {
        "en": "- For advanced settings, edit {0}",
        "it": "- Per configurazioni avanzate, modifica {0}",
        "de": "- Fur erweiterte Einstellungen bearbeiten Sie {0}",
        "fr": "- Pour les parametres avances, modifiez {0}",
        "es": "- Para configuracion avanzada, edita {0}",
        "pt": "- Para configuracoes avancadas, edite {0}",
        "ja": "- 詳細設定は {0} を編集してください",
        "ko": "- 고급 설정은 {0}을(를) 편집하세요",
        "zh": "- 高级设置请编辑 {0}",
    },
    "summary_enjoy": {
        "en": "Enjoy VASS!",
        "it": "Buon divertimento con VASS!",
        "de": "Viel Spass mit VASS!",
        "fr": "Amusez-vous avec VASS!",
        "es": "Disfruta de VASS!",
        "pt": "Divirta-se com o VASS!",
        "ja": "VASSをお楽しみください！",
        "ko": "VASS를 즐겨보세요!",
        "zh": "享受VASS！",
    },
    "summary_playwright": {
        "en": "- Run '.venv\\Scripts\\playwright install chromium' to enable web search/fetch",
        "it": "- Esegui '.venv\\Scripts\\playwright install chromium' per abilitare web search/fetch",
        "de": "- Fuhren Sie '.venv\\Scripts\\playwright install chromium' aus fur Websuche/-abruf",
        "fr": "- Lancez '.venv\\Scripts\\playwright install chromium' pour la recherche web",
        "es": "- Ejecuta '.venv\\Scripts\\playwright install chromium' para busqueda web",
        "pt": "- Execute '.venv\\Scripts\\playwright install chromium' para pesquisa web",
        "ja": "- '.venv\\Scripts\\playwright install chromium' を実行してウェブ検索を有効化",
        "ko": "- '.venv\\Scripts\\playwright install chromium' 실행으로 웹 검색 활성화",
        "zh": "- 运行 '.venv\\Scripts\\playwright install chromium' 启用网页搜索",
    },
    "summary_playwright2": {
        "en": "  (downloads ~150 MB, only needed once)",
        "it": "  (scarica ~150 MB, necessario solo una volta)",
        "de": "  (ladt ~150 MB herunter, nur einmal notwendig)",
        "fr": "  (telecharge ~150 Mo, une seule fois necessaire)",
        "es": "  (descarga ~150 MB, solo necesario una vez)",
        "pt": "  (descarrega ~150 MB, apenas necessario uma vez)",
        "ja": "  (~150MBダウンロード、一度だけ必要)",
        "ko": "  (~150MB 다운로드, 한 번만 필요)",
        "zh": "  (下载约150MB，仅需一次)",
    },
    "system_win": {
        "en": "System: Windows",
        "it": "Sistema: Windows",
    },
    "system_mac": {
        "en": "System: macOS",
        "it": "Sistema: macOS",
    },
    "system_linux": {
        "en": "System: Linux",
        "it": "Sistema: Linux",
    },
}


def _(key: str, *args) -> str:
    entry = _T.get(key, {})
    text = entry.get(LANG) or entry.get("en", key)
    if args:
        text = text.format(*args)
    return text


def title(text: str):
    print(f"\n{C_BOLD}{C_CYAN}{'═' * 60}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}  {text}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}{'═' * 60}{C_RESET}\n")


def step(n: int, text: str):
    print(f"\n{C_BOLD}{C_GREEN}[{n}/9]{C_RESET} {text}")


def venv_python(dest: Path) -> str:
    if sys.platform == "win32":
        return str(dest / ".venv" / "Scripts" / "python.exe")
    return str(dest / ".venv" / "bin" / "python")


def venv_pip(dest: Path) -> list[str]:
    return [venv_python(dest), "-m", "pip"]


def _verify_imports(dest: Path):
    """Verify that key packages are importable in the destination venv."""
    pkgs = [
        ("sounddevice", "sounddevice"), ("numpy", "numpy"), ("torch", "torch"),
        ("kokoro", "kokoro"), ("faster-whisper", "faster_whisper"),
        ("webrtcvad", "webrtcvad"), ("soundfile", "soundfile"), ("openai", "openai"),
        ("mcp", "mcp"), ("keyring", "keyring"), ("pynput", "pynput"),
        ("Pillow", "PIL"), ("httpx", "httpx"), ("beautifulsoup4", "bs4"),
        ("lxml", "lxml"), ("PyYAML", "yaml"), ("structlog", "structlog"),
        ("uvicorn", "uvicorn"), ("mss", "mss"), ("easyocr", "easyocr"),
        ("psutil", "psutil"), ("misaki", "misaki"), ("fugashi", "fugashi"),
        ("unidic-lite", "unidic_lite"), ("jaconv", "jaconv"),
        ("mojimoji", "mojimoji"), ("pypinyin", "pypinyin"),
        ("ordered-set", "ordered_set"), ("jieba", "jieba"),
        ("cn2an", "cn2an"), ("dateparser", "dateparser"),
        ("playwright", "playwright"), ("PyAutoGUI", "pyautogui"),
        ("pyperclip", "pyperclip"), ("spacy", "spacy"),
        ("cryptography", "cryptography"),
        ("google-auth-oauthlib", "google_auth_oauthlib"),
        ("google-api-python-client", "googleapiclient"),
        ("PySide6", "PySide6"),
    ]
    py = venv_python(dest)
    results = []
    for pkg_name, import_name in pkgs:
        code = f"import {import_name}; v = getattr({import_name}, '__version__', '?'); print(v, end='')"
        try:
            kwargs = dict(capture_output=True, text=True, timeout=30)
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            r = subprocess.run([py, "-c", code], **kwargs)
            ok = r.returncode == 0
            ver = r.stdout.strip() if ok else "?"
        except Exception:
            ok = False
            ver = "?"
        results.append((pkg_name, ver, ok))
    w_pkg = max(len(r[0]) for r in results) + 2
    w_ver = max(10, max(len(r[1]) for r in results) + 2)
    w_st = len(_('check_header_st')) + 4
    print(f"\n  {C_BOLD}{_('step_postcheck')}{C_RESET}\n")
    print(f"  ╔{'═' * w_pkg}╤{'═' * w_ver}╤{'═' * w_st}╗")
    print(f"  ║ {_('check_header_pkg'):<{w_pkg - 2}} │ {_('check_header_ver'):<{w_ver - 2}} │ {_('check_header_st'):^{w_st - 2}} ║")
    print(f"  ╠{'═' * w_pkg}╪{'═' * w_ver}╪{'═' * w_st}╣")
    for pkg_name, ver, ok in results:
        symbol = f"{C_GREEN}✓{C_RESET}" if ok else f"{C_RED}✗{C_RESET}"
        plain = "✓" if ok else "✗"
        pad = (w_st - 2 - len(plain)) // 2
        lhs = ' ' * pad
        rhs = ' ' * (w_st - 2 - len(plain) - pad)
        print(f"  ║ {pkg_name:<{w_pkg - 2}} │ {ver:<{w_ver - 2}} │ {lhs}{symbol}{rhs} ║")
    print(f"  ╚{'═' * w_pkg}╧{'═' * w_ver}╧{'═' * w_st}╝")
    ok_count = sum(1 for _, _, o in results if o)
    total = len(results)
    color = C_GREEN if ok_count == total else C_RED
    print(f"  {color}{ok_count}/{total} packages OK{C_RESET}\n")
    return results


_UNSET = object()


def ask(text: str, default: object = _UNSET, choices: list | None = None) -> str:
    if default is not _UNSET and str(default) and choices is None:
        prompt = f"  {text} {C_DIM}[{default}]{C_RESET}: "
    elif choices:
        opts = " / ".join(choices)
        prompt = f"  {text} {C_DIM}[{opts}]{C_RESET}: "
    else:
        prompt = f"  {text}: "
    while True:
        try:
            answer = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n{_('cancelled')}")
            sys.exit(0)
        if not answer and default is not _UNSET:
            return str(default)
        if not answer and default is _UNSET:
            print(f"  {C_YELLOW}{_('req_field')}{C_RESET}")
            continue
        if choices and answer.lower() not in [c.lower() for c in choices]:
            print(f"  {C_YELLOW}{_('invalid_choice', ', '.join(choices))}{C_RESET}")
            continue
        return answer


def run(cmd: list[str], cwd=None, show=False) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if show:
            print(r.stdout, end="")
            if r.stderr:
                print(r.stderr, end="", file=sys.stderr)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", _("cmd_not_found", cmd[0])


def copy_tree_filtered(src: Path, dst: Path):
    """Copy project files selectively, excluding dev/backup/generated data."""
    exclude_patterns = {
        "bk", ".opencode", ".git", "__pycache__",
        ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    }
    exclude_suffixes = {".log", ".onnx", ".zip", ".pyc"}
    exclude_paths = {
        "Allowed_root/memory",
        "Allowed_root/memory.json",
        "Allowed_root/events.json",
        "Allowed_root/schedule.json",
        "Allowed_root/last_response.txt",
        "mcp_server/LOG",
        "config/commands.ini",
        "config/settings.ini",
        "bump.py",
        "google_client_secret.json",
    }
    copied = 0
    total = 0

    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        parts = rel.parts

        if parts[0] in exclude_patterns or parts[0].startswith("."):
            continue
        if any(p.startswith("__pycache__") for p in parts):
            continue
        if item.suffix in exclude_suffixes:
            continue
        rel_str = str(rel).replace("\\", "/")
        if any(rel_str.startswith(ep) or rel_str == ep for ep in exclude_paths):
            continue

        total += 1
        dest = dst / rel

        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied += 1
            if copied % 10 == 0:
                print(f"\r  {_('copy_progress', copied)}", end="")
    print(f"\r  {_('copy_done', copied, total)}")
    return copied


def main():
    global LANG

    title("VASS — Installation Wizard")

    # Step 0: Language selection (always first)
    step(1, "Language / Lingua")
    for lc in _lang_choices:
        print(f"    {C_BOLD}{lc}{C_RESET} = {_lang_names[lc]}")
    print()
    lang_choice = ask(_("q_lang"), "en", _lang_choices)
    LANG = lang_choice

    print(f"\n  {_('welcome_body')}")
    print(f"  {_('welcome_reqs')}\n")
    ask(_("press_enter"), "ok")

    # ── STEP 1: Prerequisites ────────────────────────────────────────────────
    step(2, _("step_prereq"))

    py_ver = sys.version_info
    if py_ver < (3, 13):
        print(f"  {C_RED}{_('py_err', py_ver.major, py_ver.minor)}{C_RESET}")
        sys.exit(1)
    print(f"  {C_GREEN}{_('py_ok', py_ver.major, py_ver.minor, py_ver.micro)}{C_RESET}")

    pip_ok = False
    for pip_cmd in ([sys.executable, "-m", "pip", "--version"],
                    ["pip3", "--version"],
                    ["pip", "--version"]):
        rc, _out, _err = run(pip_cmd)
        if rc == 0:
            pip_ok = True
            break
    if not pip_ok:
        print(f"  {C_RED}{_('pip_err')}{C_RESET}")
        sys.exit(1)
    print(f"  {C_GREEN}{_('pip_ok')}{C_RESET}")

    if sys.platform != "win32":
        cc_ok = False
        for cc in ["cc", "gcc", "clang"]:
            rc, _out, _err = run([cc, "--version"])
            if rc == 0:
                cc_ok = True
                break
        if not cc_ok:
            print(f"  {C_YELLOW}{_('cc_warn')}{C_RESET}")

    if sys.platform == "win32":
        print(f"  {C_DIM}{_('system_win')}{C_RESET}")
    elif sys.platform == "darwin":
        print(f"  {C_DIM}{_('system_mac')}{C_RESET}")
    else:
        print(f"  {C_DIM}{_('system_linux')}{C_RESET}")

    # ── STEP 2: Destination folder ───────────────────────────────────────────
    step(3, _("step_dest"))

    if sys.platform == "win32":
        default_dest = str(Path.home() / "VASS")
    else:
        default_dest = str(Path.home() / "vass")

    dest_str = ask(_("q_dest"), default_dest)
    dest = Path(dest_str).resolve()

    if dest.exists() and any(dest.iterdir()):
        y, n = _("yes"), _("no")
        overwrite = ask(f"  {_('q_overwrite')}", n, [y, n])
        if overwrite.lower() == n.lower():
            print(f"  {_('cancelled')}")
            sys.exit(0)
    dest.mkdir(parents=True, exist_ok=True)
    print(f"  {_('dest', dest)}")

    # ── STEP 3: Configuration parameters ─────────────────────────────────────
    step(4, _("step_config"))

    wake = ask(_("q_wake"), "erika")
    model = ask(_("q_model"), "Qwen3-8B-Q4_K_M")
    url = ask(_("q_url"), "http://127.0.0.1:8080/v1")
    api_key = ask(_("q_apikey"), "")
    whisper_model = ask(_("q_whisper"), "medium", ["tiny", "base", "small", "medium"])
    system_msg = ask(_("q_sysmsg"), _("default_sysmsg"))

    # ── STEP 4: Copy files ───────────────────────────────────────────────────
    step(5, _("step_copy"))

    src = Path(__file__).resolve().parent
    print(f"  {_('source', src)}")
    copy_tree_filtered(src, dest)

    (dest / "Allowed_root" / "memory").mkdir(parents=True, exist_ok=True)
    (dest / "Allowed_root" / "memory" / "archive").mkdir(parents=True, exist_ok=True)
    (dest / "scripts").mkdir(parents=True, exist_ok=True)
    (dest / "sounds").mkdir(parents=True, exist_ok=True)
    (dest / "config").mkdir(parents=True, exist_ok=True)
    (dest / "mcp_server" / "LOG").mkdir(parents=True, exist_ok=True)

    # ── STEP 5: Create virtual environment ───────────────────────────────────
    step(6, _("step_venv"))

    venv_dir = dest / ".venv"
    print(f"  {_('venv_creating', venv_dir)}")
    rc, _out, stderr = run([sys.executable, "-m", "venv", str(venv_dir)])
    if rc != 0:
        if "ensurepip" in stderr.lower() or "ensurepip" in _out.lower():
            print(f"  {C_RED}{_('venv_fail_ensurepip')}{C_RESET}")
        else:
            print(f"  {C_RED}{_('venv_fail')}{C_RESET}\n{stderr[:500]}")
        sys.exit(1)
    print(f"  {C_GREEN}{_('venv_ok')}{C_RESET}")

    print(f"  {_('venv_pip_upgrade')}")
    run(venv_pip(dest) + ["install", "--upgrade", "pip"], show=False)

    # ── STEP 6: Install dependencies ─────────────────────────────────────────
    step(7, _("step_pip"))

    req_file = dest / "requirements.txt"
    if not req_file.exists():
        print(f"  {C_YELLOW}{_('req_not_found')}{C_RESET}")
    else:
        print(f"  {_('pip_preinstall')}")
        pre_cmds = [("numpy", "numpy")]
        extra_opts = [[]]
        rcs = []
        for (pkg_label, pkg_spec), opts in zip(pre_cmds, extra_opts):
            rc, _out, _err = run(venv_pip(dest) + ["install", pkg_spec] + opts, cwd=str(dest), show=False)
            rcs.append((pkg_label, pkg_spec, rc, opts))
        failed = [(l, s, r, o) for l, s, r, o in rcs if r != 0]
        if failed:
            print(f"\n  {C_RED}{_('pip_fatal')}{C_RESET}")
            for pkg_label, pkg_spec, rcode, opts in failed:
                print(f"  {C_RED}{pkg_label}: exit code {rcode}, retrying with output:{C_RESET}")
                run(venv_pip(dest) + ["install", pkg_spec] + opts, cwd=str(dest), show=True)
            _verify_imports(dest)
            sys.exit(1)
        print(f"  {_('pip_running')}")
        print(f"  {C_DIM}{_('pip_wait')}{C_RESET}\n")
        rc, _out, stderr = run(venv_pip(dest) + ["install", "-r", str(req_file), "--ignore-requires-python"], cwd=str(dest), show=True)
        if rc != 0:
            print(f"\n  {C_RED}{_('pip_fatal')}{C_RESET}")
            if stderr:
                print(stderr[:500])
            _verify_imports(dest)
            sys.exit(1)
        else:
            print(f"\n  {C_GREEN}{_('pip_ok_full')}{C_RESET}")
            _verify_imports(dest)

    # ── STEP 7: Generate settings.ini ────────────────────────────────────────
    step(8, _("step_settings"))

    cfg = configparser.ConfigParser()
    cfg["locale"] = {"language": LANG}
    cfg["gui"] = {
        "lastmode": "c",
        "x": "100", "y": "100", "width": "200", "height": "32",
        "font_family": "Segoe UI" if sys.platform == "win32" else "sans-serif",
        "font_size": "10",
    }
    cfg["wakeword"] = {"wakeword": wake, "sensitivity": "0.005"}
    cfg["commands"] = {"similarity": "0.6", "word_learning_enabled": "false"}
    cfg["tts"] = {"tts_engine": "kokoro", "volume": "0.50"}
    cfg["ai"] = {
        "url": url,
        "model": model,
        "api_key": api_key,
        "system_message": system_msg,
        "mcp_server_url": "http://localhost:9988",
        "memory_tokens": "4000",
        "blacklist": "Amara.org,QTTS",
        "allow_ai_scripts": "false",
        "context_length": "0",
        "overflow_strategy": "truncate",
    }
    cfg["llamacpp"] = {
        "llama_server_path": str(dest / "llamacpp"),
        "llama_server_working_directory": "",
        "llama_server_arguments": (
            "--models-dir .\\models -b 4096 --cache-type-k q8_0 --cache-type-v q8_0 "
            "--offline --prio 2 -rea off -ngl -1 --no-mmap -t 12 --models-max 1 "
            "--flash-attn on --cache-ram 4096 -c 10240 --cont-batching "
            "--sleep-idle-seconds 600 --timeout 36000"
        ),
        "llama_autostart": "false",
    }
    cfg["resources"] = {
        "cpu_max": "75", "ram_max": "99", "gpu_max": "75",
        "vram_max": "99", "resource_timeout": "10",
    }
    cfg["events"] = {"reminder_advance": "3600"}
    cfg["noise"] = {"noise_pause": "false", "noise_pause_threshold": "0.002", "noise_pause_duration": "30"}

    settings_path = dest / "config" / "settings.ini"
    with open(settings_path, "w", encoding="utf-8") as f:
        cfg.write(f)
    print(f"  {C_GREEN}{_('settings_ok')}{C_RESET}")

    # ── STEP 8: Create launcher ──────────────────────────────────────────────
    step(9, _("step_launcher"))

    if sys.platform == "win32":
        launcher = dest / "vass.bat"
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(f'cd /d "{dest}"\r\n')
            f.write(f'".venv\\Scripts\\pythonw.exe" "vass.py"\r\n')
    elif sys.platform == "darwin":
        launcher = dest / "vass.command"
        with open(launcher, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\n')
            f.write('cd "$(dirname "$0")"\n')
            f.write('exec ".venv/bin/python" vass.py\n')
        os.chmod(launcher, 0o755)
    else:
        launcher = dest / "vass.sh"
        with open(launcher, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\n')
            f.write('cd "$(dirname "$0")"\n')
            f.write('exec ".venv/bin/python" vass.py\n')
        os.chmod(launcher, 0o755)

    print(f"  {C_GREEN}{_('launcher_ok', launcher.name)}{C_RESET}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}{C_CYAN}{'═' * 60}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}  {_('step_summary')}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}{'═' * 60}{C_RESET}\n")

    print(f"  {C_BOLD}{_('summary_done')}{C_RESET}\n")
    print(f"  {_('summary_folder', dest)}")
    print(f"  {_('summary_lang', _lang_names[LANG])}")
    print(f"  {_('summary_wake', wake)}")
    print(f"  {_('summary_model', model)}")
    print(f"  {_('summary_url', url)}")
    print(f"  {_('summary_whisper', whisper_model)}")
    print()
    print(f"  {_('summary_howto')}")
    print(f"    {C_BOLD}{_('summary_howto_launcher', launcher.name)}{C_RESET}")
    print(f"  {_('summary_howto_terminal')}")
    if sys.platform == "win32":
        print(f"    {C_BOLD}cd \"{dest}\"{C_RESET}")
        print(f"    {C_BOLD}.venv\\Scripts\\pythonw vass.py{C_RESET}")
    else:
        print(f"    {C_BOLD}cd \"{dest}\" && .venv/bin/python vass.py{C_RESET}")
    print()
    print(f"  {C_YELLOW}{_('summary_note')}{C_RESET}")
    print(f"  {_('summary_note_server', url)}")
    print(f"  {_('summary_note_llama')}")
    print(f"  {_('summary_note_models')}")
    print(f"  {_('summary_note_models2')}")
    print(f"  {_('summary_note_config', settings_path)}")
    print(f"  {_('summary_playwright')}")
    print(f"  {_('summary_playwright2')}")
    print()
    print(f"  {C_GREEN}{_('summary_enjoy')}{C_RESET}")


if __name__ == "__main__":
    main()
