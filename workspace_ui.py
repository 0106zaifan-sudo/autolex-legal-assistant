"""显式下载/恢复；只传案件及原件，不序列化Streamlit会话或授权。"""
import hashlib
import json
import streamlit as st
from workspace_bundle import export_workspace,restore_workspace,restore_legacy,WorkspaceError


def read_upload(file,limit):
    if file.size>limit:raise WorkspaceError('upload_size_limit')
    data=file.getvalue()
    if len(data)>limit:raise WorkspaceError('upload_size_limit')
    return data


def finish_restore(outcome):
    # 结果仅为可查看的历史附件，不恢复到可调用AI的同意/缓存状态。
    cid=outcome['case_id']
    st.session_state['active_case']=cid
    st.session_state.setdefault('_workspace_histories',{})[cid]=outcome['history_trust']
    if outcome['analysis'] is not None:st.session_state.setdefault('_workspace_analysis',{})[cid]=outcome['analysis']
    for key in ('_md_result','_md_receipt','_md_fingerprint','_ai_result','_workspace_download'):
        st.session_state.pop(key,None)
    st.session_state['md_consent']=False
    st.session_state['_workspace_reset_ai_consent']=True
    st.session_state['_workspace_notice']='案件工作包已恢复；未恢复AI调用授权，也未自动调用模型。'
    st.rerun()


def render_workspace_import(store):
    from workspace_bundle import MAX_ZIP_BYTES,MAX_JSON_BYTES,MAX_EXPANDED_BYTES,MAX_DOCUMENTS
    if not st.checkbox('打开案件工作包导入工具（ZIP或受限旧版）',key='workspace_import_open'):
        return
    with st.expander('导入案件工作包'):
        st.caption('仅在点击导入后校验并恢复。冲突case_id不覆盖；解析器或快照不匹配拒绝。ZIP含原件，请仅使用可信离线材料。')
        upload=st.file_uploader('选择AutoLEX案件工作包ZIP',type=['zip'],max_upload_size=MAX_ZIP_BYTES//(1024*1024),key='workspace_zip_upload')
        consent=st.checkbox('我确认恢复此离线案件及其历史记录，理解哈希不证明材料真实或复核人身份',key='workspace_import_consent')
        if st.button('导入案件工作包',disabled=upload is None or not consent,key='workspace_import'):
            try:finish_restore(restore_workspace(store,read_upload(upload,MAX_ZIP_BYTES)))
            except WorkspaceError as exc:st.error(str(exc))
    with st.expander('受限旧版恢复：案件JSON＋全部原件'):
        st.caption('只接受1.1/1.2案件、当前解析器、唯一原始文件名及完全匹配的全部PDF/DOCX；不迁移未知版本，不恢复缺失的联合分析缓存。')
        bundle=st.file_uploader('原AutoLex_案件结构化.json',type=['json'],max_upload_size=MAX_JSON_BYTES//(1024*1024),key='workspace_legacy_json')
        files=st.file_uploader('该JSON对应的全部原始文件',type=['pdf','docx'],accept_multiple_files=True,key='workspace_legacy_files')
        agreed=st.checkbox('我确认按受限旧版规则恢复，保留未经身份认证的历史',key='workspace_legacy_consent')
        if st.button('验证并恢复旧版JSON与原件',disabled=bundle is None or not files or not agreed,key='workspace_legacy_import'):
            try:
                if len(files)>MAX_DOCUMENTS or len({f.name for f in files})!=len(files):raise WorkspaceError('legacy_file_count_or_names')
                originals={f.name:read_upload(f,20*1024*1024) for f in files}
                if sum(len(b) for b in originals.values())>MAX_EXPANDED_BYTES:raise WorkspaceError('legacy_total_size_limit')
                finish_restore(restore_legacy(store,read_upload(bundle,MAX_JSON_BYTES),originals))
            except WorkspaceError as exc:st.error(str(exc))
    notice=st.session_state.pop('_workspace_notice',None)
    if notice:st.success(notice)


def render_workspace_export(store,cid):
    with st.expander('下载案件工作包'):
        st.caption('工作包含原始文件与人工历史，未加密。请离线妥善保存；案件变更后须重新生成。普通结构化JSON不含原件，不能独立恢复。')
        cached=st.session_state.get('_md_result')
        if not (isinstance(cached,dict) and cached.get('case_id')==cid):
            cached=st.session_state.get('_workspace_analysis',{}).get(cid)
            if cached is not None:st.caption('可选附件来源：此前工作包恢复并重新验证的历史分析，不是本会话新调用。')
        available=isinstance(cached,dict) and cached.get('case_id')==cid
        include=st.checkbox('显式纳入当前可用的联合分析JSON（再次校验，不自动归档附件）',disabled=not available,key='workspace_include_'+cid)
        chosen=cached if include and available else None
        fingerprint=hashlib.sha256((store.export_json(cid)+json.dumps(chosen,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
        saved=st.session_state.get('_workspace_download')
        if saved and saved['fingerprint']!=fingerprint:st.session_state.pop('_workspace_download',None)
        if st.button('生成案件工作包（校验后下载）',key='workspace_generate_'+cid):
            st.session_state.pop('_workspace_download',None)
            try:
                data=export_workspace(store,cid,analysis=chosen)
                st.session_state['_workspace_download']={'case_id':cid,'fingerprint':fingerprint,'data':data}
            except WorkspaceError as exc:st.error(str(exc))
        saved=st.session_state.get('_workspace_download')
        if saved and saved['case_id']==cid and saved['fingerprint']==fingerprint:
            st.download_button('下载案件工作包',saved['data'],'AutoLEX_案件工作包.zip','application/zip',key='workspace_download_'+cid)
        restored=st.session_state.get('_workspace_analysis',{}).get(cid)
        if restored is not None:
            st.caption('以下为工作包显式附带且恢复时重新验证的联合分析，不代表本会话重新调用过模型，也没有自动导入其额外条目。')
            st.download_button('下载恢复的联合分析历史JSON',json.dumps(restored,ensure_ascii=False,indent=2),'AutoLEX_联合分析历史.json','application/json',key='workspace_restored_analysis_'+cid)
            with st.expander('查看恢复的联合分析附件'):st.json(restored)
