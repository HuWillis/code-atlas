import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'collection'
        self.root.mkdir()
        self.up = Path(self.temp.name) / 'upstream'
        self.up.mkdir()
        git(self.up, 'init', '-b', 'main')
        git(self.up, 'config', 'user.name', 'Test')
        git(self.up, 'config', 'user.email', 'test@example.invalid')
        (self.up / 'LICENSE').write_text('License fixture\n')
        (self.up / 'old.txt').write_text('first\n')
        self.commit()
        self.source = {'repo': 'example/project', 'description': '用途', 'branch': ''}

    def commit(self):
        git(self.up, 'add', '-A')
        git(self.up, 'commit', '-m', 'fixture')
        return git(self.up, 'rev-parse', 'HEAD')

    def prepare(self, source, dest):
        return sync.export_snapshot(self.up.as_uri(), source.get('branch') or 'main', dest)

    def run_sync(self, sources=None, prepare=None):
        return sync.synchronize(self.root, sources if sources is not None else [self.source], prepare or self.prepare)

    def test_import_update_delete_and_no_change(self):
        (self.root / 'notes').mkdir()
        (self.root / 'notes/mine.md').write_text('自己的笔记')
        self.assertEqual(self.run_sync(), 1)
        target = self.root / 'repos/example/project'
        self.assertEqual((target / 'LICENSE').read_text(), 'License fixture\n')
        self.assertFalse((target / '.git').exists())
        state = (self.root / 'sync-state.json').read_bytes()
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual((self.root / 'sync-state.json').read_bytes(), state)
        (self.up / 'old.txt').unlink()
        (self.up / 'new.txt').write_text('second')
        sha = self.commit()
        self.assertEqual(self.run_sync(), 1)
        self.assertFalse((target / 'old.txt').exists())
        self.assertEqual((target / 'new.txt').read_text(), 'second')
        self.assertEqual(json.loads((self.root / 'sync-state.json').read_text())['example/project']['commit'], sha)
        self.assertEqual((self.root / 'notes/mine.md').read_text(), '自己的笔记')

    def test_batch_fetch_failure_keeps_all_previous_data(self):
        self.run_sync()
        before = (self.root / 'sync-state.json').read_bytes()
        (self.up / 'old.txt').write_text('changed')
        self.commit()
        def prepare(source, dest):
            if source['repo'] == 'other/broken':
                raise RuntimeError('upstream unavailable')
            return self.prepare(source, dest)
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.run_sync([self.source, {'repo': 'other/broken'}], prepare)
        self.assertEqual((self.root / 'repos/example/project/old.txt').read_text(), 'first\n')
        self.assertEqual((self.root / 'sync-state.json').read_bytes(), before)

    def test_config_rejects_escapes_duplicates_and_unsafe_names(self):
        for repo in ['../evil', 'owner/../repo', 'https://github.com/a/b', 'a/.git', 'a/repo.git', '-a/b']:
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                sync.validate_sources([{'repo': repo}])
        with self.assertRaises(ValueError):
            sync.validate_sources([{'repo': 'Owner/Repo'}, {'repo': 'owner/repo'}])
        with self.assertRaises(ValueError):
            sync.validate_sources([{'repo': 'a/b', 'branch': '--upload-pack=evil'}])

    def test_export_rejects_lfs_and_submodules_without_publishing(self):
        (self.up / 'large.bin').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'LFS'):
            self.run_sync()
        self.assertFalse((self.root / 'repos/example/project').exists())
        (self.up / 'large.bin').unlink()
        self.commit()
        git(self.up, 'update-index', '--add', '--cacheinfo', '160000,' + git(self.up, 'rev-parse', 'HEAD') + ',nested')
        git(self.up, 'commit', '-m', 'submodule fixture')
        with self.assertRaisesRegex(ValueError, '子模块'):
            self.run_sync()

    def test_archive_rejects_escape_symlinks_and_keeps_safe_links(self):
        (self.up / 'link').symlink_to('LICENSE')
        self.commit()
        self.run_sync()
        self.assertTrue((self.root / 'repos/example/project/link').is_symlink())
        (self.up / 'link').unlink()
        (self.up / 'link').symlink_to('../../../outside')
        self.commit()
        with self.assertRaisesRegex(ValueError, '链接'):
            self.run_sync()
        self.assertEqual(os.readlink(self.root / 'repos/example/project/link'), 'LICENSE')
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as archive:
            info = tarfile.TarInfo('../outside'); info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        buf.seek(0)
        with tarfile.open(fileobj=buf) as archive, self.assertRaises(ValueError):
            sync.extract_archive(archive, self.root / 'extract')

    def test_link_chain_escape_is_rejected(self):
        (self.up / 'nested').mkdir()
        (self.up / 'nested/link').symlink_to('..', target_is_directory=True)
        (self.up / 'escape').symlink_to('nested/link/../outside')
        self.commit()
        with self.assertRaisesRegex(ValueError, '链接'):
            self.run_sync()
        self.assertFalse((self.root / 'repos/example/project').exists())

    def test_install_failure_rolls_back_previous_tree_and_index(self):
        self.run_sync()
        before = (self.root / 'sync-state.json').read_bytes()
        (self.up / 'old.txt').write_text('changed')
        self.commit()
        original = Path.rename
        def fail_state(path, target):
            if path.name == 'sync-state.json' and path.parent.name.startswith('.sync-'):
                raise OSError('simulate metadata replacement failure')
            return original(path, target)
        with patch.object(Path, 'rename', fail_state), self.assertRaises(OSError):
            self.run_sync()
        self.assertEqual((self.root / 'repos/example/project/old.txt').read_text(), 'first\n')
        self.assertEqual((self.root / 'sync-state.json').read_bytes(), before)

    def test_empty_list_and_existing_symlink_path(self):
        self.assertEqual(self.run_sync([]), 0)
        (self.root / 'repos').mkdir(exist_ok=True)
        (self.root / 'repos/example').symlink_to(self.up, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_sync()
        self.assertEqual((self.up / 'old.txt').read_text(), 'first\n')


if __name__ == '__main__':
    unittest.main()
