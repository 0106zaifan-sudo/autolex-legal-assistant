"""会话内案件工作区：显式归档、引用摘录、人工复核和安全导出。"""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from case_store import CaseStore, CaseError
from ai_ui import demo_analysis


def render_parse_report(report, key):
    st.text(f"解析状态：{report['status']}；完整性：{report['completeness']}")
    st.caption('读取情况不等于材料真实或全文完整；没有读到内容不能解释为没有证据。')
    if report['items']:
        st.dataframe(pd.DataFrame(report['items']), hide_index=True, width='stretch')
    for issue in report['issues']:
        st.text(f"[{issue['code']}] {issue['location']}：{issue['message']}")
    for limitation in report['limitations']:
        st.caption(limitation)
    st.download_button('下载解析报告 JSON', json.dumps(report, ensure_ascii=False, indent=2),
                       'AutoLex_解析报告.json', 'application/json', key=key)


def render_case_workspace(records, root):
    if '_case_store' not in st.session_state:
        st.session_state['_case_store'] = CaseStore()
    store = st.session_state['_case_store']
    st.divider()
    st.subheader('案件结构化工作区')
    st.caption('文件必须明确加入案件。材料记载、主张、推断、信息缺失分开记录；AI及规则输出不会自动成为已确认事实。原件仅存会话内存，请自行保留原件并及时导出。')
    with st.form('create_case'):
        title = st.text_input('案件标签（操作者命名，不代表真实案名）', key='case_title', max_chars=120)
        if st.form_submit_button('创建案件', key='create_case_submit'):
            try:
                cid = store.create_case(title)
                st.session_state['active_case'] = cid
            except CaseError as exc:
                st.error(str(exc))
    cases = store.list_cases()
    if not cases:
        st.info('创建案件后，可选择文档归档、记录引文、复核事实并导出案件。')
        return
    cid = st.selectbox('当前案件', list(cases), format_func=lambda x: cases[x], key='active_case')
    case = store.get_case(cid)
    failed = st.session_state.get('_parse_failures', {})
    options = list(records) + list(failed)
    selected = st.multiselect('明确选择要加入本案的文件', options,
                             format_func=lambda x: records[x]['文件名'] if x in records else failed[x]['name']+'（解析失败）',
                             key='case_documents_'+cid)
    if st.button('将所选文档加入本案', key='attach_documents'):
        for rid in selected:
            try:
                if rid in records:
                    store.attach_record(cid, records[rid])
                else:
                    upload = failed[rid]
                    store.attach_document(cid, upload['name'], upload['data'])
            except (CaseError, ValueError):
                st.error('文件归档或原件校验失败，未将该文件信息作为已确认事实。')
        st.rerun()
    if st.button('加入模拟事故材料及离线分析（不调用模型）', key='case_add_demo'):
        try:
            path = Path(root)/'samples_ai'/'模拟_AI事故材料.docx'
            did = store.attach_document(cid, path.name, path.read_bytes())
            store.import_analysis(cid, did, demo_analysis(root))
            st.rerun()
        except (CaseError, ValueError):
            st.error('模拟材料或绑定校验失败，未导入分析。')
    case = store.get_case(cid)
    st.caption(f'本案文档 {len(case.documents)} 份；证据锚点 {len(case.evidence)} 个。每个文件和引用均保留哈希及原文位置。')
    with st.expander('案件基本信息与来源', expanded=True):
        st.dataframe(pd.DataFrame([{'字段': key, **value.model_dump()} for key, value in case.basic_info.items()]), hide_index=True)
    if case.documents:
        did = st.selectbox('本案原文文件', list(case.documents),
                           format_func=lambda x: case.documents[x].file_name+' · '+x[:8], key='case_doc_'+cid)
        doc = case.documents[did]
        st.text('来源类型：'+doc.data_type)
        with st.expander('本文件解析覆盖报告'):
            render_parse_report(doc.parse_report, 'case_report_'+cid+'_'+did)
        name, data = store.get_original(cid, did)
        st.download_button('下载本案选定原始文件', data, name, key='case_original_'+cid+'_'+did)
        if doc.units:
            ui = st.selectbox('证据原文位置', list(range(len(doc.units))),
                              format_func=lambda i: doc.units[i]['location'], key='case_unit_'+cid+'_'+did)
            unit = doc.units[ui]
            st.text_area('本案原文（只读）', unit['text'], disabled=True, height=150, key='case_text_'+cid+'_'+did+'_'+str(ui))
            with st.form('case_quote_'+cid+'_'+did+'_'+str(ui)):
                quote = st.text_area('连续原文摘录（必须唯一定位）', value=unit['text'], key='case_quote_text_'+cid+'_'+did+'_'+str(ui))
                kind = st.selectbox('摘录类别', ['documented_fact', 'party_claim', 'unclassified'],
                                    format_func=lambda x: {'documented_fact':'材料记载（未确认）','party_claim':'当事人主张','unclassified':'待分类摘录'}[x],
                                    key='case_kind_'+cid+'_'+did+'_'+str(ui))
                if st.form_submit_button('保存引用及摘录', key='save_case_quote'):
                    try:
                        if not quote.strip() or unit['text'].count(quote) != 1:
                            raise CaseError('引文为空或位置有歧义，请扩大或更换摘录，不自动选第一个位置。')
                        start = unit['text'].index(quote)
                        eid = store.add_evidence(cid, did, ui, start, start+len(quote), quote)
                        store.record_statement(cid, quote, kind, [eid])
                        st.rerun()
                    except (CaseError, ValueError) as exc:
                        st.error(str(exc))
        if doc.units:
            with st.form('case_basic_'+cid+'_'+did+'_'+str(ui)):
                field = st.selectbox('基本信息字段', list(case.basic_info), key='case_basic_field_'+cid+'_'+did)
                value = st.text_input('基本信息原文值（不确定则留空，不自行补充）', key='case_basic_value_'+cid+'_'+did)
                if st.form_submit_button('保存基本信息候选', key='save_case_basic'):
                    try:
                        if not value.strip() or unit['text'].count(value) != 1:
                            raise CaseError('基本信息需在所选原文位置唯一出现，不自动选择歧义值。')
                        start = unit['text'].index(value)
                        eid = store.add_evidence(cid, did, ui, start, start+len(value), value)
                        store.record_basic_info(cid, field, value, [eid])
                        st.rerun()
                    except (CaseError, ValueError) as exc:
                        st.error(str(exc))
        with st.form('case_missing_'+cid+'_'+did):
            question = st.text_area('信息缺失或待核实事项（仅针对本文件检查范围，不代表现实中不存在）', key='case_missing_text_'+cid+'_'+did)
            if st.form_submit_button('记录待核实事项', key='save_case_missing'):
                try:
                    store.record_missing(cid, question, [did])
                    st.rerun()
                except CaseError as exc:
                    st.error(str(exc))
    cached = st.session_state.get('_ai_result')
    can_import = bool(cached and cached['record_id'] in case.documents)
    if st.button('将已生成的当前分析归入本案（不发起模型调用）', disabled=not can_import, key='case_import_analysis'):
        try:
            store.import_analysis(cid, cached['record_id'], cached['value'])
            st.rerun()
        except CaseError as exc:
            st.error(str(exc))
    case = store.get_case(cid)
    for name, label in [('facts', '材料记载与人工确认事实'), ('claims', '当事人主张'),
                        ('inferences', '推断（支持关系待人工核验）'), ('unclassified', '待分类摘录'),
                        ('timeline', '事件时间线（不同文件时钟未自动对齐）'), ('pending_items', '待核实事项与解析缺口')]:
        with st.expander(label):
            rows = getattr(case, name)
            if rows:
                st.dataframe(pd.DataFrame([row.model_dump() for row in rows]), hide_index=True, width='stretch')
            else:
                st.caption('暂无记录，不自动补齐。')
    with st.expander('证据索引及人工复核记录'):
        if case.evidence:
            st.dataframe(pd.DataFrame([{**span.model_dump(), '原始文件': case.documents[span.document_id].file_name} for span in case.evidence.values()]), hide_index=True)
        if case.reviews:
            st.dataframe(pd.DataFrame([r.model_dump() for r in case.reviews]), hide_index=True)
    candidates = [s for s in case.facts if s.kind == 'documented_fact']
    if candidates:
        with st.form('confirm_fact_'+cid):
            sid = st.selectbox('需要人工确认的材料记载', [s.statement_id for s in candidates],
                               format_func=lambda x: next(s.text[:70] for s in candidates if s.statement_id == x))
            reviewer = st.text_input('真实性复核人')
            note = st.text_area('真实性核实依据与范围（不能只写原文一致）')
            confirmed = st.checkbox('我已另行核实该事实真实性，并理解这是我录入的复核结论')
            if st.form_submit_button('登记人工确认事实', key='confirm_case_fact'):
                try:
                    if not confirmed:
                        raise CaseError('仅核对原文不会升级为已确认事实')
                    store.confirm_fact(cid, sid, reviewer, note)
                    st.rerun()
                except CaseError as exc:
                    st.error(str(exc))
    st.download_button('下载本案结构化 JSON（不内嵌原文件字节）', store.export_json(cid),
                       'AutoLex_案件结构化.json', 'application/json', key='case_export_'+cid)
