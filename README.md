# TG Oxyfire Saver

macOS app to download Telegram media (video / photo / documents) with a queue, history, channel watchers, clipboard mode, and a menu bar icon.

**[Скачать для Mac (Release)](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)** · **[Download for Mac](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)**

| | |
|---|---|
| Version | **2.3.0** |
| Platform | macOS 12+ |
| Author | Kirill Kovyirshin (Ковыршин Кирилл) © 2016 |
| Links | [3dwolf.ru](https://3dwolf.ru) · [datastore24.ru](https://datastore24.ru) · [myfabric.ru](https://myfabric.ru) |

---

## English

### What it does
- Sign in with your Telegram account (QR or phone) — User API / Telethon
- Download by link, range (`https://t.me/c/ID/100-150`), clipboard, or channel watchers
- Queue + history stay **on your Mac**; menu bar keeps downloads running with the window closed
- UI language: **Russian / English** (Settings → Interface language, default Russian)

### Privacy
Telegram auth is only sent to **official Telegram servers**, like a normal client. Session, settings, and files are **not** uploaded to our servers.

Local data: `~/Library/Application Support/TGVideoSaver/`  
(`tg_saver.session`, `data/tg_saver.db`, thumbs, `app.log`)

### API_ID / API_HASH — do I need my own?
**No.** By default the app uses the **public Telegram Desktop** open-source credentials (`API_ID=2040`). That is the same approach many open-source Telegram clients use. You do **not** register anything on my.telegram.org.

Installer creates  
`~/Library/Application Support/TGVideoSaver/.env`  
from `.env.example` automatically. Only change it if you want your own app keys (optional, advanced).

### Install (Mac app — recommended)
1. Open the latest [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Download `TG-Oxyfire-Saver-macOS.zip`
3. Unzip and run **`Install.command`** (double-click)
4. Open **TG Oxyfire Saver** from Applications
5. Sign in with QR (Telegram → Settings → Devices → Link Desktop Device)
6. If Gatekeeper blocks it: right-click → **Open**

### Build from source
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
bash scripts/install_from_source.sh
```
Requires Python 3.12+ and Xcode CLT (for the menu bar helper).

---

## Русский

### Что делает
- Вход в Telegram от вашего пользователя (QR или номер) — User API / Telethon
- Скачивание по ссылке, диапазону (`https://t.me/c/ID/100-150`), из буфера или через сторожей каналов
- Очередь и история **только на этом Mac**; иконка в menu bar продолжает загрузки при закрытом окне
- Язык интерфейса: **Русский / English** (Настройки → Язык, по умолчанию русский)

### Приватность
Авторизация уходит только на **официальные серверы Telegram**, как в обычном клиенте. Сессию, пароли и файлы мы **нигде не собираем**.

Данные: `~/Library/Application Support/TGVideoSaver/`  
(`tg_saver.session`, `data/tg_saver.db`, превью, `app.log`)

### API_ID / API_HASH — нужно ли регистрировать свои?
**Нет.** По умолчанию используются **публичные ключи Telegram Desktop** из открытого исходного кода (`API_ID=2040`). Так делают многие open-source клиенты. Регистрироваться на my.telegram.org **не нужно**.

Установщик сам создаёт  
`~/Library/Application Support/TGVideoSaver/.env`  
из `.env.example`. Менять файл имеет смысл только если хотите свои ключи приложения (опционально).

### Установка (приложение для Mac — рекомендуется)
1. Откройте последний [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Скачайте `TG-Oxyfire-Saver-macOS.zip`
3. Распакуйте и запустите **`Install.command`**
4. Откройте **TG Oxyfire Saver** из Программ
5. Войдите по QR (Telegram → Настройки → Устройства → Подключить устройство)
6. Если macOS не открывает: ПКМ → **Открыть**

### Сборка из исходников
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
bash scripts/install_from_source.sh
```
Нужны Python 3.12+ и Xcode CLT.

---

## License

MIT — see [LICENSE](LICENSE)
