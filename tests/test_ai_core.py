"""Explicit synthetic fixtures and mocked responses: not a real-model accuracy evaluation."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import MagicMock
from dynamic_topics import discover_topics
from content_analysis import build_annotations,build_detail,pillar_summary,high_interaction
from ai_summary import build_summary
from ai_contract import SECTIONS,validate_response,ResponseError,render_sections
from ai_client import AIConfig,load_config,ask_ai,AIError,request_version
from cross_account_cases import CASES,case_notes


def fixture(case=None):
    case=case or CASES[1]
    notes=case_notes(case)
    snapshot={'name':case['name'],'account_id':case['name'],'bio':case['bio'],'notes':notes,
              'captured_at':'2026-09-29T12:00:00+08:00','source_kind':'测试样本'}
    frame=build_detail(notes,build_annotations(notes))
    analysis={'detail':frame,'identity':'个人创作者','domains':case['domains'],'goals':case['goals'],
              'commerce_enabled':'销售' in case['goals'],'metric':'互动总量','position':'秘密内部备注','audience':'内部人群判断',
              'diagnosis_note':'内部诊断','annotations':build_annotations(notes)}
    return snapshot,analysis


def response_for(summary, chat=False):
    result={section:[] for section in SECTIONS if (section=='answer')==chat}
    section='answer' if chat else 'profile'
    fact=summary['facts'][0]
    result[section]=[{'text':{f:'当前数据不足，暂无法判断。' for f in SECTIONS[section][2]},
                     'fact_ids':[fact['id']], 'note_ids':[], 'numbers':[{'fact_id':fact['id'],'value':fact['value'],'unit':fact['unit']}], 'quotes':[]}]
    return result


class SummaryTests(unittest.TestCase):
    def test_cross_domains_privacy_sampling_and_ids(self):
        for case in CASES:
            snap,analysis=fixture(case)
            summary=build_summary(snap,analysis,max_notes=3,body_chars=20)
            self.assertEqual(summary['total_notes'],8)
            self.assertEqual(len(summary['notes']),3)
            self.assertTrue(summary['sampling']['sampled'])
            self.assertNotIn('秘密内部备注',json.dumps(summary,ensure_ascii=False))
            self.assertEqual(len({n['id'] for n in summary['notes']}),3)
            repeated=build_summary(snap,analysis,max_notes=3,body_chars=20)
            self.assertEqual(summary,repeated)
            self.assertEqual(summary['current_profile']['confirmed_goals'],case['goals'])
            self.assertEqual(validate_response(response_for(summary),summary),response_for(summary))
            self.assertIn('profile',render_sections(response_for(summary),summary))

    def test_missing_imprecise_titles_unknown_scope(self):
        notes=[{'标题':'未知领域 星图边界','点赞':'1.2万'},{'标题':'未知领域 星图记录','点赞':0}]
        snap,analysis=fixture(); snap['notes']=notes
        analysis['detail']=build_detail(notes,build_annotations(notes))
        summary=build_summary(snap,analysis)
        self.assertEqual(summary['sampling']['missing_body_total'],2)
        self.assertEqual(next(c for c in summary['coverage'] if c['field']=='点赞')['valid'],1)
        self.assertFalse(any(f['label']=='平均藏赞比' for f in summary['facts']))
        self.assertEqual(summary['high_interaction']['valid'],0)

    def test_changed_unsent_note_and_account_invalidates(self):
        snap,a=fixture(); config=AIConfig()
        old=build_summary(snap,a,max_notes=3)
        a['detail'].loc[7,'正文']='已改动未发送正文'
        new=build_summary(snap,a,max_notes=3)
        self.assertNotEqual(request_version(old,config),request_version(new,config))
        snap['account_id']='另一个账号'
        other=build_summary(snap,a,max_notes=3)
        self.assertNotEqual(new['account_id'],other['account_id'])

    def test_fact_precision_quotes_and_fabricated_references(self):
        summary=build_summary(*fixture()); good=response_for(summary)
        for mutation in ['ref','value','unit','quote','prose']:
            bad=deepcopy(good); card=bad['profile'][0]
            if mutation=='ref': card['fact_ids']=['Ffake']
            if mutation=='value': card['numbers'][0]['value']=123456789
            if mutation=='unit': card['numbers'][0]['unit']='%'
            if mutation=='quote':
                card['note_ids']=[summary['notes'][0]['id']]
                card['quotes']=[{'note_id':card['note_ids'][0],'field':'body','quote':'虚构的连续摘录'}]
            if mutation=='prose': card['text']['核心方向']='平均点赞9999'
            with self.assertRaises(ResponseError,msg=mutation): validate_response(bad,summary)


class ClientTests(unittest.TestCase):
    def test_real_sdk_transport_mock_and_structure_failure(self):
        import openai
        import httpx2 as httpx
        summary=build_summary(*fixture()); config=AIConfig(api_key='fake-key')
        calls=[]
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,'status':'completed','model':config.model,
                'output':[{'type':'message','id':'msg_test','role':'assistant','status':'completed',
                           'content':[{'type':'output_text','text':json.dumps(response_for(summary)),'annotations':[]}]}]})
        def factory(**kwargs): return openai.OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        response=ask_ai(summary,config,client_factory=factory)
        self.assertEqual(len(calls),1)
        self.assertEqual(response['result'],response_for(summary))
        self.assertNotIn('tools',calls[0])
        self.assertEqual(calls[0]['text']['format']['type'],'json_schema')
        factory=MagicMock(); factory.return_value.__enter__.return_value.responses.create.return_value=SimpleNamespace(status='completed',output_text='not json')
        with self.assertRaises(AIError) as ctx: ask_ai(summary,config,client_factory=factory)
        self.assertEqual(ctx.exception.code,'structure')

    def test_config_no_secret_repr_missing_call(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'secrets.toml'
            config=load_config(path,{})
            with self.assertRaises(AIError) as ctx: ask_ai({},config)
            self.assertEqual(ctx.exception.code,'missing')
            config=load_config(path,{'OPENAI_API_KEY':'fake-secret','OPENAI_MODEL':'my-model'})
            self.assertNotIn('fake-secret',repr(config))
            self.assertNotIn('fake-secret',json.dumps(config.public()))
            path.write_text('OPENAI_TIMEOUT="wrong"')
            with self.assertRaises(AIError): load_config(path,{})

    def test_official_sdk_boundary_mocked(self):
        summary=build_summary(*fixture()); config=AIConfig(api_key='fake-secret')
        factory=MagicMock(); client=factory.return_value.__enter__.return_value
        client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(response_for(summary)),model='test',usage=None)
        result=ask_ai(summary,config,client_factory=factory)
        self.assertEqual(result['model'],config.model)
        self.assertIsNone(result['usage'])
        self.assertEqual(factory.call_args.kwargs['max_retries'],0)
        call=client.responses.create.call_args.kwargs
        self.assertFalse(call['store'])
        self.assertTrue(call['text']['format']['strict'])
        self.assertNotIn('fake-secret',json.dumps(result))

    def test_error_categories_and_bounded_input(self):
        import openai
        # SDK uses the bundled HTTP transport's Request/Response types, but exceptions only need attributes here.
        import httpx2 as httpx
        request=httpx.Request('POST','https://api.openai.com/v1/responses')
        summary=build_summary(*fixture()); config=AIConfig(api_key='fake')
        errors=[(openai.APITimeoutError(request=request),'timeout'),
                (openai.APIConnectionError(request=request),'network'),
                (openai.AuthenticationError('secret',response=httpx.Response(401,request=request),body={}), 'auth'),
                (openai.RateLimitError('secret',response=httpx.Response(429,request=request),body={'code':'insufficient_quota'}),'quota'),
                (openai.RateLimitError('secret',response=httpx.Response(429,request=request),body={}), 'rate_limit')]
        for error,code in errors:
            factory=MagicMock(); factory.return_value.__enter__.return_value.responses.create.side_effect=error
            with self.assertRaises(AIError) as ctx: ask_ai(summary,config,client_factory=factory)
            self.assertEqual(ctx.exception.code,code)
            self.assertNotIn('secret',str(ctx.exception))
        config.max_input_chars=20
        with self.assertRaises(AIError) as ctx: ask_ai(summary,config)
        self.assertEqual(ctx.exception.code,'input')


if __name__=='__main__': unittest.main()
