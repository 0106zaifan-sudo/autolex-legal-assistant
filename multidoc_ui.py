"""独立批次授权与结果预览；只有明确点击才发起一次调用。"""
import json
import streamlit as st
from security import QuotaStore,SecurityError
from multidoc_ai import prepare_case,analyze_case,import_case_analysis,MultiAIError


def render_multidoc_ai(store,cid,settings,principal):
    st.subheader('AI 多文档综合分析')
    case=store.get_case(cid)
    selected=st.multiselect('选择本案2—4份联合分析材料',list(case.documents),
                           format_func=lambda did:case.documents[did].file_name+' · '+did[:8],key='md_select_'+cid)
    if not 2<=len(selected)<=4:
        st.caption('先明确归档文档，再选择同案2—4份材料；不自动逐文件调用。');return
    try:
        batch=prepare_case(store,cid,selected,settings)
    except (ValueError,SecurityError):
        st.error('当前批次解析、规模或原件校验未通过，禁止发送。');return
    fingerprint=(batch['batch_sha256'],principal)
    reset=st.session_state.pop('_md_reset_consent',False)
    changed=st.session_state.get('_md_fingerprint')!=fingerprint
    if changed:
        st.session_state.pop('_md_result',None);st.session_state.pop('_md_receipt',None)
    if changed or reset:
        st.session_state['md_consent']=False;st.session_state['_md_fingerprint']=fingerprint

    st.caption('本次批次：'+batch['batch_sha256'])
    ack=[]
    for d in batch['documents']:
        st.text(d['file_name']+' · '+d['document_id']);st.caption('SHA256：'+d['file_sha256'])
        if d['document_id'] in batch['required_ack']:
            with st.expander('解析风险：'+d['file_name']):st.json(d['parse_report'])
            if st.checkbox('我已核查此文件解析风险，仅分析已读取范围',key='md_ack_'+batch['batch_sha256']+'_'+d['document_id']):ack.append(d['document_id'])
    reason=settings.ai_disabled_reason(principal)
    if reason:st.info(reason)
    consent=st.checkbox(f'我授权将上述全部材料本次发送至{settings.provider_spec.label}，已完成脱敏并理解可能计费',key='md_consent')
    enabled=not reason and consent and set(batch['required_ack']).issubset(ack)
    if st.button('分析所选批次（一次请求）',disabled=not enabled,key='run_multidoc_ai'):
        st.session_state.pop('_md_result',None);st.session_state.pop('_md_receipt',None)
        try:
            result=analyze_case(store,cid,selected,settings,QuotaStore(settings.db_path),principal,
                                authorized_batch=batch['batch_sha256'],coverage_acknowledged=ack)
            st.session_state['_md_result']=result;st.session_state['_md_receipt']=result['receipt']
        except (MultiAIError,SecurityError) as exc:
            st.session_state['_md_receipt']=getattr(exc,'receipt',None)
            st.session_state['_md_error']='联合分析失败，未导入案件。请查看安全回执，不自动重试。'
        finally:st.session_state['_md_reset_consent']=True
        st.rerun()
    error=st.session_state.pop('_md_error',None)
    if error:st.error(error)
    result=st.session_state.get('_md_result')
    matches=bool(result and result['case_id']==cid and result['batch_sha256']==batch['batch_sha256'])
    if matches:
        st.warning('候选全部待人工核验。时间线按文档分别保留，不选择最终时间；证据一致不证明关系语义成立。')
        for key,label in [('facts','事实及主张'),('timeline','多来源时间线'),('relations','跨文件候选关系'),('pending_evidence','待核实问题'),('completeness_diagnostics','有限完整性提示'),('cross_document_diagnostics','跨文档时间差异提示')]:
            with st.expander(label):st.json(result[key])
        st.download_button('下载联合分析JSON（含独立来源清单）',json.dumps(result,ensure_ascii=False,indent=2),'AutoLex_联合分析_待核验.json','application/json',key='download_multidoc')
    if st.button('将当前批次候选明确导入本案',disabled=not matches,key='import_multidoc_ai'):
        try:import_case_analysis(store,cid,result);st.success('已导入候选；原人工审阅保留。')
        except (ValueError,KeyError,TypeError):st.error('结果或档案已变化，未导入；请重新核对。')
    receipt=st.session_state.get('_md_receipt')
    if receipt and receipt.get('case_id')==cid and receipt.get('batch_sha256')==batch['batch_sha256']:
        with st.expander('最近联合调用安全回执'):
            st.json(receipt)
            st.download_button('下载联合验证安全回执（不含原文）',json.dumps(receipt,ensure_ascii=False,indent=2),
                               'AutoLex_联合验证回执.json','application/json',key='download_multidoc_receipt')
