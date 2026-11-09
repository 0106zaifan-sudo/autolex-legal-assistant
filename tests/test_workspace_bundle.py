"""仅虚构四材料与本地AI Mock；工作包正反例不读写Secrets。"""
import io,json,stat,unittest,zipfile,hashlib
from copy import deepcopy
from unittest.mock import patch
import test_event_candidates as fixtures
from case_store import CaseStore


class WorkspaceBundle(unittest.TestCase):
    def setUp(self):
        import workspace_bundle as w
        self.w=w;self.helper=fixtures.EventCandidates();self.helper.setUp()
        self.addCleanup(self.helper.b.tmp.cleanup);self.helper.four()
        self.b=self.helper.b;self.store=self.b.store;self.cid=self.b.cid
        self.analysis=self.helper.analyze();self.b.m.import_case_analysis(self.store,self.cid,self.analysis)
        fact=next(s for s in self.store.get_case(self.cid).facts if '08:30' in s.text)
        self.store.confirm_fact(self.cid,fact.statement_id,'模拟复核员','仅用于虚构工作包测试的人工复核记录')
        refs=[]
        for s in self.b.batch['sources']:
            if '事件编号' in s['text']:
                refs.append(self.store.add_evidence(self.cid,s['document_id'],s['unit_index'],s['start'],s['end'],s['text']))
        self.store.discover_relations(self.cid)
        rid=self.store.get_case(self.cid).relations[0].relation_id
        self.store.review_relation(self.cid,rid,'needs_review','needs_verification','模拟甲','时钟及来源待核对')
        self.store.review_relation(self.cid,rid,'modified','related','模拟乙','保留原候选与复核链')
        self.store.record_missing(self.cid,'模拟核查原始日志是否另有提供',self.b.ids)

    def pack(self,analysis=False):
        return self.w.export_workspace(self.store,self.cid,analysis=self.analysis if analysis else None)

    def entries(self,data=None):
        with zipfile.ZipFile(io.BytesIO(self.pack() if data is None else data)) as z:
            return {n:z.read(n) for n in z.namelist()}

    def rewrite(self,entries,compression=zipfile.ZIP_STORED):
        manifest=json.loads(entries['manifest.json'])
        for row in manifest['members']:
            if row['path'] in entries:
                row['size']=len(entries[row['path']]);row['sha256']=hashlib.sha256(entries[row['path']]).hexdigest()
        entries['manifest.json']=json.dumps(manifest,ensure_ascii=False).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',compression) as z:
            for n,b in entries.items():z.writestr(n,b)
        return out.getvalue()

    def mutate_case(self,callback):
        entries=self.entries();payload=json.loads(entries['case.json']);callback(payload)
        entries['case.json']=json.dumps(payload,ensure_ascii=False).encode()
        return self.rewrite(entries)

    def reject(self,data,code=None):
        target=CaseStore();existing=target.create_case('模拟已有案件');before=target.export_json(existing)
        with self.assertRaises(self.w.WorkspaceError) as caught:self.w.restore_workspace(target,data)
        if code:self.assertEqual(caught.exception.code,code)
        self.assertEqual(target.list_cases(),{existing:'模拟已有案件'})
        self.assertEqual(target.export_json(existing),before)

    def test_four_documents_roundtrip_exact_case_and_original_bytes(self):
        data=self.pack();expected=self.store.export_json(self.cid);target=CaseStore()
        result=self.w.restore_workspace(target,data)
        self.assertEqual(result['case_id'],self.cid);self.assertIsNone(result['analysis'])
        self.assertEqual(target.export_json(self.cid),expected)
        for did in self.b.ids:self.assertEqual(target.get_original(self.cid,did),self.store.get_original(self.cid,did))
        self.assertEqual(len(target.get_case(self.cid).timeline),4)
        self.assertEqual(len(target.get_case(self.cid).relation_reviews),2)

    def test_explicit_analysis_inclusion_is_verified_but_not_auto_imported(self):
        target=CaseStore();result=self.w.restore_workspace(target,self.pack(analysis=True))
        self.assertEqual(result['analysis'],self.analysis)
        self.assertEqual(target.export_json(self.cid),self.store.export_json(self.cid))
        self.assertNotIn('authorized_batch',result)

    def test_no_analysis_cache_is_assumed(self):
        entries=self.entries();self.assertNotIn('analysis.json',entries)
        self.assertEqual(set(entries),{'manifest.json','case.json'}|{n for n in entries if n.startswith('files/')})
        self.assertFalse(any(n.endswith('.sqlite3') or 'secret' in n.lower() for n in entries))

    def test_missing_original_file_rejected(self):
        entries=self.entries();del entries[next(n for n in entries if n.startswith('files/'))]
        self.reject(self.rewrite(entries))

    def test_tampered_original_hash_rejected(self):
        entries=self.entries();name=next(n for n in entries if n.startswith('files/'));entries[name]+=b'tampered'
        self.reject(self.rewrite(entries))

    def test_bad_manifest_hash_rejected(self):
        entries=self.entries();manifest=json.loads(entries['manifest.json']);manifest['members'][0]['sha256']='0'*64
        entries['manifest.json']=json.dumps(manifest).encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for n,b in entries.items():z.writestr(n,b)
        self.reject(out.getvalue())

    def test_tampered_quote_rejected_even_after_manifest_rehash(self):
        self.reject(self.mutate_case(lambda p:p['evidence'][next(iter(p['evidence']))].update(quote='伪造引文')))

    def test_snapshot_or_parser_change_rejected(self):
        for field,value in [('parsed_text_sha256','0'*64),('parser_version','unknown-parser')]:
            self.reject(self.mutate_case(lambda p:p['documents'][next(iter(p['documents']))].update({field:value})))

    def test_units_and_parse_report_tampering_rejected(self):
        self.reject(self.mutate_case(lambda p:p['documents'][next(iter(p['documents']))]['parse_report'].update(status='failed')))

    def test_cross_case_evidence_rejected(self):
        self.reject(self.mutate_case(lambda p:p['evidence'][next(iter(p['evidence']))].update(case_id='case_'+'0'*32)))

    def test_missing_statement_reference_rejected(self):
        self.reject(self.mutate_case(lambda p:p['facts'][0].update(evidence_ids=['evidence_foreign'])))

    def test_claim_promoted_to_confirmed_fact_rejected(self):
        def change(p):
            row=p['claims'].pop();row.update(kind='confirmed_fact',verification='human_confirmed');p['facts'].append(row)
        self.reject(self.mutate_case(change))

    def test_confirmed_fact_without_review_rejected(self):
        self.reject(self.mutate_case(lambda p:p.update(reviews=[])))

    def test_forged_dangling_human_review_rejected(self):
        self.reject(self.mutate_case(lambda p:p['reviews'][0].update(statement_id='statement_foreign')))

    def test_forged_review_chain_or_duplicate_id_rejected(self):
        self.reject(self.mutate_case(lambda p:p['relation_reviews'][1].update(previous_review_id=None)))
        self.reject(self.mutate_case(lambda p:p['relation_reviews'][1].update(review_id=p['relation_reviews'][0]['review_id'])))

    def test_relation_cross_document_binding_rejected(self):
        self.reject(self.mutate_case(lambda p:p['relations'][0].update(right_id=p['relations'][0]['left_id'])))

    def test_timeline_time_or_identity_tampering_rejected(self):
        self.reject(self.mutate_case(lambda p:p['timeline'][0].update(time_text='2099年1月1日')))
        self.reject(self.mutate_case(lambda p:p['timeline'][0].update(source_event_id='event_fake')))

    def test_pending_item_cross_document_rejected(self):
        self.reject(self.mutate_case(lambda p:p['pending_items'][0].update(document_ids=['foreign-document'])))

    def test_receipt_for_other_case_or_credentials_rejected(self):
        self.reject(self.mutate_case(lambda p:p['analysis_receipts'][0].update(case_id='foreign-case')))
        self.reject(self.mutate_case(lambda p:p['analysis_receipts'][0].update(api_key='not-for-export')))
        self.reject(self.mutate_case(lambda p:p['analysis_receipts'][0].update(candidate_selection_ids=['CE_'+'0'*24])))

    def test_duplicate_import_never_overwrites(self):
        target=CaseStore();data=self.pack();self.w.restore_workspace(target,data);before=target.export_json(self.cid)
        with self.assertRaises(self.w.WorkspaceError):self.w.restore_workspace(target,data)
        self.assertEqual(target.export_json(self.cid),before)

    def test_bad_zip_and_unknown_format_rejected(self):
        self.reject(b'not a zip')
        entries=self.entries();manifest=json.loads(entries['manifest.json']);manifest['format_version']='workspace/future'
        entries['manifest.json']=json.dumps(manifest).encode();self.reject(self.rewrite(entries))

    def test_traversal_absolute_backslash_and_extra_entries_rejected(self):
        for name in ['../case.json','/absolute.pdf','files\\evil.pdf','secrets.toml','quota.sqlite3']:
            entries=self.entries();entries[name]=b'forbidden';self.reject(self.rewrite(entries))

    def test_duplicate_zip_entry_rejected(self):
        out=io.BytesIO();data=self.pack()
        with zipfile.ZipFile(out,'w') as z:
            for n,b in self.entries(data).items():z.writestr(n,b)
            import warnings
            with warnings.catch_warnings():warnings.simplefilter('ignore');z.writestr('case.json',b'{}')
        self.reject(out.getvalue())

    def test_symlink_zip_entry_rejected(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for n,b in self.entries().items():
                info=zipfile.ZipInfo(n)
                if n=='case.json':info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(info,b)
        self.reject(out.getvalue())

    def test_size_entry_count_and_ratio_limits_prevent_import(self):
        data=self.pack()
        for name,value in [('MAX_ZIP_BYTES',len(data)-1),('MAX_EXPANDED_BYTES',10),('MAX_ENTRIES',1),('MAX_RATIO',0.1)]:
            with patch.object(self.w,name,value):self.reject(data)

    def test_encrypted_flag_rejected(self):
        # 标记ZIP local+central encrypted位；在尝试解密前拒绝。
        data=bytearray(self.pack())
        for signature,offset in [(b'PK\x03\x04',6),(b'PK\x01\x02',8)]:
            pos=0
            while True:
                pos=data.find(signature,pos)
                if pos<0:break
                data[pos+offset]|=1;pos+=4
        self.reject(bytes(data))

    def test_optional_analysis_tamper_rejected_and_no_fake_pass(self):
        entries=self.entries(self.pack(analysis=True));p=json.loads(entries['analysis.json'])
        p['raw_output']['timeline'][0]['text']='伪造恢复引文';entries['analysis.json']=json.dumps(p).encode()
        self.reject(self.rewrite(entries))
        entries=self.entries(self.pack(analysis=True));p=json.loads(entries['analysis.json'])
        p['receipt']['case_id']='foreign-case';entries['analysis.json']=json.dumps(p).encode()
        self.reject(self.rewrite(entries))

    def test_export_refuses_corrupt_in_memory_case(self):
        doc=self.store._cases[self.cid].documents[self.b.ids[0]];doc.original_bytes=b'corrupt'
        with self.assertRaises(self.w.WorkspaceError):self.pack()

    def test_legacy_json_plus_exact_originals_uses_same_verification(self):
        target=CaseStore();files={d.file_name:d.original_bytes for d in self.store.get_case(self.cid).documents.values()}
        result=self.w.restore_legacy(target,self.store.export_json(self.cid).encode(),files)
        self.assertEqual(result['case_id'],self.cid)
        self.assertEqual(target.export_json(self.cid),self.store.export_json(self.cid))

    def test_legacy_missing_file_duplicate_names_or_unknown_version_rejected(self):
        files={d.file_name:d.original_bytes for d in self.store.get_case(self.cid).documents.values()};files.pop(next(iter(files)))
        with self.assertRaises(self.w.WorkspaceError):self.w.restore_legacy(CaseStore(),self.store.export_json(self.cid).encode(),files)
        p=json.loads(self.store.export_json(self.cid));p['schema_version']='99'
        with self.assertRaises(self.w.WorkspaceError):self.w.restore_legacy(CaseStore(),json.dumps(p).encode(),{})

    def test_wrong_document_extension_or_extra_original_rejected(self):
        entries=self.entries();entries['files/'+'0'*64+'.pdf']=b'fake'
        self.reject(self.rewrite(entries))
        self.reject(self.mutate_case(lambda p:p['documents'][next(iter(p['documents']))].update(file_name='../secret.pdf')))

    def test_zip_prefix_trailer_and_mismatched_local_flags_rejected(self):
        data=self.pack();self.reject(b'EXE'+data);self.reject(data+b'garbage')
        data=bytearray(data);data[6]^=1;self.reject(bytes(data))

    def test_unknown_case_schema_and_extra_auth_fields_rejected(self):
        self.reject(self.mutate_case(lambda p:p.update(schema_version='1.0')))
        self.reject(self.mutate_case(lambda p:p.update(authenticated=True)))
        self.reject(self.mutate_case(lambda p:p.pop('facts')))

    def test_duplicate_json_keys_rejected(self):
        entries=self.entries();entries['case.json']=entries['case.json'][:-1]+b',"case_id":"fake"}'
        self.reject(self.rewrite(entries))

    def test_docx_internal_symlink_and_bomb_limits_checked(self):
        doc=next(d for d in self.store.get_case(self.cid).documents.values() if d.file_name.endswith('.docx'))
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(doc.original_bytes)) as source,zipfile.ZipFile(out,'w') as target:
            for info in source.infolist():
                new=zipfile.ZipInfo(info.filename)
                if info.filename=='word/document.xml':new.create_system=3;new.external_attr=(stat.S_IFLNK|0o777)<<16
                target.writestr(new,source.read(info))
        with self.assertRaises(self.w.WorkspaceError):self.w.check_original(doc.file_name,out.getvalue())
        with patch.object(self.w,'MAX_EXPANDED_BYTES',10),self.assertRaises(self.w.WorkspaceError):self.w.check_original(doc.file_name,doc.original_bytes)
        for encoding in ('utf-8','utf-16'):
            out=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(doc.original_bytes)) as source,zipfile.ZipFile(out,'w') as target:
                for info in source.infolist():
                    content=source.read(info)
                    if info.filename=='word/document.xml':content=('<?xml version="1.0" encoding="'+encoding+'"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///never-read">]><x>&e;</x>').encode(encoding)
                    target.writestr(info.filename,content)
            with self.assertRaises(self.w.WorkspaceError) as caught:self.w.check_original(doc.file_name,out.getvalue())
            self.assertEqual(caught.exception.code,'xml_entities_forbidden')


    def test_dangling_pending_review_and_coverage_reference_rejected(self):
        self.reject(self.mutate_case(lambda p:p['pending_items'].append({'pending_id':'review_fake','kind':'ai_inference_review','text':'假的待核查问题','document_ids':list(p['documents']),'evidence_ids':[],'coverage_refs':[],'status':'open','value':None})))
        self.reject(self.mutate_case(lambda p:p['pending_items'].append({'pending_id':'pending_fake','kind':'coverage_gap','text':'假的覆盖缺口','document_ids':list(p['documents']),'evidence_ids':[],'coverage_refs':[{'document_id':next(iter(p['documents'])),'coverage_id':'C9999','code':'fake','location':'文件'}],'status':'open','value':None})))

    def test_invalid_review_timestamp_and_blank_reviewer_rejected(self):
        self.reject(self.mutate_case(lambda p:p['reviews'][0].update(reviewed_at='not-a-time')))
        self.reject(self.mutate_case(lambda p:p['relation_reviews'][0].update(reviewer='  ')))

    def test_changed_statement_identity_or_basic_info_rejected(self):
        self.reject(self.mutate_case(lambda p:p['facts'][0].update(statement_id='statement_fake')))
        self.reject(self.mutate_case(lambda p:p['basic_info']['事故日期'].update(value='编造日期',status='unverified',evidence_ids=list(p['evidence'])[:1])))

    def test_ai_origins_and_inference_survive_revalidation(self):
        b=self.b;p=self.helper.payload()
        left=next(s for s in b.batch['sources'] if '现场记录：' in s['text']);right=next(s for s in b.batch['sources'] if '摘要：' in s['text'])
        p['relations']=[{'left':{'source_id':left['source_id'],'quote':left['text']},'right':{'source_id':right['source_id'],'quote':right['text']},
                         'relation_type':'needs_verification','reasoning':'待核实推断：两份碰撞时间记录的差异是否需要核对？'}]
        p['pending_evidence']=[{'kind':'推断','text':'原始日志未提供。','reasoning':'待核实推断：原始日志是否另有提供？',
                                'sources':[{'source_id':right['source_id'],'quote':right['text']}]}]
        import time
        with patch('security.time.time',return_value=time.time()+2):analysis=self.helper.analyze(p)
        b.m.import_case_analysis(self.store,self.cid,analysis)
        target=CaseStore();self.w.restore_workspace(target,self.pack())
        self.assertEqual(target.export_json(self.cid),self.store.export_json(self.cid))
        self.assertTrue(target.get_case(self.cid).inferences)
        relation=next(r for r in target.get_case(self.cid).relations if r.ai_origins)
        self.assertEqual(relation.ai_origins[0]['reasoning'],p['relations'][0]['reasoning'])
        self.reject(self.mutate_case(lambda d:next(r for r in d['relations'] if r.get('ai_origins'))['ai_origins'][0]['left'].update(quote='假的原始建议')))

    def test_empty_case_roundtrip_and_file_count_limit(self):
        empty=CaseStore();cid=empty.create_case('模拟空案件');target=CaseStore()
        self.w.restore_workspace(target,self.w.export_workspace(empty,cid))
        self.assertEqual(target.export_json(cid),empty.export_json(cid))
        with patch.object(self.w,'MAX_DOCUMENTS',1),self.assertRaises(self.w.WorkspaceError):self.pack()

    def test_safe_error_never_echoes_untrusted_case_text(self):
        data=self.mutate_case(lambda p:p['evidence'][next(iter(p['evidence']))].update(quote='SECRET_PRIVATE_QUOTE_DO_NOT_LOG'))
        with self.assertRaises(self.w.WorkspaceError) as caught:self.w.restore_workspace(CaseStore(),data)
        self.assertNotIn('SECRET_PRIVATE',str(caught.exception))

    def test_restore_does_not_touch_quota_store_or_ai(self):
        with patch('security.QuotaStore',side_effect=AssertionError('must not restore quotas')),patch('multidoc_ai.invoke',side_effect=AssertionError('no model calls')):
            self.w.restore_workspace(CaseStore(),self.pack(analysis=True))

    def test_legacy_duplicate_saved_filenames_and_changed_parser_rejected(self):
        payload=json.loads(self.store.export_json(self.cid));docs=list(payload['documents'].values());docs[1]['file_name']=docs[0]['file_name']
        with self.assertRaises(self.w.WorkspaceError):self.w.restore_legacy(CaseStore(),json.dumps(payload).encode(),{})
        payload=json.loads(self.store.export_json(self.cid));next(iter(payload['documents'].values()))['parser_version']='future'
        files={d.file_name:d.original_bytes for d in self.store.get_case(self.cid).documents.values()}
        with self.assertRaises(self.w.WorkspaceError):self.w.restore_legacy(CaseStore(),json.dumps(payload).encode(),files)

    def test_concurrent_imports_cannot_overwrite_case_id(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        data=self.pack();target=CaseStore();barrier=threading.Barrier(2);original=self.w.stage_case
        def stage(*a,**k):
            result=original(*a,**k);barrier.wait(timeout=10);return result
        def restore():
            try:return self.w.restore_workspace(target,data)['case_id']
            except self.w.WorkspaceError as e:return e.code
        with patch.object(self.w,'stage_case',side_effect=stage),ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda _:restore(),range(2)))
        self.assertEqual(sorted(outcomes),sorted([self.cid,'case_id_conflict']))
        self.assertEqual(target.export_json(self.cid),self.store.export_json(self.cid))
