"""同案跨文件候选的并排复核；不调用模型。"""
import streamlit as st
from case_store import CaseError

TYPES={'support_candidate':'支持候选','inconsistency_candidate':'不一致候选','related':'有关联，关系未定','needs_verification':'需进一步核实'}

def render_relations(store,cid):
 st.subheader('跨文件证据候选与复核')
 st.caption('先在各文档保存连续引用，再发现候选；相同关键词不证明支持，时间差异不等于法律矛盾。')
 if st.button('发现本案证据关系候选（离线）',key='discover_relations'):
  try:store.discover_relations(cid)
  except (CaseError,ValueError) as exc:st.error(str(exc))
 case=store.get_case(cid)
 if not case.relations:
  st.caption('暂无候选；需要不同原始文件的证据锚点。');return
 rid=st.selectbox('选择关系候选',[r.relation_id for r in case.relations],key='relation_'+cid)
 relation=next(r for r in case.relations if r.relation_id==rid)
 st.info(TYPES[relation.relation_type]+' · '+relation.reason)
 st.caption(relation.method+' · '+relation.limitations)
 for column,eid in zip(st.columns(2),(relation.left_id,relation.right_id)):
  span=case.evidence[eid];doc=case.documents[span.document_id]
  with column:
   st.text(doc.file_name);st.caption('文档ID：'+doc.document_id)
   st.caption('原文件SHA256：'+span.document_sha256)
   st.caption('解析快照SHA256：'+span.parsed_text_sha256)
   st.caption(f'{span.location} · [{span.start}, {span.end})')
   st.code(span.quote,language=None)
 st.warning('确认关系只表示操作者的关联判断，不确认材料真实，不确认责任。原自动候选不会被覆盖。')
 with st.form('review_relation_'+cid):
  status=st.selectbox('关系复核状态',['needs_review','confirmed','modified','rejected'],key='relation_status')
  kind=st.selectbox('本次审阅关系类型',list(TYPES),index=list(TYPES).index(relation.relation_type),format_func=TYPES.get,key='relation_type')
  who=st.text_input('关系复核人',key='relation_reviewer')
  reason=st.text_area('关系复核理由及范围',key='relation_reason')
  if st.form_submit_button('追加关系审阅记录',key='save_relation_review'):
   try:store.review_relation(cid,rid,status,kind,who,reason);st.rerun()
   except (CaseError,ValueError) as exc:st.error(str(exc))
 reviews=[r.model_dump() for r in case.relation_reviews if r.relation_id==rid]
 if reviews:
  st.caption('最近人工审阅：'+reviews[-1]['status']+' · '+TYPES[reviews[-1]['relation_type']])
  st.json(reviews)
