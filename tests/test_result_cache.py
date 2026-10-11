from copy import deepcopy
from unittest.mock import patch
import unittest
import numpy as np
import pandas as pd
from result_cache import BoundedCache,report_bytes,export_payload
from state_codec import fingerprint,encoded

class CacheTests(unittest.TestCase):
    def test_text_only_changes_recompute_features(self):
        import content_analysis as core
        notes=[{'标题':'给新手的清单','正文':'如何复盘','点赞':1,'收藏':0,'评论':0}]
        annotations=core.build_annotations(notes)
        with patch.object(core,'TEXT_CACHE',BoundedCache()),patch.object(core,'detect_features',wraps=core.detect_features) as detect:
            core.build_detail(notes,annotations); count=detect.call_count
            notes[0]['点赞']=999;core.build_detail(notes,annotations)
            self.assertEqual(detect.call_count,count)
            notes[0]['正文']='如何面试';core.build_detail(notes,annotations)
            self.assertGreater(detect.call_count,count)

    def test_stable_nan_numeric_dataframe_and_dict_order(self):
        a={'z':pd.DataFrame({'x':[1.,np.nan]}),'a':pd.NA}
        b={'a':None,'z':pd.DataFrame({'x':[1,None]},index=[3,4])}
        self.assertEqual(fingerprint(a),fingerprint(b))

    def test_bounded_lru_and_failure_retry(self):
        cache=BoundedCache(max_entries=2,max_bytes=1000); calls=[]
        def build(): calls.append(1); return b'valid'
        self.assertEqual(cache.get('a',1,build),cache.get('a',1,build)); self.assertEqual(len(calls),1)
        cache.get('a',2,build);cache.get('a',3,build)
        self.assertEqual(len(cache.entries),2)
        with self.assertRaises(ValueError): cache.get('fail',1,lambda:(_ for _ in ()).throw(ValueError('test')))
        self.assertEqual(cache.get('fail',1,build),b'valid')
        self.assertEqual(cache.failures,1)
        cache.get('big',1,lambda:b'x'*2000)
        self.assertLessEqual(cache.bytes,1000)

    def test_export_all_semantic_changes_and_no_account_leak(self):
        snapshot={'name':'账号甲','source_kind':'Excel上传','captured_at':'fixed','scope':'本次8篇',
                  'notes':[{'标题':'原题','正文':'正文','点赞':1}], 'creator_data':{'overview':{'period':'7日','metrics':[1]}}}
        analysis={'position':'定位','audience':'假设','diagnosis_note':'补充','analysis_goals':['涨粉'],'metric':'点赞',
                  'annotations':pd.DataFrame([{'主支柱':'A','封面观察':'观察','封面辅助标签':'文字密集'}]),
                  'editing':{'revision':1,'undo':None,'packaging':{'cover_types':['待标注','自定义']}},
                  'final_topics':pd.DataFrame([{'主题ID':'a','最终主题':'A'}]),'diagnosis':pd.DataFrame([{'观察':'原结论'}])}
        cache=BoundedCache(); calls=[]
        def writer(s,a): calls.append(1);return encoded(export_payload(s,a)).encode()
        with patch('excel_export.public_workbook',side_effect=writer):
            original=report_bytes(cache,snapshot,analysis,lambda s,a:a['position'])
            self.assertEqual(original,report_bytes(cache,deepcopy(snapshot),deepcopy(analysis),lambda s,a:a['position']))
            self.assertEqual(len(calls),1)
            mutations=[('position','新定位'),('audience','新假设'),('diagnosis_note','新补充'),('metric','评论'),('analysis_goals',['咨询'])]
            for field,value in mutations:
                changed=deepcopy(analysis);changed[field]=value
                self.assertNotEqual(original[0],report_bytes(cache,snapshot,changed,lambda s,a:a['position'])[0])
            for field,value in [('name','账号乙'),('scope','部分样本'),('source_kind','公开账号'),('notes',[{'标题':'更改','点赞':2}]),('creator_data',{'overview':{'period':'30日'}})]:
                changed=deepcopy(snapshot);changed[field]=value
                self.assertNotEqual(original[0],report_bytes(cache,changed,analysis,lambda s,a:a['position'])[0])
            changed=deepcopy(analysis);changed['annotations'].loc[0,'主支柱']='B'
            self.assertNotEqual(original[0],report_bytes(cache,snapshot,changed,lambda s,a:a['position'])[0])
            changed=deepcopy(analysis);changed['editing']['packaging']['cover_types'].append('新类型')
            self.assertNotEqual(original[0],report_bytes(cache,snapshot,changed,lambda s,a:a['position'])[0])
            report_bytes(cache,snapshot,analysis,lambda s,a:a['position']); count=len(calls)
            changed=deepcopy(analysis);changed['editing']['revision']=999
            report_bytes(cache,snapshot,changed,lambda s,a:a['position'])
            self.assertEqual(len(calls),count)
