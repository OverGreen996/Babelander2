"""Downloader failure contracts; no network or user data."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import tempfile
import unittest
import zipfile
from babelander.assets import Asset,download,extract_verified
from babelander.types import Cancellation,Cancelled

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup);self.payload=b'verified bytes';self.token=Cancellation()
        self.asset=Asset('model.gguf','https://example.invalid/file',len(self.payload),hashlib.sha256(self.payload).hexdigest())
    def session(self,body,status=200,content_range='',cancel=False):
        owner=self
        class Response:
            status_code=status;headers={'Content-Range':content_range}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def raise_for_status(self):pass
            def iter_content(self,size):
                if cancel:owner.token.cancel()
                yield body
        client=SimpleNamespace(calls=[])
        def get(url,**kwargs):client.calls.append(kwargs);return Response()
        client.get=get;return client
    def test_full_verified_download(self):
        final=download(self.asset,self.root,self.token,session=self.session(self.payload))
        self.assertEqual(final.read_bytes(),self.payload);self.assertFalse((self.root/'model.gguf.part').exists())
    def test_resume_requires_exact_content_range(self):
        (self.root/'model.gguf.part').write_bytes(self.payload[:4]);client=self.session(self.payload[4:],206,f'bytes 4-{len(self.payload)-1}/{len(self.payload)}')
        self.assertEqual(download(self.asset,self.root,self.token,session=client).read_bytes(),self.payload)
        self.assertEqual(client.calls[0]['headers']['Range'],'bytes=4-')
    def test_range_ignored_restarts_without_append(self):
        (self.root/'model.gguf.part').write_bytes(b'old partial')
        self.assertEqual(download(self.asset,self.root,self.token,session=self.session(self.payload)).read_bytes(),self.payload)
    def test_mismatched_range_keeps_original_partial(self):
        p=self.root/'model.gguf.part';p.write_bytes(b'orig')
        with self.assertRaises(ValueError):download(self.asset,self.root,self.token,session=self.session(b'bad',206,'bytes 0-2/3'))
        self.assertEqual(p.read_bytes(),b'orig');self.assertFalse((self.root/'model.gguf').exists())
    def test_corruption_never_replaces_existing_asset(self):
        final=self.root/'model.gguf';final.write_bytes(b'existing')
        with self.assertRaises(ValueError):download(self.asset,self.root,self.token,session=self.session(b'x'*len(self.payload)))
        self.assertEqual(final.read_bytes(),b'existing');self.assertFalse((self.root/'model.gguf.part').exists())
    def test_short_download_keeps_partial(self):
        with self.assertRaises(ValueError):download(self.asset,self.root,self.token,session=self.session(b'short'))
        self.assertEqual((self.root/'model.gguf.part').read_bytes(),b'short')
    def test_oversized_response_never_installs(self):
        with self.assertRaises(ValueError):download(self.asset,self.root,self.token,session=self.session(self.payload+b'extra'))
        self.assertFalse((self.root/'model.gguf').exists())
    def test_cancel_preserves_partial(self):
        p=self.root/'model.gguf.part';p.write_bytes(self.payload[:4])
        with self.assertRaises(Cancelled):download(self.asset,self.root,self.token,session=self.session(self.payload[4:],206,f'bytes 4-{len(self.payload)-1}/{len(self.payload)}',True))
        self.assertEqual(p.read_bytes(),self.payload[:4]);self.assertFalse((self.root/'model.gguf').exists())
    def test_valid_existing_asset_needs_no_request(self):
        (self.root/'model.gguf').write_bytes(self.payload);client=self.session(b'wrong')
        download(self.asset,self.root,self.token,session=client);self.assertFalse(client.calls)
    def test_archive_rejects_windows_paths_and_symlinks(self):
        for index,name in enumerate(('../escape.dll','/absolute.dll','C:/outside.dll','folder/../outside.dll','folder\\..\\outside.dll','con.dll','name.dll:stream','name. /file.dll')):
            with self.subTest(name=name):
                archive=self.root/f'{index}.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'bad')
                stage=self.root/f'stage{index}';stage.mkdir()
                with self.assertRaises(ValueError):extract_verified([archive],stage,self.token)
                self.assertFalse(any(stage.rglob('*.dll')))
        archive=self.root/'link.zip'
        with zipfile.ZipFile(archive,'w') as z:
            link=zipfile.ZipInfo('link.dll');link.external_attr=(0o120777<<16);z.writestr(link,b'outside')
        with self.assertRaises(ValueError):extract_verified([archive],self.root/'stage0',self.token)
    def test_archive_rejects_duplicate_case_names(self):
        archive=self.root/'duplicate.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('file.dll',b'1');z.writestr('FILE.dll',b'2')
        stage=self.root/'stage';stage.mkdir()
        with self.assertRaises(ValueError):extract_verified([archive],stage,self.token)
    def test_good_archives_and_cancel(self):
        archive=self.root/'good.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('server.exe',b'1');z.writestr('nested/file.dll',b'2')
        stage=self.root/'stage';stage.mkdir();extract_verified([archive],stage,self.token)
        self.assertEqual((stage/'nested/file.dll').read_bytes(),b'2')
        self.token.cancel()
        with self.assertRaises(Cancelled):extract_verified([archive],stage,self.token)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AssetTests))
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,'failures':[s for _,s in result.failures],'errors':[s for _,s in result.errors],'network':'zero requests, controlled responses'}
    Path(__file__).with_name('test-results').joinpath('asset-unit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(not report['passed'])
