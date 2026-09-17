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

### Install (Mac app — recommended)
1. Open the latest [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Download `TG-Oxyfire-Saver-macOS.zip`
3. Unzip and run **`Install.command`** (double-click)
4. Create API credentials at [my.telegram.org](https://my.telegram.org) → API development tools
5. Put `API_ID` and `API_HASH` into  
   `~/Library/Application Support/TGVideoSaver/.env`
6. Open **TG Oxyfire Saver** from Applications (or Desktop after install)
7. If Gatekeeper blocks it: right-click → **Open**

### Build from source
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
bash scripts/install_from_source.sh
```
Requires Python 3.12+, Xcode CLT (for the menu bar helper), and Telegram `API_ID` / `API_HASH`.

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

### Установка (приложение для Mac — рекомендуется)
1. Откройте последний [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Скачайте `TG-Oxyfire-Saver-macOS.zip`
3. Распакуйте и запустите **`Install.command`**
4. Получите ключи на [my.telegram.org](https://my.telegram.org) → API development tools
5. Пропишите `API_ID` и `API_HASH` в  
   `~/Library/Application Support/TGVideoSaver/.env`
6. Запустите **TG Oxyfire Saver** из Программ
7. Если macOS не открывает: ПКМ → **Открыть**

### Сборка из исходников
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
bash scripts/install_from_source.sh
```
Нужны Python 3.12+, Xcode CLT и `API_ID` / `API_HASH` от Telegram.

---

## License

MIT — see [LICENSE](LICENSE)
