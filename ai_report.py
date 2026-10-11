"""Shared rendering for Excel and Markdown; drafts never silently become adopted results."""
import json
import pandas as pd
from ai_contract import SECTIONS


def report_tables(bundle):
    tables={}
    for kind,record in bundle.items():
        prefix='AI采纳' if kind=='accepted' else 'AI草稿附录'
        summary=record['summary']
        metadata={k:record.get(k) for k in ['status','generated_at','accepted_at','model','returned_model','version','app_version','prompt_version','contract_version','usage']}
        metadata.update(source=summary['source'],account_id=summary['account_id'],captured_at=summary['captured_at'],
                        total_notes=summary['total_notes'],selected_dates=summary['selected_dates'],sampling=summary['sampling'],
                        limits=summary['limits'],简介证据编号=summary.get('bio_id',''),已发送简介=summary.get('bio',''),
                        口径='藏赞比=收藏÷点赞；评赞比=评论÷点赞；本地计算。AI解释及用户采纳不代表因果已证实。')
        tables[prefix+'范围']=pd.DataFrame([{'项目':k,'内容':json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v} for k,v in metadata.items()])
        tables[prefix+'结论']=pd.DataFrame([{'模块':SECTIONS[k][0],'结论':text,'状态':record['status']} for k,text in record['sections'].items()])
        tables[prefix+'事实']=pd.DataFrame(summary['facts'])
        tables[prefix+'笔记证据']=pd.DataFrame(summary['notes'])
    return tables


def markdown_appendix(bundle):
    from html import escape
    lines=[]
    for title,table in report_tables(bundle).items():
        lines.append('## '+title)
        for row in table.to_dict('records'):
            lines.append('\n'.join(escape(str(k))+ '：'+escape(str(v)) for k,v in row.items()))
    return '\n\n'.join(lines)
