"""AppTest仅使用显式虚构配置，不解析磁盘Secrets或读取宿主Codespaces凭据。"""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
import streamlit as st
from streamlit.runtime.secrets import Secrets
from ai_providers import codespaces_values


@contextmanager
def isolated_ui_runtime(*, environment=None):
    # AppTest在at.secrets为空时沿用全局st.secrets；预置内存空值阻断磁盘解析。
    memory_secrets = Secrets()
    memory_secrets._secrets = {}
    simulated_environment = {} if environment is None else dict(environment)
    with patch.object(st,'secrets',memory_secrets), \
         patch.object(Secrets,'_parse_file_path',side_effect=AssertionError('UI tests must not parse local Secrets')) as disk, \
         patch('ai_ui.codespaces_values',side_effect=lambda values,_host: codespaces_values(values,simulated_environment)), \
         patch('ai_analysis.invoke',side_effect=AssertionError('UI tests must not call model runtime')) as model, \
         patch('multidoc_ai.invoke',side_effect=AssertionError('UI tests must not call multidoc runtime')) as multimodel:
        try:
            yield
        finally:
            disk.assert_not_called()
            model.assert_not_called()
            multimodel.assert_not_called()


class IsolatedUITestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(isolated_ui_runtime())
