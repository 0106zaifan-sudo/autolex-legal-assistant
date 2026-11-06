"""下载包只含明确列出的代码、文档及模拟样本，绝不遍历部署目录。"""
from pathlib import Path
import io
import zipfile

SOURCE_FILES = (
    'ai_providers.py', 'tests/test_providers.py', 'tests/test_fact_classification.py', 'docs/MULTI_PROVIDER.md',
    'docs/multi_provider_offline_tests.txt',
    'docs/FACT_CLASSIFICATION_PATCH.md', 'docs/fact_classification_offline_tests.txt',
    'model_runtime.py', 'live_acceptance.py', 'make_acceptance_samples.py',
    'tools/run_live_acceptance.py', 'tests/test_live_acceptance.py',
    'acceptance_samples/模拟_接管提示争议.docx', 'acceptance_samples/模拟_时间缺失与日志核验.docx',
    'acceptance_samples/manifest.json', 'docs/LIVE_AI_ACCEPTANCE.md',
    'docs/LIVE_AI_ACCEPTANCE_STATUS.json', 'docs/live_acceptance_offline_tests.txt',
    'document_parser.py', 'case_schema.py', 'case_store.py', 'evidence.py', 'case_ui.py',
    'tests/test_document_parser.py', 'tests/test_case_store.py', 'tests/test_case_ui.py',
    'docs/CASE_STRUCTURE_COVERAGE.md',
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
