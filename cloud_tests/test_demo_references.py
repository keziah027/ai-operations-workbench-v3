import unittest
from ai_client import AIConfig
from demo_ai import demo_response
from ai_contract import validate_response

class DemoReferenceTests(unittest.TestCase):
    def test_only_sent_notes_with_exact_facts_are_ranked(self):
        summary={'notes':[{'id':'Na','title':'甲','body':''},{'id':'Nb','title':'乙','body':''},{'id':'Nc','title':'丙','body':''}],
                 'facts':[{'id':'Fabc','label':'笔记Na：点赞','value':3,'unit':'次'},
                          {'id':'Fdef','label':'笔记Nc：点赞','value':9,'unit':'次'},
                          {'id':'Faaa','label':'笔记Nnot_sent：点赞','value':999,'unit':'次'}]}
        result=demo_response(summary,AIConfig())['result']
        self.assertEqual(result['ideas'][0]['note_ids'],['Nc','Na'])
        validate_response(result,summary)
        summary['facts']=[]
        result=demo_response(summary,AIConfig())['result']
        self.assertEqual(result['ideas'][0]['note_ids'],[])
