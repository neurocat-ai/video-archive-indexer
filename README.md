# Video Archive Indexer

Система каталогизации видеоархива с возможностью семантического поиска роликов через Telegram.

## Возможности

- извлечение технических метаданных видео;
- транскрибация речи с помощью Whisper;
- OCR текста с кадров и обложек;
- анализ сцен с помощью Vision;
- сохранение карточек роликов в Google Sheets;
- поиск роликов по смыслу через Telegram.

---

# Структура проекта

```
video_archive_indexer/

├── credentials/
│
├── data/
│   ├── covers/
│   ├── extracted_audio/
│   ├── metadata_normalized/
│   ├── metadata_raw/
│   ├── ocr/
│   ├── ocr_frames/
│   ├── scene_frames/
│   ├── scenes/
│   └── transcripts/
│
├── integrations/
│   ├── __init__.py
│   ├── sheets.py
│   └── telegram_bot.py
│
├── scripts/
│   ├── analyze_scenes.py
│   ├── extract_metadata.py
│   ├── extract_ocr.py
│   └── transcribe_audio.py
│
├── search/
│   ├── __init__.py
│   └── search.py
│
├── .env
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

# Установка

Создать виртуальное окружение:

```bash
python -m venv .venv
```

Активировать виртуальное окружение.

macOS / Linux

```bash
source .venv/bin/activate
```

Windows

```bash
.venv\Scripts\activate
```

Установить зависимости:

```bash
pip install -r requirements.txt
```

---

# Настройка

Переименовать файл

```
.env.example
```

в

```
.env
```

---

## Настройка Google Sheets

1. Создать сервисный аккаунт в Google Cloud.
2. Включить Google Sheets API и Google Drive API.
3. Скачать JSON-ключ сервисного аккаунта.
4. Поместить JSON-файл в папку:

```
credentials/
```

5. Открыть Google Sheets и предоставить сервисному аккаунту доступ к таблице с правами редактора.
6. Заполнить параметры в файле `.env`.

Пример:

```text
# Папки с видео

VIDEO_METADATA_INPUT_PATH=path/to/metadata
VIDEO_TRANSCRIPTION_INPUT_PATH=path/to/transcription
VIDEO_OCR_INPUT_PATH=path/to/ocr
VIDEO_VISION_INPUT_PATH=path/to/vision

# Google Sheets

GOOGLE_CREDENTIALS_FILE=credentials/service-account.json
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_WORKSHEET_NAME=Карточка ролика

# OpenAI

OPENAI_API_KEY=your_openai_api_key

# Telegram

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

---

# Подготовка видеоархива

Рассортировать видео по папкам обработки:

```
metadata/
transcription/
ocr/
vision/
```

При необходимости один и тот же ролик может находиться сразу в нескольких папках.

Указать пути к этим папкам в файле `.env`.

---

# Обработка видео

### Извлечение метаданных

```bash
python scripts/extract_metadata.py
```

### Транскрибация речи

```bash
python scripts/transcribe_audio.py
```

### OCR

```bash
python scripts/extract_ocr.py
```

### Vision-анализ

```bash
python scripts/analyze_scenes.py
```

После выполнения каждого скрипта карточки роликов автоматически обновляются в Google Sheets.

---

# Поиск

Запустить Telegram-бота:

```bash
python -m integrations.telegram_bot
```

После запуска отправить боту запрос в свободной форме.

Примеры:

- Найти ролик про эксперимент Либета
- Найти ролик про клиническую смерть
- Найти ролик, где врач рассказывает о сердце
- Найти ролик про оплодотворение
- Найти ролик, где показано сходство отпечатка пальца и среза дерева

---

# Используемые технологии

- Python
- OpenAI API
- Faster Whisper
- Tesseract OCR
- FFmpeg
- Google Sheets API
- Telegram Bot API