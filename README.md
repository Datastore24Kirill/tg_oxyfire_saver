<p align="center">
  <img src="docs/logo.png" alt="TG Oxyfire Saver" width="128" height="128" />
</p>

<h1 align="center">TG Oxyfire Saver</h1>

<p align="center">
Download Telegram media (video / photo / documents) with a queue, history, channel watchers, clipboard mode, and a tray / menu bar icon.
</p>

<p align="center">
  <a href="https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest"><strong>Download Mac</strong></a>
  ·
  <a href="https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest"><strong>Download Windows</strong></a>
  ·
  <a href="https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest"><strong>Скачать Mac / Windows</strong></a>
</p>

| | |
|---|---|
| Version | **2.4.0** |
| Platforms | **macOS 12+** · **Windows 10/11** |
| Author | Kirill Kovyirshin (Ковыршин Кирилл) © 2016 |
| Links | [3dwolf.ru](https://3dwolf.ru) · [datastore24.ru](https://datastore24.ru) · [myfabric.ru](https://myfabric.ru) |

---

## English

### What it does
- Sign in with your Telegram account (QR or phone) — User API / Telethon
- Download by link, range (`https://t.me/c/ID/100-150`), clipboard, or channel watchers
- Queue + history stay **on your computer**; tray / menu bar keeps downloads running with the window closed
- UI language: **Russian / English** (Settings → Interface language, default Russian)

### Privacy
Telegram auth is only sent to **official Telegram servers**, like a normal client. Session, settings, and files are **not** uploaded to our servers.

**Local data**
- macOS: `~/Library/Application Support/TGVideoSaver/`
- Windows: `%APPDATA%\TGVideoSaver\`

### Install — Mac
1. Open the latest [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Download `TG-Oxyfire-Saver-macOS.zip`
3. Unzip → run **`Install.command`**
4. Open **TG Oxyfire Saver** → sign in with QR
5. Gatekeeper: right-click → **Open** if blocked

### Install — Windows
1. Open the latest [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest)
2. Download `TG-Oxyfire-Saver-Windows.zip`
3. Unzip → run **`TGOxyfireSaver.exe`**
4. Sign in with QR (Telegram → Settings → Devices)
5. Needs **WebView2** (usually already on Windows 10/11). If the window is blank, install [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
6. SmartScreen: **More info** → **Run anyway**

### Build from source
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
# macOS
bash scripts/install_from_source.sh
# Windows (or GitHub Actions → Build Windows)
pip install -r requirements-windows.txt
pyinstaller packaging/tg_oxyfire_saver_win.spec
```

---

## Русский

### Что делает
- Вход в Telegram от вашего пользователя (QR или номер)
- Скачивание по ссылке, диапазону, из буфера или через сторожей
- Очередь локально; трей / menu bar продолжает загрузки при закрытом окне
- Язык: **Русский / English**

### Приватность
Авторизация только с серверами Telegram. Данные у вас на компьютере.

- macOS: `~/Library/Application Support/TGVideoSaver/`
- Windows: `%APPDATA%\TGVideoSaver\`

### Установка — Mac
1. [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest) → `TG-Oxyfire-Saver-macOS.zip`
2. **`Install.command`** → открыть приложение → QR
3. Gatekeeper: ПКМ → **Открыть**

### Установка — Windows
1. [Release](https://github.com/Datastore24Kirill/tg_oxyfire_saver/releases/latest) → `TG-Oxyfire-Saver-Windows.zip`
2. Распаковать → **`TGOxyfireSaver.exe`**
3. Войти по QR
4. Нужен **WebView2** (обычно уже есть). Пустое окно → [установить Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
5. SmartScreen: **Подробнее** → **Выполнить в любом случае**

### Сборка из исходников
```bash
git clone https://github.com/Datastore24Kirill/tg_oxyfire_saver.git
cd tg_oxyfire_saver
# macOS
bash scripts/install_from_source.sh
# Windows / CI
pip install -r requirements-windows.txt
pyinstaller packaging/tg_oxyfire_saver_win.spec
```

---

## License

MIT — see [LICENSE](LICENSE)
