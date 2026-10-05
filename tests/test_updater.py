import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util
spec=importlib.util.spec_from_file_location('updater',Path(__file__).resolve().parents[1]/'src/core/updater.py')
updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)

class UpdateTests(unittest.TestCase):
    def test_archive_paths(self):
        for name in ['../outside','/absolute','C:/file','a\\..\\..\\outside']:
            with tempfile.TemporaryDirectory() as root:
                file=Path(root)/'bad.zip'
                with zipfile.ZipFile(file,'w') as z: z.writestr(name,'bad')
                with self.assertRaises(ValueError): updater.validate_zip(file)
    def test_archive_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'bad.zip'
            with zipfile.ZipFile(file,'w') as z:
                entry=zipfile.ZipInfo('app/link');entry.external_attr=0o120777<<16;z.writestr(entry,'../../escape')
            with self.assertRaises(ValueError): updater.validate_zip(file)
    def test_wrong_digest_keeps_install_untouched(self):
        asset={'name':'app-macOS-arm64.zip','browser_download_url':'https://github.com/o/r/releases/download/v1/app.zip','digest':'sha256:'+'0'*64,'size':3}
        class Response(io.BytesIO): url='https://release-assets.githubusercontent.com/file'
        with tempfile.TemporaryDirectory() as root, patch.object(updater,'choose_asset',return_value=asset),patch.object(updater,'urlopen',return_value=Response(b'bad')):
            with self.assertRaises(ValueError): updater.download({'assets':[asset]},'o/r','translator',root,lambda text:None)
            self.assertEqual(list(Path(root).iterdir()),[])
    def test_asset_platform(self):
        with patch.object(updater.sys,'platform','win32'):
            asset={'name':'OxyTranslateGame-1.0.0-Windows-x64-Portable.zip'}
            self.assertEqual(updater.choose_asset({'assets':[asset]},'translator'),asset)
            with self.assertRaises(RuntimeError): updater.choose_asset({'assets':[]},'translator')
    def test_windows_helper_parses(self):
        if sys.platform != 'win32': self.skipTest('PowerShell is verified on Windows CI')
        import subprocess
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);candidate=base/'new'/'app';candidate.mkdir(parents=True);target=base/'installed'
            with patch.object(updater.subprocess,'Popen'):
                updater.launch_swap(candidate,target,base,'App.exe',pid=12345)
            helper=candidate.parent/'install.ps1'
            quoted=str(helper).replace("'","''")
            subprocess.run(['powershell.exe','-NoProfile','-Command',"$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+quoted+"',[ref]$t,[ref]$e)|Out-Null;if($e.Count){throw $e}"],check=True)

    def test_mac_swap_and_backup(self):
        if sys.platform != 'darwin': self.skipTest('macOS helper')
        import subprocess
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);candidate=base/'stage'/'app';candidate.mkdir(parents=True);(candidate/'version').write_text('new')
            target=base/'installed';target.mkdir();(target/'version').write_text('old')
            with patch.object(updater.subprocess,'Popen'):
                updater.launch_swap(candidate,target,base,'App',pid=99999999)
            script=candidate.parent/'install.sh'
            script.write_text(script.read_text().replace('/usr/bin/open','/usr/bin/true'))
            subprocess.run(['/bin/sh',str(script)],check=True)
            self.assertEqual((target/'version').read_text(),'new')
            self.assertEqual((candidate.parent/'previous/version').read_text(),'old')
