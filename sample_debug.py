"""默认关闭的固定虚构样本调试仓；不读取Secrets，不接受任意输出路径。"""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

ROOT = Path(__file__).resolve().parent
# 独立于可编辑manifest，禁止仅靠文件名/“模拟”标签或模型提供的哈希放行。
FIXTURES = {
    'SIM_A': ('模拟_接管提示争议.docx', '56677f79901be2f1d889ffad415e86d7fc6eec32884230bbd6991919d87049e0'),
    'SIM_B': ('模拟_时间缺失与日志核验.docx', '9c73e94cea4746f53099fde92f4f34b729286350e8540fcdb43c7f0203443600'),
}
MODES = ('live_sdk', 'injected_test_client', 'manual_offline')
MAX_BYTES = 512000
SECRET_MARKERS = re.compile(r'(?i)\bsk-[a-z0-9_-]{8,}|\bgh[pousr]_[a-z0-9]+|bearer\s+|api[_ -]?key|password|密码|pbkdf2_sha256|-----BEGIN .*PRIVATE KEY')


def fixed_record(scenario_id):
    from core import extract
    name, digest = FIXTURES[scenario_id]
    path = ROOT/'acceptance_samples'/name
    if path.is_symlink():
        raise ValueError('fixture_unavailable')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('fixture_unavailable')
    return extract(name, data)


def fixture_id(record):
    for scenario_id, (name, digest) in FIXTURES.items():
        if record.get('文件SHA256') == digest and record.get('文件名') == name:
            canonical = fixed_record(scenario_id)
            if (record.get('units') == canonical['units']
                    and record.get('parser_version') == canonical['parser_version']):
                return scenario_id
    return None


@contextmanager
def _private_directory():
    """POSIX dir_fd+NOFOLLOW拒绝符号链接；不支持安全权限的平台失败关闭。"""
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
        raise OSError('secure_storage_unavailable')
    with ExitStack() as stack:
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        for part in ('.autolex_runtime', 'rejected_sample_debug'):
            try: os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError: pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, child)
            info = os.fstat(child)
            if info.st_uid != os.geteuid():
                raise OSError('wrong_storage_owner')
            os.fchmod(child, 0o700)
            fd = child
        yield fd


def capture_rejected_output(record, raw_output, *, enabled=False,
                            execution_mode='manual_offline', forbidden_values=()):
    """只保存Schema通过而绑定失败的原始JSON字符串；从不返回原文或异常详情。"""
    if enabled is not True:
        return {'status': 'disabled'}
    try:
        scenario = fixture_id(record)
        if scenario is None:
            return {'status': 'refused_non_fixture'}
        if execution_mode not in MODES or not isinstance(raw_output, str) or len(raw_output.encode()) > MAX_BYTES:
            return {'status': 'refused_output'}
        if SECRET_MARKERS.search(raw_output) or any(value and value in raw_output for value in forbidden_values):
            return {'status': 'refused_sensitive_output'}
        from ai_analysis import Analysis, AIError, PROMPT, analysis_context, build_sources, validate_analysis
        try:
            parsed = Analysis.model_validate_json(raw_output)
        except ValueError:
            return {'status': 'refused_schema'}
        decoded = json.dumps(parsed.model_dump(mode='json'),ensure_ascii=False)
        if SECRET_MARKERS.search(decoded) or any(value and value in decoded for value in forbidden_values):
            return {'status': 'refused_sensitive_output'}
        # 不为借用模拟哈希的任意文字建立原文仓：所有摘录必须来自固定正文。
        if any(getattr(parsed, key) != value for key,value in analysis_context(record).items()):
            return {'status': 'refused_context'}
        text = '\n'.join(unit['text'] for unit in record['units'])
        for section in ('facts','timeline','issues','pending_evidence'):
            for item in getattr(parsed,section):
                refs = list(item.sources)
                if section == 'timeline':
                    refs += [item.event_source] + ([item.time_source] if item.time_source else [])
                if item.text not in text or any(ref.quote not in text for ref in refs):
                    return {'status': 'refused_non_fixture_text'}
        try:
            validate_analysis(parsed, record, build_sources(record))
        except AIError:
            pass
        else:
            return {'status': 'refused_valid_analysis'}
        envelope = {'artifact_version': '1.0', 'purpose': 'rejected_debug_not_valid_analysis',
                    'execution_mode': execution_mode, 'fixture_id': scenario,
                    'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
                    'schema_valid': True, 'evidence_binding_valid': False,
                    'raw_output': raw_output}
        encoded = json.dumps(envelope, ensure_ascii=False, indent=2).encode()
        if len(encoded) > MAX_BYTES*2:
            return {'status':'refused_output'}
        with _private_directory() as directory:
            if len(os.listdir(directory)) >= 100:
                return {'status': 'storage_limit_reached'}
            artifact_id = uuid.uuid4().hex
            filename = artifact_id+'.json'
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(encoded)
            except BaseException:
                os.unlink(filename, dir_fd=directory)
                raise
        return {'status': 'saved', 'artifact_id': artifact_id, 'fixture_id': scenario,
                'execution_mode': execution_mode}
    except Exception:
        return {'status': 'capture_failed'}


def read_capture(artifact_id):
    """只读固定私有目录的32位ID；不会打开用户指定的任意路径。"""
    if not re.fullmatch(r'[0-9a-f]{32}', artifact_id):
        raise ValueError('invalid_debug_artifact')
    try:
        with _private_directory() as directory:
            fd = os.open(artifact_id+'.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or info.st_size > MAX_BYTES*2):
                    raise ValueError('invalid_debug_artifact')
                result = json.loads(handle.read(MAX_BYTES*2))
        if (result.get('purpose') != 'rejected_debug_not_valid_analysis'
                or result.get('execution_mode') not in MODES or result.get('fixture_id') not in FIXTURES
                or not isinstance(result.get('raw_output'), str)):
            raise ValueError('invalid_debug_artifact')
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        raise ValueError('invalid_debug_artifact') from None
