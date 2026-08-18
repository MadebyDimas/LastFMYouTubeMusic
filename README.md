# YouTube Music to Last.fm Scrobbler

Навайбкоженный, легкий серверный скроблер **YouTube Music** для **Last.fm**, работающий в **Docker**.

---

## Возможности

- **Now Playing**: Отправляет статус текущего трека в Last.fm в реальном времени.
- **Защита от дубликатов**: Двойные скробблы полностью исключены благодаря умному контролю истории и локальной БД SQLite.
- **Очистка названий**: Автоматически убирает мусор вроде `(Official Video)`, `[Lyrics]`, `(4K Remastered)`.
- **Порог 20%**: Скробблит трек после прослушивания 20% длительности.

---

## Быстрый старт

### 1. Настройка Last.fm
Скопируйте шаблон конфигурации и укажите ваши ключи и данные аккаунта Last.fm:
```bash
cp .env.example .env
nano .env
```

### 2. Запуск контейнера
Запустите сервис в фоновом режиме:
```bash
docker compose up -d
```

### 3. Подключение YouTube Music
1. Откройте [music.youtube.com](https://music.youtube.com) в браузере и нажмите `F12` &rarr; вкладка **Network (Сеть)**.
2. Включите любой трек, найдите запрос `player` &rarr; **Copy request headers** (или скопируйте строку Cookie).
3. Запустите настройку авторизации в работающем контейнере:
```bash
docker compose exec scrobbler python src/main.py setup-headers
```
4. Вставьте скопированный текст и нажмите `Enter` &rarr; `Ctrl+D`. Файл авторизации автоматически сохранится в `./data/browser.json`.


---

## Управление контейнером

```bash
# Запуск в фоне:
docker compose up -d

# Просмотр логов в реальном времени:
docker compose logs -f

# Перезапуск сервиса:
docker compose restart

# Остановка:
docker compose down
```

---

## Конфигурация (`.env`)

Все параметры хранятся в `.env`, а база данных и сессии в папке `./data`:
- `LASTFM_API_KEY` & `LASTFM_API_SECRET`
- `LASTFM_USERNAME` & `LASTFM_PASSWORD`
- `POLL_INTERVAL=30`
- `SCROBBLE_PERCENTAGE=0.2`
- `CLEAN_TITLES=true`
