import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import importlib.util
spec = importlib.util.spec_from_file_location('release_check', Path(__file__).resolve().parents[1] / 'src/core/releases.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
select_release, version = module.select_release, module.version

REPO = 'owner/app'
def release(tag='v1.2.0', **patch):
    return dict(tag_name=tag, html_url='https://github.com/owner/app/releases/tag/'+tag,
                assets=[{'name':'app.zip','size':12}], **patch)

class ReleaseTests(unittest.TestCase):
    def test_numeric_order_and_no_downgrade(self):
        self.assertEqual(select_release([release('v1.9.0'),release('v1.10.0')],REPO,'1.8.0')['latest'],'1.10.0')
        self.assertIsNone(select_release([release()],REPO,'1.2.0'))
    def test_unready_and_untrusted(self):
        for field,value in [('assets',[]),('draft',True),('html_url','https://github.com.evil/owner/app/releases/tag/v1.2.0'),('tag_name','v1.2.0;sh')]:
            item=release();item[field]=value
            self.assertIsNone(select_release([item],REPO,'1.0.0'))
    def test_preview_opt_in(self):
        item=release(prerelease=True)
        self.assertIsNone(select_release([item],REPO,'1.0.0'))
        self.assertEqual(select_release([item],REPO,'1.0.0',True)['latest'],'1.2.0')
    def test_reject_invalid_versions(self):
        for v in ['main','1.2','1.2.3rc1','1.2.3.4']:
            self.assertIsNone(version(v))
