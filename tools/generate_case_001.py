"""CASE-001标准版：只生成/解析固定虚构资料、定位人工Gold、离线预检。不调用模型/配额。"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import io
import json
from importlib.metadata import version
from pathlib import Path
import random
import stat
import sys
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docx import Document
from docx.shared import Pt
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from case_store import CaseStore
from core import extract
from evidence import make_span,snapshot_hash
from ai_analysis import build_sources
from multidoc_ai import prepare_case,candidate_request_for
from security import Settings
from timeline_candidates import build_event_catalog
from conflict_review import review_pair

SOURCE=ROOT/'datasets'/'CASE-001'
GENERATOR_VERSION='case001-generator/1.0'
BASE_SHA='2ff740104cdd334f33d085e8a90d7e8053b6a4f9'
SEED=20261109
CASE_ID='case_'+hashlib.sha256(b'AutoLEX CASE-001 standard/1.0').hexdigest()[:32]
NEUTRAL='【模拟材料：完全虚构，不是真实案件；来源及真实性未核验】'
DECLARATION='【完全虚构，仅用于软件测试】'


class DatasetError(ValueError):pass


def digest(data):return hashlib.sha256(data).hexdigest()


def js(value):return (json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()


def ensure(ok,message):
    if not ok:raise DatasetError(message)


def filename(doc):
    value='模拟_CASE-001_'+doc['id']+'_'+doc['title']+'.'+doc['format']
    ensure('/' not in value and '\\' not in value,'文件名不安全')
    return value


def paragraphs(doc,tag):
    return [NEUTRAL,doc['lead'],DECLARATION,'模拟材料：'+doc['title'],
            '测试案件：CASE-001；材料编号：'+doc['id']+'；生成标记：'+tag+'。',
            '文内编制时间：'+doc['compiled_at']+'；编制者：'+doc['compiler']+'。',
            *doc['paragraphs']]


def docx_bytes(lines,title):
    doc=Document();doc.styles['Normal'].font.size=Pt(10)
    cp=doc.core_properties;cp.title=title;cp.subject='完全虚构，仅用于软件测试'
    cp.author='AutoLEX虚构数据生成器';cp.last_modified_by=cp.author
    cp.created=cp.modified=datetime(2026,10,1);cp.revision=1
    for text in lines:doc.add_paragraph(text)
    raw=io.BytesIO();doc.save(raw);out=io.BytesIO()
    # 固定OOXML ZIP成员时间、顺序与权限，消除python-docx打包时钟差异。
    with zipfile.ZipFile(io.BytesIO(raw.getvalue())) as source,zipfile.ZipFile(out,'w') as target:
        for name in sorted(source.namelist()):
            info=zipfile.ZipInfo(name,(2026,10,1,0,0,0));info.create_system=3
            info.external_attr=(stat.S_IFREG|0o600)<<16;info.compress_type=zipfile.ZIP_DEFLATED
            target.writestr(info,source.read(name),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    return out.getvalue()


def pdf_bytes(lines,title):
    font='STSong-Light';pdfmetrics.registerFont(UnicodeCIDFont(font))
    ensure(len(lines)<=30,'PDF标准版单页超过30段；不自动截断或隐藏分页')
    for i,text in enumerate(lines):
        ensure(pdfmetrics.stringWidth(text,font,9.5)<=515,f'PDF {title} 第{i+1}段超宽；请显式调整段落，不截断')
    raw=io.BytesIO();c=canvas.Canvas(raw,pagesize=(595.28,841.89),invariant=1,pageCompression=1)
    c.setTitle('模拟_CASE-001_'+title);c.setAuthor('AutoLEX fictional fixture generator')
    c.setSubject('完全虚构，仅用于软件测试');c.setCreator(GENERATOR_VERSION)
    for i,text in enumerate(lines):
        c.setFillColorRGB(.7,0,0) if text==DECLARATION else c.setFillColorRGB(0,0,0)
        c.setFont(font,9.5);c.drawString(40,802-i*23,text)
    c.showPage();c.save();return raw.getvalue()


def build_store(files):
    store=CaseStore();temporary=store.create_case('CASE-001 完全虚构，仅用于软件测试')
    case=store._cases.pop(temporary);case.case_id=CASE_ID;store._cases[CASE_ID]=case
    ids={}
    for did,(name,data) in files.items():ids[did]=store.attach_document(CASE_ID,name,data)
    return store,ids


def locate(store,ids,reference):
    doc=store.get_case(CASE_ID).documents[ids[reference['document_id']]];quote=reference['quote']
    matches=[(i,unit['text'].index(quote)) for i,unit in enumerate(doc.units) if unit['text'].count(quote)==1]
    total=sum(unit['text'].count(quote) for unit in doc.units)
    ensure(total==1 and len(matches)==1,'Gold引文不存在或不唯一：'+reference['document_id']+'，不模糊匹配')
    ui,start=matches[0];span=make_span(CASE_ID,doc,ui,start,start+len(quote),quote)
    sources=[s for s in build_sources(doc.as_record()) if s['unit_index']==ui and s['start']<=start and start+len(quote)<=s['start']+len(s['text']) and s['text'].count(quote)==1]
    ensure(len(sources)==1,'Gold引用跨源块或跨行；请保持独立完整引用，不自动拼接')
    return {'material_id':reference['document_id'],'file_name':doc.file_name,'document_id':doc.document_id,
            'file_sha256':doc.file_sha256,'parsed_text_sha256':doc.parsed_text_sha256,'parser_version':doc.parser_version,
            'unit_index':ui,'location':span.location,'start':span.start,'end':span.end,'quote':quote,
            'quote_sha256':digest(quote.encode()),'local_source_id':sources[0]['source_id'],
            'fixture_evidence_id':span.evidence_id,'fixture_case_id':CASE_ID}


def render_all():
    scenario=json.loads((SOURCE/'scenario.json').read_text());gold_spec=json.loads((SOURCE/'gold_specs.json').read_text())
    batch_spec=json.loads((SOURCE/'batch_specs.json').read_text())
    ensure(scenario['seed']==SEED and len(scenario['documents'])==8,'场景种子/文档数错误')
    ensure({d['id'] for d in scenario['documents']}=={f'D{i:02d}' for i in range(1,9)},'文档编号错误')
    rng=random.Random(SEED);tag='SIMGEN-'+f'{rng.getrandbits(32):08X}'
    files={};result={}
    for doc in scenario['documents']:
        lines=paragraphs(doc,tag);ensure(all('CASE-001-E01' in d['lead'] for d in scenario['documents']),'事故标识错误')
        data=(pdf_bytes(lines,doc['title']) if doc['format']=='pdf' else docx_bytes(lines,doc['title']))
        name=filename(doc);files[doc['id']]=(name,data);result['materials/'+name]=data
    store,ids=build_store(files)
    docs=store.get_case(CASE_ID).documents
    entries=[]
    for doc in scenario['documents']:
        name,data=files[doc['id']];snapshot=docs[ids[doc['id']]]
        text='\n'.join(u['text'] for u in snapshot.units)
        ensure('完全虚构，仅用于软件测试' in text,'缺少醒目虚构声明')
        ensure(snapshot.parse_report['status'] in ('parsed','partial') and bool(text.strip()),'标准材料未解析出正文')
        ensure(snapshot.parsed_text_sha256==snapshot_hash(snapshot.units),'解析快照哈希异常')
        ensure('08:30:20' not in text,'作者参考T0泄漏到盲测材料')
        ensure(len(build_sources(snapshot.as_record()))<=80 and len(text)<=8000,'单份材料超限，不截断')
        entries.append({'material_id':doc['id'],'path':'materials/'+name,'size':len(data),'sha256':digest(data),
                        'document_id':snapshot.document_id,'parsed_text_sha256':snapshot.parsed_text_sha256,
                        'parser_version':snapshot.parser_version,'status':snapshot.parse_report['status'],
                        'characters':sum(len(u['text']) for u in snapshot.units),'source_blocks':len(build_sources(snapshot.as_record())),
                        'issues':snapshot.parse_report['issues'],'requires_acknowledgement':snapshot.parse_report['requires_acknowledgement']})
    gold={'version':gold_spec['version'],'status':gold_spec['status'],'case_id':'CASE-001','logical_event_id':'CASE-001-E01',
          'provenance':'助手拟定的人工评审规范草案，非被测系统输出；仅引用定位与哈希由解析器计算，不从程序判断反推Gold',
          'coordinate_system':'unit_index和start/end从0开始；end不包含；Python Unicode字符偏移，非PDF字节或Word页码',
          'fixture_case_id':CASE_ID,'items':[]}
    for spec in gold_spec['items']:
        row=deepcopy(spec);row['citations']=[locate(store,ids,ref) for ref in spec['citations']]
        gold['items'].append(row)
    settings=Settings(provider=batch_spec['provider_for_budget'],model=batch_spec['model_for_budget'])
    observed=[];all_selected=set()
    for config in batch_spec['batches']:
        selected=config['documents'];ensure(2<=len(selected)<=4 and len(set(selected))==len(selected),'批次必须2—4份不重复材料')
        all_selected.update(selected)
        batch=prepare_case(store,CASE_ID,[ids[d] for d in selected],settings)
        request,budget=candidate_request_for(batch,settings);catalog=build_event_catalog(batch)
        observed.append({**config,'file_names':[files[d][0] for d in selected],
                         'preflight':{'passed':True,'original_characters':batch['input_chars'],'source_blocks':len(batch['sources']),
                                      'candidate_count':len(catalog['candidates']),**budget,'batch_sha256':batch['batch_sha256'],
                                      'required_coverage_acknowledgements':[d for d in selected if ids[d] in batch['required_ack']]},
                         'observed_candidate_coverage':{'available_candidate_ids':[c['candidate_id'] for c in catalog['candidates']],
                                                        'excluded_count':len(catalog['excluded']),
                                                        'not_a_complete_timeline':True}})
    ensure(all_selected==set(files),'未覆盖全部八份材料')
    try:prepare_case(store,CASE_ID,list(ids.values()),settings)
    except ValueError:whole_blocked=True
    else:whole_blocked=False
    ensure(whole_blocked,'八材料请求应在调用前拒绝')
    windows=[]
    for selected_batches in batch_spec['suggested_windows']:
        rows=[b for b in observed if b['id'] in selected_batches]
        chars=sum(b['preflight']['input_chars'] for b in rows);size=sum(b['preflight']['request_bytes'] for b in rows)
        ensure(len(rows)<=settings.hourly_limit and chars<=settings.hourly_input_chars and size<=settings.hourly_request_bytes,'建议窗口超默认额度；必须显式拆窗')
        windows.append({'batches':selected_batches,'planned_calls':len(rows),'input_characters':chars,'request_bytes':size,
                        'budget_only_not_authorized':True,'minimum_between_calls_seconds':settings.cooldown})
    # 仅验证两条可机械判定的有限规则，不冒充26项语义Gold全部自动通过。
    rule_checks=[]
    for item in gold['items']:
        check=item['offline_rule_check']
        if not check:continue
        if check['kind']=='dataset_hygiene':
            rule_checks.append({'gold_id':item['id'],'check':check,'passed':whole_blocked});continue
        a=next(c for c in item['citations'] if c['material_id']==check['left'])
        b=next(c for c in item['citations'] if c['material_id']==check['right'])
        eids=[]
        for ref in (a,b):eids.append(store.add_evidence(CASE_ID,ref['document_id'],ref['unit_index'],ref['start'],ref['end'],ref['quote']))
        view=review_pair(store,CASE_ID,*eids)
        if check['kind']=='time_pair':passed=view['time']['literal_delta_seconds']==check['literal_delta_seconds'] and view['time']['reliable_comparison'] is False
        else:passed=view['assessment_type']==check['assessment_type'] and view['predicate']['rule']==check['rule']
        ensure(passed,'有限规则回归不符：'+item['id']+'；不修改Gold或核心规则')
        rule_checks.append({'gold_id':item['id'],'check':check,'passed':True})
    result['gold_standard.json']=js(gold)
    markdown=['# CASE-001独立人工Gold Standard','',gold['provenance'],
              '禁止作为模型输入；不是被测系统输出，也不是外部专家认证。坐标为0基Unicode字符范围[start,end)。','']
    for row in gold['items']:
        markdown.extend(['## '+row['id']+'：'+row['expected_judgment'],'',
                         '类别：'+', '.join(row['test_categories']),'',
                         '审查理由：'+row['review_reason'],'',
                         '禁止推断：'+'；'.join(row['forbidden_inferences']),'',
                         '评测方式：'+row['evaluation_mode']+'；自动检查仅限明确列出的有限规则，不代表语义验收。',''])
        for ref in row['citations']:
            markdown.extend(['来源：'+ref['material_id']+' / '+ref['file_name'],
                             '位置：'+ref['location']+f"；unit_index={ref['unit_index']}；[{ref['start']},{ref['end']})",'',
                             '> '+ref['quote'],'','文件SHA256：'+ref['file_sha256'],
                             '解析快照SHA256：'+ref['parsed_text_sha256'],'引文SHA256：'+ref['quote_sha256'],''])
    result['gold_standard.md']=('\n'.join(markdown).rstrip()+'\n').encode()

    result['batches.json']=js({**batch_spec,'batches':observed,'budget_windows':windows,'eight_document_request_blocked':whole_blocked})
    result['offline_report.json']=js({'dataset_version':scenario['version'],'parsed_documents':len(entries),
       'gold_items':len(gold['items']),'all_citations_uniquely_bound':True,'all_batches_within_limits':True,
       'limited_rule_checks':rule_checks,'real_model_calls':0,'mock_model_calls':0,'quota_database_opened':False,
       'model_semantic_accuracy':'not_measured','manual_semantic_items_not_executed':[r['id'] for r in gold['items'] if not r['offline_rule_check']],
       'known_limits':['PDF表格覆盖仍未核验，必须确认风险；标准版只有文本层，不代表PDF无表格',
                       '首个保守事件候选不保证时间线完整；毫秒/相对EDR/复杂语义多需人工核查',
                       'command_id、二次引用、状态语义与证明独立性不在当前闭集规则完整覆盖内',
                       '本轮未执行任何真实或模拟模型响应验收，不给出模型成功率']})
    manifest={'version':'case001-manifest/1.0','dataset_id':'CASE-001','variant':'standard','seed':SEED,
       'generator_version':GENERATOR_VERSION,'baseline_sha':BASE_SHA,
       'environment':{'python':sys.version.split()[0],'zlib':zlib.ZLIB_RUNTIME_VERSION,
                      **{k:version(k) for k in ('reportlab','python-docx','pypdf','pydantic','openai')}},
       'determinism':'固定种子、PDF invariant、DOCX ZIP元数据；保证相同依赖/运行时下字节可重复，跨版本须复核',
       'metadata_policy':'PDF/DOCX技术创建时间固定用于可重复构建，不代表案发或文内编制时间',
       'input_sha256':{name:digest((SOURCE/name).read_bytes()) for name in ('DESIGN.md','scenario.json','gold_specs.json','batch_specs.json')},
       'generator_sha256':digest(Path(__file__).read_bytes()),'documents':entries,
       'blind_input_paths':[e['path'] for e in entries],
       'do_not_send_to_model':['DESIGN.md','gold_specs.json','gold_standard.json','gold_standard.md','batch_specs.json','batches.json','offline_report.json'],
       'generated_nonmaterial_sha256':{n:digest(b) for n,b in result.items() if not n.startswith('materials/')}}
    result['manifest.json']=js(manifest)
    result['SHA256SUMS']=(''.join(digest(data)+'  '+name+'\n' for name,data in sorted(result.items()))).encode()
    return result


def generate(output,check=False):
    output=Path(output).resolve();artifacts=render_all()
    if output.exists():
        actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
        ensure(actual<=set(artifacts),'目标含额外文件，拒绝混入或删除；请使用新目录')
        if check:ensure(actual==set(artifacts),'检查目录的文件集合不完整')
    for name,data in artifacts.items():
        path=output/name
        ensure(path.resolve().is_relative_to(output),'拒绝通过符号链接逃逸输出目录')
        if check:ensure(path.is_file() and path.read_bytes()==data,'生成校验不一致：'+name)
        else:
            ensure(not path.is_symlink(),'拒绝符号链接目标')
            if path.exists():ensure(path.read_bytes()==data,'拒绝覆盖不同版本文件：'+name+'；请在新目录生成并审查')
    if not check:
        for name,data in artifacts.items():
            path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return artifacts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=SOURCE/'standard')
    parser.add_argument('--check',action='store_true',help='重新生成到内存并逐字节比较，不写文件')
    args=parser.parse_args();files=generate(args.output,args.check)
    print(f'CASE-001：8份虚构材料，{len(files)}个标准版文件；真实模型调用0次；'+('校验通过' if args.check else '已生成'))


if __name__=='__main__':main()
