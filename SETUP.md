# Инструкция по запуску Винни

---

## Где взять CLAUDE_API_KEY

1. Открой [console.anthropic.com](https://console.anthropic.com) и зарегистрируйся (или войди)
2. В левом меню выбери **API Keys**
3. Нажми **Create Key**, дай ключу имя (например `vinnie-assistant`)
4. Скопируй ключ — он показывается только один раз
5. Вставь его в файл `.env` в строку `CLAUDE_API_KEY=...`

> Новым пользователям Anthropic даёт бесплатный кредит ~$5 для тестирования.
> Один голосовой запрос к Винни стоит примерно $0.001–0.003.

---

---

# Раздел 1 — Запуск на macOS

### Что понадобится

| Программа | Проверить | Установить если нет |
|-----------|-----------|---------------------|
| Docker Desktop | `docker --version` | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| Google Chrome | Открыть браузер | [google.com/chrome](https://www.google.com/chrome/) |

---

### Шаг 1 — Скопируй файл с переменными

```bash
cd vinnie-assistant
cp .env.example .env
```

---

### Шаг 2 — Заполни `.env`

Открой файл `.env` в любом редакторе и заполни:

```env
CLAUDE_API_KEY=sk-ant-...       # вставь ключ из console.anthropic.com
JIRA_API_TOKEN=                 # оставь пустым, понадобится позже
JIRA_URL=                       # оставь пустым
JIRA_EMAIL=                     # оставь пустым
WHISPER_MODEL=base              # base — оптимально для старта
OS_TYPE=macos                   # НЕ менять для macOS
DATA_DIR=/data                  # НЕ менять
```

---

### Шаг 3 — Запусти Docker Desktop

Открой приложение Docker Desktop и дождись пока статус станет **Running** (иконка в трее).

---

### Шаг 4 — Собери и запусти контейнер

Команду нужно выполнять из корневой папки проекта `vinnie-assistant/`
(там где лежит файл `docker-compose.yml`):

```bash
cd ~/PycharmProjects/vinnie-assistant
docker-compose up --build
```

**Первый запуск занимает 5–10 минут** — Docker скачивает базовый образ Python,
устанавливает зависимости и загружает модель Whisper (~150 МБ).

Последующие запуски — секунды.

Когда увидишь в терминале:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```
— приложение готово.

---

### Шаг 5 — Открой в браузере

Открой **Google Chrome** (только Chrome — нужен Web Speech API):

```
http://localhost:8000
```

---

### Шаг 6 — Разреши микрофон

При первом открытии Chrome спросит разрешение на использование микрофона.
Нажми **Разрешить**.

---

### Шаг 7 — Используй

1. Скажи **«Привет Винни»**
2. Дождись бипа и надписи *«Запись...»*
3. Скажи, например:
   > *«Делал задачу PROJ-123, потратил полтора часа, сегодня,
   > рефакторинг модуля авторизации»*
4. Нажми кнопку **«Готово»** или подожди 20 секунд
5. Винни ответит голосом и запишет в таблицу

---

### Остановить приложение

```bash
# остановить контейнер
docker-compose down

# или просто Ctrl+C в терминале где запущен docker-compose up
```

---

### Где хранятся данные

Все записи сохраняются в файл `vinnie-assistant/data/worklog.xlsx`.
Файл остаётся на твоём компьютере даже после остановки контейнера.

---

---

# Раздел 2 — Запуск на удалённом сервере Linux

### Архитектура

```
Твой рабочий ПК (Chrome + микрофон)
        │
        │  HTTP / браузер
        ▼
Удалённый Linux-сервер (Docker + Винни)
        │
        └── data/worklog.xlsx  (на сервере)
```

Микрофон работает в браузере на твоём ПК — никаких звуковых устройств
на сервере не требуется.

---

### Что понадобится на сервере

| Программа | Проверить | Установить |
|-----------|-----------|------------|
| Docker | `docker --version` | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | `docker compose version` | входит в Docker >= 23 |
| Git | `git --version` | `apt install git` |

---

### Шаг 1 — Скопируй проект на сервер

**Вариант А — через Git (рекомендуется):**

```bash
git clone <url-твоего-репозитория> vinnie-assistant
cd vinnie-assistant
```

**Вариант Б — через scp с Mac:**

```bash
# выполнить на Mac
scp -r ./vinnie-assistant user@your-server-ip:/home/user/vinnie-assistant
```

---

### Шаг 2 — Создай `.env` на сервере

```bash
cd vinnie-assistant
cp .env.example .env
nano .env   # или vim .env
```

Заполни файл (отличия от macOS выделены ⚠️):

```env
CLAUDE_API_KEY=sk-ant-...       # тот же ключ что и на Mac
JIRA_API_TOKEN=                 # оставь пустым
JIRA_URL=                       # оставь пустым
JIRA_EMAIL=                     # оставь пустым
WHISPER_MODEL=base
OS_TYPE=linux                   # ⚠️ ИЗМЕНИТЬ на linux
DATA_DIR=/data                  # НЕ менять
```

---

### Шаг 3 — Открой порт в файрволе

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 8000/tcp

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8000/tcp && sudo firewall-cmd --reload

# Если сервер в облаке (AWS/GCP/Yandex Cloud) — также открой порт 8000
# в настройках Security Group / правил брандмауэра в личном кабинете
```

---

### Шаг 4 — Собери и запусти контейнер

Команду нужно выполнять из корневой папки проекта `vinnie-assistant/`
(там где лежит файл `docker-compose.linux.yml`):

```bash
cd ~/vinnie-assistant
docker-compose -f docker-compose.linux.yml up --build -d
```

Флаг `-d` запускает контейнер в фоне (detached mode).

Проверить что запустилось:

```bash
docker-compose -f docker-compose.linux.yml logs -f
# Ctrl+C чтобы выйти из просмотра логов
```

---

### Шаг 5 — Открой в браузере на рабочем ПК

Открой **Google Chrome** на своём ПК:

```
http://<ip-адрес-сервера>:8000
```

> Узнать IP сервера: `curl ifconfig.me` (выполни на сервере)

---

### Шаг 6 — Разреши микрофон в Chrome

⚠️ Chrome разрешает микрофон только для `localhost` и HTTPS-адресов.
Для HTTP по IP нужно добавить исключение:

1. В Chrome открой `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. В поле вставь: `http://<ip-сервера>:8000`
3. Нажми **Enable** → **Relaunch**

**Или используй HTTPS** (рекомендуется для постоянного использования):
- Настрой nginx как reverse proxy с SSL-сертификатом Let's Encrypt
- Тогда микрофон будет работать без флагов Chrome

---

### Автозапуск при перезагрузке сервера

```bash
# добавить флаг restart в docker-compose.linux.yml уже стоит (restart: unless-stopped)
# достаточно включить автозапуск Docker
sudo systemctl enable docker
```

---

### Остановить / перезапустить

```bash
# остановить
docker-compose -f docker-compose.linux.yml down

# перезапустить
docker-compose -f docker-compose.linux.yml restart

# обновить код и пересобрать
git pull
docker-compose -f docker-compose.linux.yml up --build -d
```

---

### Где хранятся данные на сервере

```
/home/user/vinnie-assistant/data/worklog.xlsx
```

Скопировать файл на Mac:

```bash
scp user@your-server-ip:/home/user/vinnie-assistant/data/worklog.xlsx ~/Desktop/
```

---

---

# Справочник переменных `.env`

| Переменная | macOS | Linux (сервер) | Описание |
|------------|-------|----------------|----------|
| `CLAUDE_API_KEY` | `sk-ant-...` | `sk-ant-...` | Ключ Claude API — одинаковый везде |
| `OS_TYPE` | `macos` | `linux` | ⚠️ Отличается — влияет на docker-compose |
| `WHISPER_MODEL` | `base` | `base` или `small` | `base` быстрее, `small` точнее для акцентов |
| `DATA_DIR` | `/data` | `/data` | Путь внутри контейнера — не менять |
| `JIRA_API_TOKEN` | *(пусто)* | *(пусто)* | Зарезервировано для следующей итерации |
| `JIRA_URL` | *(пусто)* | *(пусто)* | URL твоего Jira (`https://company.atlassian.net`) |
| `JIRA_EMAIL` | *(пусто)* | *(пусто)* | Email аккаунта Jira |

### Размеры моделей Whisper

| Модель | Размер | Скорость | Качество русского |
|--------|--------|----------|-------------------|
| `tiny` | 75 МБ | очень быстро | удовлетворительно |
| `base` | 145 МБ | быстро | **хорошо (рекомендуется)** |
| `small` | 466 МБ | средне | отлично |
| `medium` | 1.5 ГБ | медленно | превосходно |
