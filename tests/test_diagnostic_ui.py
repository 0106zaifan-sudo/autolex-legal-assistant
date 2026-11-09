import json,sys
from unittest.mock import patch
from ui_isolation import IsolatedUITestCase
import test_multidoc_ui as fixtures
from multidoc_ai import prepare_case,MultiAIError

class DiagnosticUI(IsolatedUITestCase):
 def test_safe_failure_receipt_is_visible_and_downloadable(self):
  # AppTest replaces __main__; restore it before later spawn-based deadline tests.
  original_main=sys.modules["__main__"]
  self.addCleanup(sys.modules.__setitem__,"__main__",original_main)
  helper=fixtures.JointUI()
  app,store,cid,ids=helper.app()
  settings=app.session_state['settings'];batch=prepare_case(store,cid,ids[:2],settings)
  receipt={'case_id':cid,'batch_sha256':batch['batch_sha256'],'provider_status':'completed','format_status':'passed','evidence_status':'failed',
           'token_usage':{'total_tokens':121},'validation_diagnostic':{'stage':'document_binding','section':'timeline','item_index':0,'rule':'timeline_multi_sentence','source_ids':[batch['sources'][0]['source_id']]}}
  with patch('multidoc_ui.analyze_case',side_effect=MultiAIError(receipt=receipt)),patch('multidoc_ui.QuotaStore'):
   app.checkbox(key='md_consent').check().run();app.button(key='run_multidoc_ai').click().run()
  self.assertFalse(app.exception)
  self.assertTrue(any('timeline_multi_sentence' in item.value for item in app.json))
  self.assertTrue(any('下载联合验证安全回执' in element.proto.label for element in app.get('download_button')))
  self.assertFalse(store.get_case(cid).relations)
