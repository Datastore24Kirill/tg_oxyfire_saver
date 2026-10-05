"""Runs from the update cache after the service exits, with the installed Python runtime."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def install(config):
    package=Path(config['package']); target=Path(config['target']); support=Path(config['support'])
    backup=package.parent/'backup'; backup.mkdir()
    for _ in range(120):
        try: os.kill(config['pid'],0)
        except ProcessLookupError: break
        time.sleep(1)
    else: raise RuntimeError('Сервис не завершился; установка отменена')
    # Only terminate this app's known UI/menu helper executables, never unrelated Python apps.
    commands=subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True)
    for line in commands.splitlines():
        parts=line.strip().split(None,1)
        if len(parts)!=2: continue
        command=parts[1]
        prefixes=[str(target/'Contents/Helpers'/name/'Contents/MacOS')+'/' for name in ('TGSaverWindow.app','TGOxyfireMenu.app')]
        if any(command.startswith(prefix) for prefix in prefixes):
            try: os.kill(int(parts[0]),signal.SIGTERM)
            except ProcessLookupError: pass
    subprocess.run(['/usr/bin/ditto',str(target),str(backup/'app')],check=True)
    managed=[]
    for source in (package/'src').rglob('*'):
        if not source.is_file(): continue
        relative=source.relative_to(package/'src')
        if any(part in {'.env','data','thumbs','.venv','__pycache__'} or part.endswith(('.session','.pyc','.log')) for part in relative.parts): continue
        dest=support/relative
        managed.append((relative,dest.exists()))
        if dest.exists():
            old=backup/'source'/relative;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
    old_version=(support/'VERSION').read_bytes() if (support/'VERSION').exists() else None
    try:
        subprocess.run(['/bin/bash',str(package/'scripts/install_from_source.sh')],check=True,cwd=str(package))
    except Exception:
        if target.exists(): shutil.rmtree(target)
        subprocess.run(['/usr/bin/ditto',str(backup/'app'),str(target)],check=True)
        for relative, existed in managed:
            dest=support/relative
            if existed: shutil.copy2(backup/'source'/relative,dest)
            elif dest.is_file(): dest.unlink()
        if old_version is not None: (support/'VERSION').write_bytes(old_version)
        raise
    finally:
        subprocess.run(['/usr/bin/open',str(target)],check=False)

if __name__=='__main__':
    try: install(json.loads(Path(sys.argv[1]).read_text()))
    except Exception as error:
        print('UPDATE FAILED:',error,flush=True)
        Path(sys.argv[1]).with_suffix('.error.txt').write_text(str(error))
        raise
