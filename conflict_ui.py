"""独立审查工作台。解释只读，人工结论只追加原RelationReview历史。"""
import streamlit as st
from case_store import CaseError
from conflict_review import build_workbench,ConflictReviewError
from relation_ui import TYPES

STAGES={'system_emit':'系统发出','vehicle_output':'车辆输出','driver_receive':'驾驶人接收','driver_perceive':'驾驶人感知'}
STATUS={'all':'全部','unreviewed':'未审阅','needs_review':'待复核','modified':'已修改','rejected':'已驳回','confirmed':'已确认关系'}


def filter_rows(rows,category,status):
    result=[]
    for row in rows:
        if category=='时间记载' and not (row['left']['time']['time_texts'] or row['right']['time']['time_texts']):continue
        if category=='提示命题' and not (row['left']['predicate']['stage'] or row['right']['predicate']['stage']):continue
        if category=='信息缺口' and not (row['left']['gaps'] or row['right']['gaps']):continue
        latest=row['latest_review'];current=latest['status'] if latest else 'unreviewed'
        if status!='all' and current!=status:continue
        result.append(row)
    return result


def render_conflict_workbench(store,cid):
    st.subheader('证据冲突审查工作台')
    st.caption('只读规则解释与人工审阅分开；不自动判定材料真实、法律矛盾、责任或事故因果。')
    if not st.checkbox('打开证据冲突审查工作台',key='cr_open_'+cid):return
    if st.button('发现已保存锚点的关系候选（离线）',key='cr_discover_'+cid):
        try:store.discover_relations(cid);st.rerun()
        except (ValueError,CaseError):st.error('原文引用或候选发现未通过核验，未生成有效审查结论。')
    try:rows=build_workbench(store,cid)
    except ConflictReviewError as exc:st.error(str(exc));return
    if not rows:
        st.info('暂无可审查关系。先保存不同材料的完整引用，再明确点击发现候选；不按关键词自动合并材料。');return
    category=st.selectbox('按审查内容筛选',['全部','时间记载','提示命题','信息缺口'],key='cr_category_'+cid)
    status=st.selectbox('按最新人工状态筛选',list(STATUS),format_func=STATUS.get,key='cr_filter_'+cid)
    selected=filter_rows(rows,category,status)
    st.caption(f'筛选显示 {len(selected)} / {len(rows)} 项；未显示不等于已经排除风险。')
    if not selected:st.info('当前筛选没有项目；原候选和历史记录均保留。');return
    by_id={row['relation_id']:row for row in selected}
    rid=st.selectbox('选择证据审查对',list(by_id),format_func=lambda r:by_id[r]['left']['file_name']+' ↔ '+by_id[r]['right']['file_name']+' · '+r[:20],key='cr_pair_'+cid)
    row=by_id[rid];original=row['original_candidate']
    st.text('原自动候选：'+TYPES[original['relation_type']]+' · '+original['method'])
    st.text('原规则依据：'+original['reason'])
    st.info('当前只读解释：'+(TYPES[row['assessment_type']] if row['assessment_type'] else '事件编号不同，不合并为同一事件'))
    st.caption('只读解释版本：'+row['version']+'；事件身份：'+row['identity']['status']+'；命题规则：'+row['predicate']['rule']+'；时间规则：'+row['time']['rule'])
    st.warning('人工确认关系不等于确认事实或证据真实。时区/时钟未认证，无法可靠比较实际时刻；不选择最终时间、不校准、不归责。')
    for column,side in zip(st.columns(2),('left','right')):
        data=row[side]
        with column:
            st.text(data['file_name']);st.caption('文档ID：'+data['document_id'])
            st.caption('证据ID：'+data['evidence_id']);st.caption('文件SHA256：'+data['file_sha256'])
            st.caption('解析快照SHA256：'+data['parsed_text_sha256']);st.caption('引文SHA256：'+data['quote_sha256'])
            st.caption(data['parser_version']+' · '+data['location']+f" · [{data['start']}, {data['end']})")
            st.text_area('完整连续原文引文（只读）',value=data['quote'],disabled=True,height=160,key='cr_quote_'+cid+'_'+rid+'_'+side)
            time_text=data['time']['time_text'] or ('未选定：'+'；'.join(data['time']['time_texts']) if data['time']['time_texts'] else '无法确定')
            st.text('时间文本：'+time_text+'；精度：'+data['time']['precision'])
            p=data['predicate'];st.text('命题环节：'+STAGES.get(p['stage'],'待核实')+'；字面主体：'+(p['subject'] or '未知'))
            st.caption('命题规则：'+p['rule']+'；范围条件：'+('可进行有限字面对照' if data['scope_valid'] else '归属/完整性不确定'))
            if data['parse_issue_codes']:st.warning('解析风险仍保留：'+', '.join(data['parse_issue_codes']))
            with st.expander('完整原文上下文与事件标识来源'):
                st.text_area('完整单元上下文（只读）',value=data['context'],disabled=True,height=180,key='cr_context_'+cid+'_'+rid+'_'+side)
                if data['event_identity_source']:st.json(data['event_identity_source'])
            if data['gaps']:
                with st.expander('原文明确提及的信息缺口（只读定位）'):st.json(data['gaps'])
    if row['time']['display']:
        st.info('字面时间差：'+row['time']['display']+'。仅对显示文本作算术；不是实际间隔。')
    else:st.info('无法计算可靠的字面时间差；不补日期、精度或其他来源时间。')
    for text in row['suggestions']:st.text(text)
    for text in row['limitations']:st.caption(text)
    latest=row['latest_review']
    if latest:
        st.text('最新人工状态：'+STATUS[latest['status']]+'；修正类型：'+TYPES[latest['relation_type']])
        st.text('复核人：'+latest['reviewer']+'；理由：'+latest['reason'])
    else:st.caption('尚无人工审阅，不因规则解释自动完成核验。')
    target=(cid,rid)
    if st.session_state.get('_cr_target')!=target:
        st.session_state['_cr_target']=target
        st.session_state['cr_status']='needs_review';st.session_state['cr_type']=row['assessment_type'] or original['relation_type']
        st.session_state['cr_reviewer']='';st.session_state['cr_reason']=''
    with st.form('cr_review_'+cid):
        chosen_status=st.selectbox('本次人工审阅状态',['needs_review','modified','rejected','confirmed'],format_func=STATUS.get,key='cr_status')
        kind=st.selectbox('本次人工关系类型',list(TYPES),format_func=TYPES.get,key='cr_type')
        who=st.text_input('本次复核人',key='cr_reviewer')
        reason=st.text_area('本次复核理由与范围',key='cr_reason')
        if st.form_submit_button('追加本次审查记录',key='cr_save'):
            try:
                build_workbench(store,cid)  # 写前再核验，不依赖先前预览或按钮状态。
                store.review_relation(cid,rid,chosen_status,kind,who,reason);st.rerun()
            except (ValueError,CaseError):st.error('审查记录未保存，请核验原文并填写复核人和理由。')
    with st.expander('完整人工审查历史（不覆盖原候选）'):
        if row['history']:st.json(row['history'])
        else:st.caption('暂无记录。')
