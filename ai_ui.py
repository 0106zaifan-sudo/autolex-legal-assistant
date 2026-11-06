"""Streamlit 访问门禁和独立 AI 面板。任何付费请求仅由用户点击触发。"""
import json
import os
from ai_providers import codespaces_values
from pathlib import Path
import streamlit as st
from ai_analysis import AIError, Analysis, analyze_record, build_sources, validate_analysis
from core import extract
from security import QuotaStore, SecurityError, Settings, verify_password


def load_settings():
    try:
        # 普通环境只读Secrets；Codespaces仅补入所选服务商的环境Secret。
        values = dict(st.secrets)
    except FileNotFoundError:
        values = {}
    try:
        return Settings.from_secrets(codespaces_values(values, os.environ))
    except ValueError as exc:
        raise SecurityError(str(exc)) from None


def enforce_access(settings):
    if settings.mode == 'local' and not settings.password_hash:
        st.caption('本地模式：AI 仍需配置访问密码并登录。请勿以此模式公开部署。')
        return None
    if not settings.password_hash:
        st.error('公开模式未配置访问控制，应用已锁定。请在 Streamlit Secrets 设置 APP_PASSWORD_HASH。')
        st.stop()
    if st.session_state.get('_auth_principal') == settings.principal:
        with st.sidebar:
            if st.button('退出登录', key='logout'):
                st.session_state.clear()
                st.rerun()
        return settings.principal
    # 密码变更导致旧登录失效时，清除旧会话资料和分析结果。
    if st.session_state.get('_auth_principal'):
        st.session_state.clear()
    st.subheader('访问验证')
    def authenticate():
        password = st.session_state.pop('_login_password', '')
        try:
            QuotaStore(settings.db_path).reserve_login()
            valid = verify_password(password, settings.password_hash)
            if valid:
                st.session_state['_auth_principal'] = settings.principal
                st.session_state.pop('_login_error', None)
            else:
                st.session_state['_login_error'] = '访问密码不正确。'
        except SecurityError as exc:
            st.session_state['_login_error'] = str(exc)
    with st.form('login'):
        st.text_input('访问密码', type='password', key='_login_password', max_chars=128)
        st.form_submit_button('登录', on_click=authenticate)
    if st.session_state.get('_login_error'):
        st.error(st.session_state['_login_error'])
    st.stop()


def demo_analysis(root):
    root = Path(root)
    p = root / 'samples_ai' / '模拟_AI事故材料.docx'
    record = extract(p.name, p.read_bytes())
    parsed = Analysis.model_validate_json((root / 'samples_ai' / 'mock_analysis.json').read_text())
    result = validate_analysis(parsed, record, build_sources(record))
    result['mode'] = '离线模拟结果（非 AI 调用、非真实案件）'
    return result


def render_result(result, key):
    st.info(result['mode'])
    st.text('对应文件：' + result['file_name'])
    st.caption('文件 SHA256：' + result['file_sha256'])
    st.warning('全部内容待人工核验。“事实”仅指原文记载，不代表真实性已确认。引文一致性校验不能证明推理成立。')
    names = {'facts': '关键事实及主张', 'timeline': '事故时间线',
             'issues': '法律争议焦点（待核实推断）', 'pending_evidence': '待核实证据（待核实推断）'}
    for section, label in names.items():
        with st.expander(label, expanded=True):
            rows = result['sections'][section]
            if not rows:
                st.caption('原文信息不足，未生成此项。')
            if section == 'timeline':
                st.caption('能识别的完整原文日期按时间排序；无法识别或未记载的时间列在后面，不据此推断因果。')
            for i, row in enumerate(rows, 1):
                st.text(f"{i}. [{row['kind']}] {row.get('time_text', '')} {row['text']}")
                if row['reasoning']:
                    st.text(row['reasoning'])
                for ref in row['sources']:
                    st.caption(f"来源 {ref['source_id']} · {ref['location']} · 字符 [{ref['start']}, {ref['end']})")
                    st.code(ref['quote'], language=None)
    st.download_button('下载分析 JSON（含来源及核验状态）',
                       json.dumps(result, ensure_ascii=False, indent=2),
                       'AutoLex_分析_待人工核验.json', 'application/json', key=key)


def render_ai_panel(record, settings, principal, root):
    st.divider()
    st.subheader('AI 案件事实分析')
    st.caption('仅分析当前选中的单份资料；不自动合并不同案件。事实、主张及推断分开呈现，所有项目保留原文引证。')
    reason = settings.ai_disabled_reason(principal)
    if reason:
        st.info(reason)
    selected_id = (record['id'] if record else None, settings.provider, settings.model)
    if st.session_state.get('_ai_selected_record') != selected_id:
        st.session_state['ai_consent'] = False
        st.session_state.pop('_ai_result', None)
        st.session_state.pop('_last_ai_receipt', None)
        st.session_state['_ai_selected_record'] = selected_id
    coverage_needed = bool(record and record.get('parse_report', {}).get('requires_acknowledgement'))
    if coverage_needed:
        st.warning('解析报告有未读取或未核验区域。下方确认同时表示仅分析已读取文本，其他区域仍需人工检查。')
    consent_label = f'我确认有权将所选资料正文发送至 {settings.provider_spec.label} API，已完成必要脱敏。'
    if coverage_needed:
        consent_label += '我已查看解析报告，并确认仅分析已读取范围。'
    consent = st.checkbox(consent_label, key='ai_consent')
    coverage_ack = consent if coverage_needed else True
    disabled = bool(reason) or record is None or not consent
    if st.button('分析当前资料', disabled=disabled, key='run_ai'):
        # 每次都重新执行后端权限、额度、输入、输出检查，不能依赖按钮禁用。
        st.session_state.pop('_ai_result', None)
        st.session_state.pop('_last_ai_receipt', None)
        try:
            with st.spinner('正在分析并核对引证…'):
                result = analyze_record(record, settings, QuotaStore(settings.db_path), principal, consent, coverage_acknowledged=coverage_ack)
            st.session_state['_ai_result'] = {'record_id': record['id'], 'value': result}
            st.session_state['_last_ai_receipt'] = result.get('call_receipt')
        except (AIError, SecurityError) as exc:
            st.session_state['_last_ai_receipt'] = getattr(exc, 'receipt', None)
            st.error(str(exc))
        except Exception:
            st.error('分析暂不可用，未保存结果，请联系管理员。')
    cached = st.session_state.get('_ai_result')
    if cached and record and cached['record_id'] == record['id']:
        render_result(cached['value'], 'download_ai')
    with st.expander('离线模拟演示（不调用模型、不消耗额度）'):
        st.caption('使用独立的虚构事故材料及固定测试响应，与当前上传资料无关。不会替代真实 AI 分析。')
        if st.button('查看离线模拟分析', key='show_ai_demo'):
            st.session_state['_show_ai_demo'] = True
        if st.session_state.get('_show_ai_demo'):
            render_result(demo_analysis(root), 'download_ai_demo')

    receipt=st.session_state.get('_last_ai_receipt')
    if receipt:
        with st.expander('最近一次模型调用记录（错误也保留，未知用量不填零）'):
            st.json(receipt)
            st.download_button('下载调用记录 JSON',json.dumps(receipt,ensure_ascii=False,indent=2),
                               'AutoLex_模型调用记录.json','application/json',key='download_ai_receipt')
