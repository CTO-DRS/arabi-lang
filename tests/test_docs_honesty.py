# -*- coding: utf-8 -*-
"""اختبارات التوثيق الصادق (الإصدار 1.33 — المرحلة 11).

طلب التدقيق (الفصل 18): «اختبار لقطة يتأكد أن إصدار LSP المعلن في
initialize يطابق __version__ — يمنع الانحراف مستقبلًا»، وقاعدة
«كل ترويسة وحدة تذكر سلوكها الفعلي لا نياتها».

فهذا الملف يثبّت السلوك الموثق:
- إصدار LSP المعلن = __version__ دائمًا (لا انحراف).
- المنسق يفعل ما يقول ترويسته حرفيًا: يصلح الإزاحة والتبويب والمسافات
  الطرفية، ويحفظ المسافات الداخلية كما كتبها الكاتب (سلوك موثق).
- مصفوفة CI والclassifiers متسقان (3.13 في الموضين — الفصل 17).
"""

import io
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import arabi_lang
from arabi_lang.tools import format_source


def _lsp_session(messages):
    """جلسة LSP مصغّرة — نفس نمط TestLsp في test_arabi.py."""
    from arabi_lang.lsp import ArabiLanguageServer, read_message
    stream_in = io.BytesIO()
    for m in messages:
        body = json.dumps(m, ensure_ascii=False).encode('utf-8')
        stream_in.write(f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii'))
        stream_in.write(body)
    stream_in.seek(0)
    out = io.BytesIO()
    ArabiLanguageServer(input_stream=stream_in, output_stream=out).run()
    out.seek(0)
    responses = []
    while True:
        r = read_message(out)
        if r is None:
            break
        responses.append(r)
    return responses


class TestLspVersionHonesty(unittest.TestCase):
    """الفصل 18 حرفيًا: إصدار initialize = __version__ — لا انحراف."""

    def test_initialize_version_matches_package(self):
        responses = _lsp_session([
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'shutdown', 'params': None},
            {'jsonrpc': '2.0', 'method': 'exit', 'params': None},
        ])
        init = next(r for r in responses
                    if r.get('id') == 1 and 'result' in r)
        info = init['result']['serverInfo']
        self.assertEqual(info['version'], arabi_lang.__version__,
                         'إصدار LSP المعلن انحرف عن __version__')
        self.assertEqual(info['name'], 'خادم لغة عربي')


class TestFormatterHonesty(unittest.TestCase):
    """المنسق يفعل ما تقوله ترويسته حرفيًا — سلوك مثبت باختبار."""

    def test_internal_spacing_preserved(self):
        """المسافات بين المعاملات داخل السطر تُحفظ — سلوك موثق لا وعد."""
        src = 'اطبع( "أ"  كما  كُتبت )\n'
        out, _changed = format_source(src)
        self.assertEqual(out, src)

    def test_trailing_whitespace_fixed(self):
        out, changed = format_source('اطبع("نهاية")   \n')
        self.assertEqual(out, 'اطبع("نهاية")\n')
        self.assertGreaterEqual(changed, 1)

    def test_tabs_become_spaces(self):
        out, _changed = format_source('لو صح:\n\tاطبع("تاب")\n')
        self.assertIn('\n    اطبع', out)
        self.assertNotIn('\t', out)


class TestCiClassifierConsistency(unittest.TestCase):
    """الفصل 17: 3.13 معلن في classifiers ومفحوص في CI معًا — لا ادعاء بلا فحص."""

    def test_313_in_classifiers_and_ci_matrix(self):
        with open(os.path.join(ROOT, 'pyproject.toml'),
                  encoding='utf-8') as f:
            pyproject = f.read()
        self.assertIn('"Programming Language :: Python :: 3.13"', pyproject)
        wf = os.path.join(ROOT, '.github', 'workflows', 'tests.yml')
        with open(wf, encoding='utf-8') as f:
            workflow = f.read()
        matrix = re.search(r"python-version:\s*\[(.*?)\]", workflow)
        self.assertIsNotNone(matrix, 'مصفوفة CI غير موجودة؟')
        self.assertIn("'3.13'", matrix.group(1),
                      'CI لا يفحص 3.13 بينما الclassifiers تدّعيه')

    def test_requires_python_matches_min_classifier(self):
        with open(os.path.join(ROOT, 'pyproject.toml'),
                  encoding='utf-8') as f:
            pyproject = f.read()
        self.assertIn('requires-python = ">=3.8"', pyproject)
        self.assertIn('"Programming Language :: Python :: 3.8"', pyproject)


if __name__ == '__main__':
    unittest.main()
