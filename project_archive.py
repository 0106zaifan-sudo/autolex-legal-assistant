"""下载包只含明确列出的代码、文档及模拟样本，绝不遍历部署目录。"""
from pathlib import Path
import io
import zipfile

SOURCE_FILES = (
    'app.py', 'core.py', 'ai_analysis.py', 'ai_ui.py', 'security.py', 'project_archive.py',
    'requirements.txt', 'README.md', 'TEST_REPORT.md', 'PHASE2_ACCEPTANCE.md',
    'make_samples.py', 'make_ai_samples.py', '.gitignore', '.streamlit/config.toml',
    '.streamlit/secrets.example.toml', 'tools/hash_password.py',
    'tests/test_core.py', 'tests/test_app.py', 'tests/test_ai_analysis.py', 'tests/test_security.py',
    'tests/test_ai_ui.py', 'tests/test_archive.py',
    'samples/模拟_信息缺失.docx', 'samples/模拟_无文字页.pdf',
    'samples/模拟_车联网数据.docx', 'samples/模拟_车联网数据.pdf',
    'samples/模拟_辅助驾驶责任.docx', 'samples/模拟_辅助驾驶责任.pdf',
    'samples_ai/模拟_AI事故材料.docx', 'samples_ai/mock_analysis.json',
    '模拟成果_法律资料整理.xlsx',
)


def build_project_zip(root):
    root = Path(root).resolve()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for rel in SOURCE_FILES:
            path = root / rel
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                archive.write(path, 'legal_assistant/' + rel)
    return output.getvalue()
