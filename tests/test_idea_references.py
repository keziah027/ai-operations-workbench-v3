import unittest
from unittest.mock import patch
from ai_ui import render_idea_references
from ai_contract import validate_response, ResponseError, SECTIONS
from test_ai_core import fixture, response_for
from ai_summary import build_summary
from prompts.analysis_prompts import ANALYZE_PROMPT

class IdeaReferenceTests(unittest.TestCase):
    def test_titles_ids_are_plain_text_in_card_order(self):
        summary={'notes':[{'id':'N1a2b','title':'清单标题'},{'id':'N2abc','title':'[链接文字](https://example.com)'}]}
        with patch('ai_ui.st') as ui:
            render_idea_references({'ideas':[{'note_ids':['N1a2b','N2abc','N1a2b']}]},summary)
            ui.text.assert_called_once_with('选题 1 · 参考笔记：清单标题（N1a2b）；[链接文字](https://example.com)（N2abc）')
            ui.markdown.assert_not_called()

    def test_missing_reference_has_no_empty_block(self):
        with patch('ai_ui.st') as ui:
            render_idea_references({'ideas':[{}, {'note_ids':[]}]},{'notes':[]})
            ui.text.assert_not_called()

    def test_existing_contract_rejects_unknown_and_accepts_known_ids(self):
        snapshot,analysis=fixture(); summary=build_summary(snapshot,analysis)
        result=response_for(summary)
        result['ideas']=[{'text':{field:'当前数据不足，暂无法判断。' for field in SECTIONS['ideas'][2]},
                          'fact_ids':[], 'note_ids':[], 'numbers':[], 'quotes':[]}]
        result['ideas'][0]['note_ids']=[summary['notes'][0]['id']]
        validate_response(result,summary)
        result['ideas'][0]['note_ids']=['Nnot_sent']
        with self.assertRaises(ResponseError): validate_response(result,summary)
        self.assertIn('编号仅放入 note_ids',ANALYZE_PROMPT)
