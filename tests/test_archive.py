import io
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from project_archive import build_project_zip

class ArchiveTests(unittest.TestCase):
    def test_credentials_git_data_and_runtime_are_never_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in ['app.py','.streamlit/config.toml','.streamlit/secrets.example.toml',
                        '.streamlit/secrets.toml','.env','.git/config','.autolex_runtime/limits.sqlite3',
                        'samples/private_real_case.docx','__pycache__/secret.pyc','untracked_secret.py']:
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('test')
            with ZipFile(io.BytesIO(build_project_zip(root))) as z:
                self.assertEqual(set(z.namelist()),{'legal_assistant/app.py','legal_assistant/.streamlit/config.toml','legal_assistant/.streamlit/secrets.example.toml'})

    def test_symlink_to_external_content_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir()
            secret=Path(tmp)/'private';secret.write_text('test')
            (root/'app.py').symlink_to(secret)
            with ZipFile(io.BytesIO(build_project_zip(root))) as z:self.assertEqual(z.namelist(),[])
