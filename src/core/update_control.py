"""User-triggered update job; checks metadata again and never accepts a client URL."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from core.releases import check_release
from core.runtime import support_dir
from core.version import APP_VERSION
from core.updater import download, stage_replacement, launch_swap


class UpdateController:
    def __init__(self, service):
        self.service = service; self.lock = threading.Lock()
        self.state = {'busy':False, 'message':'', 'error':''}
    def status(self):
        with self.lock: return dict(self.state)
    def message(self, message):
        with self.lock: self.state['message'] = message
    def start(self):
        with self.lock:
            if self.state['busy']: return {'ok':False, 'error':'Обновление уже выполняется'}
            self.state = {'busy':True, 'message':'Проверка версии…', 'error':''}
        threading.Thread(target=self.run, daemon=True, name='update-install').start()
        return {'ok':True}
    def run(self):
        was_paused = self.service._paused
        try:
            if sys.platform == 'win32' and not getattr(sys,'frozen',False):
                raise RuntimeError('Запустите установленную сборку приложения.')
            info = check_release('Datastore24Kirill/tg_oxyfire_saver', APP_VERSION)
            if not info: raise RuntimeError('Новой готовой версии нет.')
            cache = support_dir()/'updates'
            unpacked = download(info,'Datastore24Kirill/tg_oxyfire_saver','saver',cache,self.message)
            self.service.set_paused(True)
            self.message('Обновление готово. Ожидаю завершения активных загрузок…')
            time.sleep(1)  # Allow the queue worker to observe pause before inspecting active jobs.
            while self.service.snapshot()['stats']['active']:
                time.sleep(1)
            if sys.platform == 'darwin':
                from core.app_paths import find_app_bundle
                target = find_app_bundle()
                if target != Path('/Applications/TG Oxyfire Saver.app'):
                    raise RuntimeError('Для обновления TG Saver должен находиться в /Applications/TG Oxyfire Saver.app.')
                if not os.access(target.parent,os.W_OK): raise RuntimeError('Нет доступа к папке приложения.')
                package = unpacked/'TG-Oxyfire-Saver-macOS'
                installer=package/'scripts/install_from_source.sh'
                if not installer.is_file(): raise RuntimeError('В пакете отсутствует установщик')
                helper = cache/('install-'+str(os.getpid())+'.py')
                shutil.copy2(Path(__file__).with_name('update_mac_helper.py'),helper)
                config = helper.with_suffix('.json')
                config.write_text(json.dumps({'package':str(package),'target':str(target),'support':str(support_dir()),'pid':os.getpid()}))
                log = (cache/'last-install.log').open('w')
                subprocess.Popen([str(support_dir()/'.venv/bin/python'),str(helper),str(config)],cwd=str(cache),start_new_session=True,stdout=log,stderr=subprocess.STDOUT)
                log.close()
            else:
                target=Path(sys.executable).parent
                candidate=stage_replacement(unpacked,target,'saver')
                launch_swap(candidate,target,cache,'TGOxyfireSaver.exe')
            self.message('Установка обновления. Приложение перезапустится…')
            time.sleep(1)
            os._exit(0)
        except Exception as error:
            self.service.set_paused(was_paused)
            with self.lock: self.state={'busy':False,'message':'Обновление не установлено','error':str(error)}
