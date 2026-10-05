"""Verified release download and staging. Installation is requested explicitly by the user."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shlex
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile


def choose_asset(info, product):
    if sys.platform == 'darwin':
        suffix = f'macOS-{platform.machine()}.zip' if product == 'translator' else 'macOS.zip'
    elif sys.platform == 'win32':
        suffix = 'Windows-x64-Portable.zip' if product == 'translator' else 'Windows.zip'
    else:
        raise RuntimeError('Автообновление поддерживается только на Mac и Windows.')
    for asset in info.get('assets', []):
        if asset.get('name', '').endswith(suffix): return asset
    raise RuntimeError('Для этой системы ещё нет готовой сборки.')


def validate_zip(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if sum(x.file_size for x in entries) > 4_000_000_000:
            raise ValueError('Слишком большой архив обновления')
        links = set()
        for entry in entries:
            name = entry.filename
            parts = PurePosixPath(name).parts
            if not parts or name.startswith('/') or '\\' in name or ':' in name or '..' in parts:
                raise ValueError('Небезопасный путь в архиве')
            if stat.S_ISLNK(entry.external_attr >> 16):
                target = archive.read(entry).decode('utf-8')
                if target.startswith('/') or '\\' in target or ':' in target:
                    raise ValueError('Небезопасная ссылка в архиве')
                resolved = posixpath.normpath(str(PurePosixPath(name).parent / target))
                if resolved == '..' or resolved.startswith('../'):
                    raise ValueError('Ссылка выходит за пределы архива')
                links.add(name.rstrip('/'))
        for entry in entries:
            if any(str(parent) in links for parent in PurePosixPath(entry.filename).parents):
                raise ValueError('Запись через символическую ссылку запрещена')


def download(info, repo, product, cache, progress):
    asset = choose_asset(info, product)
    url = asset.get('browser_download_url', '')
    prefix = 'https://github.com/' + repo + '/releases/download/'
    digest = asset.get('digest', '')
    if not url.startswith(prefix) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('Нет проверяемой SHA-256 суммы официальной сборки')
    size = asset.get('size', 0)
    if not isinstance(size, int) or not 0 < size <= 2_000_000_000:
        raise ValueError('Некорректный размер сборки')
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='update-', dir=cache)); archive = stage/'release.zip'
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    hashed = hashlib.sha256(); received = 0; last_percent = -1
    try:
        with urlopen(Request(url, headers={'User-Agent':'Oxyfire-Updater'}), timeout=30, context=context) as response, archive.open('wb') as output:
            if not response.url.startswith('https://'): raise ValueError('Небезопасное перенаправление')
            while block := response.read(1024*1024):
                received += len(block)
                if received > size: raise ValueError('Размер загрузки не совпадает')
                output.write(block); hashed.update(block)
                percent = int(received*100/size)
                if percent != last_percent: progress(f'Скачивание обновления: {percent}%'); last_percent = percent
        if received != size or hashed.hexdigest() != digest[7:]: raise ValueError('Контрольная сумма обновления не совпала')
        progress('Проверка и распаковка обновления…'); validate_zip(archive)
        unpacked = stage/'unpacked'; unpacked.mkdir()
        if sys.platform == 'darwin': subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),str(unpacked)],check=True)
        else:
            with zipfile.ZipFile(archive) as z: z.extractall(unpacked)
        return unpacked
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def mac_bundle(executable):
    for parent in Path(executable).absolute().parents:
        if parent.suffix == '.app': return parent
    raise RuntimeError('Автообновление доступно в установленной .app сборке.')


def stage_replacement(unpacked, target, product):
    target = Path(target).absolute()
    if sys.platform == 'darwin':
        name = 'OxyTranslateGame.app' if product == 'translator' else 'TG Oxyfire Saver.app'
        source = Path(unpacked)/name if product == 'translator' else Path(unpacked)/'TG-Oxyfire-Saver-macOS'/'dist'/name
    else:
        source = Path(unpacked)/('OxyTranslateGame' if product == 'translator' else 'TG-Oxyfire-Saver-Windows')
    if not source.is_dir(): raise ValueError('В архиве нет ожидаемого приложения')
    if not target.is_dir(): raise ValueError('Не найдена установленная копия')
    # Copy beside the installation before stopping it. Permission/disk errors leave it untouched.
    candidate = Path(tempfile.mkdtemp(prefix=target.name+'.update-',dir=target.parent))/'app'
    try:
        shutil.copytree(source,candidate,symlinks=True)
        if sys.platform == 'darwin' and product == 'translator':
            import plistlib
            info=plistlib.loads((candidate/'Contents/Info.plist').read_bytes())
            if info.get('CFBundleIdentifier') != 'com.oxyfire.OxyTranslateGame.Desktop': raise ValueError('Неверный идентификатор приложения')
            subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(candidate)],check=True,capture_output=True)
        if sys.platform == 'win32':
            exe = 'OxyTranslateGame.exe' if product == 'translator' else 'TGOxyfireSaver.exe'
            if not (candidate/exe).is_file(): raise ValueError('В сборке нет исполняемого файла')
        return candidate
    except Exception:
        shutil.rmtree(candidate.parent,ignore_errors=True); raise


def launch_swap(candidate, target, cache, executable_name, pid=None):
    """External OS helper survives app exit. Keep the prior installation for rollback."""
    candidate, target = Path(candidate), Path(target).absolute()
    backup = candidate.parent/'previous'; log = Path(cache)/'last-install.log'
    pid = pid or os.getpid()
    if sys.platform == 'darwin':
        q=shlex.quote
        script=f'''#!/bin/sh
exec >>{q(str(log))} 2>&1
n=0
while kill -0 {int(pid)} 2>/dev/null; do
 n=$((n+1)); [ "$n" -lt 120 ] || exit 1; sleep 1
done
mv {q(str(target))} {q(str(backup))} || exit 1
if mv {q(str(candidate))} {q(str(target))}; then
 /usr/bin/open {q(str(target))}
else
 mv {q(str(backup))} {q(str(target))}
 /usr/bin/open {q(str(target))}
 exit 1
fi
'''
        helper=candidate.parent/'install.sh';helper.write_text(script)
        subprocess.Popen(['/bin/sh',str(helper)],start_new_session=True,cwd=str(candidate.parent),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        def q(value): return "'"+str(value).replace("'","''")+"'"
        script=f'''$ErrorActionPreference = 'Stop'
Start-Transcript -Path {q(log)} -Force
try {{
  $p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue
  if ($p -and !$p.WaitForExit(120000)) {{ throw 'Application did not exit' }}
  Move-Item -LiteralPath {q(target)} -Destination {q(backup)}
  try {{ Move-Item -LiteralPath {q(candidate)} -Destination {q(target)} }}
  catch {{ Move-Item -LiteralPath {q(backup)} -Destination {q(target)}; throw }}
  Start-Process -FilePath {q(target/executable_name)}
}} finally {{ Stop-Transcript }}
'''
        (candidate.parent/'install.ps1').write_text(script,encoding='utf-8-sig')
        subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],cwd=str(candidate.parent),creationflags=0x08000000,close_fds=True)
