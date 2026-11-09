"""下载包只含明确列出的代码、文档及模拟样本，绝不遍历部署目录。"""
from pathlib import Path
import io
import zipfile

SOURCE_FILES = (
    "timeline_candidates.py", "tests/test_event_candidates.py", "tests/test_candidate_ui.py",
    "docs/V2B_EVENT_CANDIDATES.md", "docs/v2b_event_candidates_tests.txt",
    "tests/test_multidoc_timeline_quote.py", "docs/V2B_TIMELINE_QUOTE_FIX.md",
    "docs/v2b_timeline_quote_tests.txt",
    "tests/test_fact_reasoning_contract.py", "docs/V2B_FACT_REASONING_FIX.md",
    "docs/v2b_fact_reasoning_tests.txt",
    "validation_diagnostics.py", "tests/test_validation_diagnostics.py", "tests/test_diagnostic_ui.py",
    "docs/V2B_VALIDATION_DIAGNOSTICS.md", "docs/v2b_validation_diagnostics_tests.txt",
    'multidoc_ai.py', 'multidoc_ui.py', 'tests/test_multidoc_ai.py', 'tests/test_multidoc_ui.py',
    'docs/MULTIDOC_AI_V2B.md', 'docs/multidoc_ai_offline_tests.txt',
    'evidence_relations.py', 'relation_ui.py', 'make_multidoc_samples.py', 'tests/test_multidoc.py',
    'docs/MULTIDOC_V2A.md', 'docs/multidoc_offline_tests.txt',
    'samples_multidoc/模拟_现场记录.pdf', 'samples_multidoc/模拟_驾驶人陈述.docx',
    'samples_multidoc/模拟_企业说明.docx', 'samples_multidoc/模拟_电子数据摘要.pdf',
    'tests/test_timeline_completeness.py', 'docs/TIMELINE_COMPLETENESS_PATCH.md', 'docs/timeline_completeness_offline_tests.txt',
    'tests/test_output_quality.py', 'docs/OUTPUT_QUALITY_P1.md', 'docs/output_quality_p1_offline_tests.txt',
    'tests/ui_isolation.py', 'tests/test_single_scenario.py',
    'docs/SINGLE_SCENARIO.md', 'docs/single_scenario_offline_tests.txt',
    'sample_debug.py', 'sim_b_debug.py', 'tools/replay_sim_b.py', 'tests/test_sample_debug.py',
    'docs/SIM_B_DEBUG.md', 'docs/sim_b_manual_reproduction.json', 'docs/sample_debug_offline_tests.txt',
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
