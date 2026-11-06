from pathlib import Path
import io
import zipfile
import pandas as pd
import streamlit as st
from core import FIELDS, PENDING, extract, summary, search, review, export_excel

ROOT = Path(__file__).parent
st.set_page_config(page_title='智能网联汽车法律资料助手', page_icon='⚖️', layout='wide')
st.title('智能网联汽车法律资料整理与检索助手')
st.caption('研究生实习作品 · 本地规则提取 MVP · 无付费 AI API')
st.warning('自动提取仅生成原文候选，不能验证案件真实性、法律效力或适用性。模拟样本均为虚构，不可作为法律依据。')
if 'records' not in st.session_state:
    st.session_state.records = {}
records = st.session_state.records


def add_file(name, data):
    try:
        r = extract(name, data)
        if r['id'] in records:
            st.info(f'已跳过重复文件：{name}')
        else:
            records[r['id']] = r
            st.success(f'已读取：{name}')
    except Exception as exc:
        st.error(f'{name}：读取失败（{type(exc).__name__}）。请检查文件是否损坏、加密、超限或格式错误。')


with st.sidebar:
    st.header('资料导入')
    uploads = st.file_uploader('上传 PDF / DOCX（单文件 ≤20 MB）', type=['pdf', 'docx'], accept_multiple_files=True)
    if st.button('读取上传文件', width='stretch'):
        for f in uploads or []:
            add_file(f.name, f.getvalue())
    if st.button('加载模拟测试样本', width='stretch'):
        for p in sorted((ROOT / 'samples').glob('*')):
            if p.suffix in ('.pdf', '.docx'):
                add_file(p.name, p.read_bytes())
    st.caption('文件和核验记录仅保存在本浏览器会话的服务器内存中；会话丢失或服务重启会清空。请及时导出 Excel。程序不主动调用外部服务。')
    if st.button('清空本会话资料', width='stretch'):
        records.clear()
        st.rerun()
    st.divider()
    st.caption('代码、样本和使用文档可下载，解压后在自己的电脑运行。')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.zip', '.pyc'):
                z.write(p, 'legal_assistant/' + str(p.relative_to(ROOT)))
    st.download_button('下载完整项目 ZIP', buf.getvalue(), 'legal_assistant.zip', 'application/zip')

all_records = list(records.values())
cols = st.columns(3)
cols[0].metric('资料数量', len(all_records))
cols[1].metric('待人工核验资料', sum(summary(r)['核验状态'] == PENDING for r in all_records))
cols[2].metric('模拟资料', sum(r['数据类型'].startswith('模拟') for r in all_records))
keyword = st.text_input('关键词检索', placeholder='搜索文件名、提取字段或全文；多个词以空格分隔，须同时命中')
a, b, c = st.columns(3)
court_options = sorted({v for r in all_records for v in summary(r)['法院'].split('；')})
courts = a.multiselect('法院', court_options)
statuses = b.multiselect('资料核验状态', [PENDING, '已人工核验', '提取有误'])
kinds = c.multiselect('数据类型', sorted({r['数据类型'] for r in all_records}))
filtered = search(all_records, keyword, courts, statuses, kinds)
st.subheader(f'检索结果 · {len(filtered)} 份')
st.caption('资料状态汇总：任一字段“提取有误”优先显示有误；否则任一字段待核验则资料待核验；全部字段已人工核验才显示已核验。')
if filtered:
    st.dataframe(pd.DataFrame([summary(r) for r in filtered]), hide_index=True, width='stretch')
    st.download_button('导出当前检索结果为 Excel', export_excel(filtered), '法律资料整理_含核验状态.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    rid = st.selectbox('选择资料查看原文与核验', [r['id'] for r in filtered],
                       format_func=lambda x: f"{records[x]['文件名']} · {x[:8]}")
    record = records[rid]
    st.info(record['数据类型'])
    for warning in record['warnings']:
        st.warning(warning)
    left, right = st.columns([1, 1])
    with left:
        st.subheader('字段候选与出处')
        st.dataframe(pd.DataFrame(record['candidates']), hide_index=True, width='stretch')
        cid = st.selectbox('选择核验项', [x['候选ID'] for x in record['candidates']],
                           format_func=lambda x: next(f"{v['字段']} · {v['原文摘录'][:45] or '未提取到内容'} · {v['原文位置']}" for v in record['candidates'] if v['候选ID'] == x), key=f'candidate_{rid}')
        candidate = next(x for x in record['candidates'] if x['候选ID'] == cid)
        st.caption('核验范围：请注明仅核对原文一致性，或另行核查了权威来源、效力和适用性。原文候选保留，不直接改写。')
        with st.form(f'review_{rid}_{cid}'):
            status = st.selectbox('核验状态', [PENDING, '已人工核验', '提取有误'], index=[PENDING, '已人工核验', '提取有误'].index(candidate['核验状态']))
            reviewer = st.text_input('核验人', value=candidate['核验人'])
            note = st.text_area('核验备注 / 出处 / 错误原因', value=candidate['核验备注'])
            if st.form_submit_button('保存核验记录'):
                try:
                    review(record, cid, status, reviewer, note)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with right:
        st.subheader('原文定位')
        unit_indices = list(range(len(record['units'])))
        if unit_indices:
            default = next((i for i, u in enumerate(record['units']) if u['location'] == candidate['原文位置']), 0)
            ui = st.selectbox('页码 / 段落 / 表格', unit_indices, index=default,
                              format_func=lambda i: record['units'][i]['location'], key=f'unit_{rid}_{cid}')
            st.text_area('解析后的正文（只读）', record['units'][ui]['text'], height=440, disabled=True, key=f'text_{rid}_{cid}_{ui}')
            st.caption('字符区间使用解析文本的零起点、左闭右开区间。DOCX 段落编号不等于 Word 页码；PDF 页码是文件物理页序。')
        else:
            st.warning('没有可读取的正文单元。')
    with st.expander('核验日志'):
        st.dataframe(pd.DataFrame(record['audit']), hide_index=True)
else:
    st.info('请从左侧加载模拟样本或上传文件；已有资料时可调整筛选条件。')
