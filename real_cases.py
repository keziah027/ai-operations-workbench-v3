"""Curated, dated account snapshots; never synthesize missing operating metrics."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent / 'case_studies'
NOTICE = '真实账号公开信息快照，仅用于案例分析；不是实时数据，不代表账号全部历史或本项目的运营成果。'


def validate_case(case):
    """Only curated on-disk cases enter this catalogue; no visitor credentials."""
    if not isinstance(case, dict) or case.get('data_kind') != 'real_public_snapshot':
        raise ValueError('真实案例必须声明数据性质。')
    for field in ('id', 'name', 'url', 'captured_at', 'scope', 'collection_method'):
        if not isinstance(case.get(field), str) or not case[field].strip():
            raise ValueError('真实案例缺少来源字段：' + field)
    from account_reader import validate_profile_url
    url = validate_profile_url(case['url'])
    if url != case['url'] or urlsplit(url).query or urlsplit(url).fragment or urlsplit(url).hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}:
        raise ValueError('案例必须保留可追溯的完整账号主页地址。')
    captured = datetime.fromisoformat(case['captured_at'])
    if captured.tzinfo is None:
        raise ValueError('采集时间必须包含时区。')
    if not isinstance(case.get('notes'), list) or not 1 <= len(case['notes']) <= 100:
        raise ValueError('案例必须包含 1～100 篇实际读取的笔记。')
    from account_batch import valid_note_url, note_identity
    excluded = {note_identity(row.get('url', '')) for row in case.get('excluded_pinned', [])}
    for note in case['notes']:
        if not isinstance(note, dict) or not str(note.get('标题', '')).strip():
            raise ValueError('笔记缺少实际标题。')
        if not valid_note_url(note.get('笔记链接', '')):
            raise ValueError('每篇笔记必须保留公开来源链接。')
        if urlsplit(note['笔记链接']).query or urlsplit(note['笔记链接']).fragment:
            raise ValueError('公开案例链接不能包含访问令牌或请求签名。')
        if case.get('exclude_pinned'):
            if note.get('是否置顶') is not False or not note.get('置顶核验时间') or not note.get('置顶核验依据'):
                raise ValueError('非置顶案例的每篇笔记必须提供核验记录。')
            if note_identity(note['笔记链接']) in excluded:
                raise ValueError('已排除的置顶笔记不能进入案例分析。')
    from state_codec import without_secrets
    if without_secrets(case) != case:
        raise ValueError('案例包含登录或敏感配置字段，不能公开展示。')
    return case


def list_cases(root=ROOT):
    if not Path(root).exists():
        return []
    cases = [validate_case(json.loads(path.read_text(encoding='utf-8')))
             for path in sorted(Path(root).glob('*.json'))]
    return sorted(cases, key=lambda case: (case.get('display_order', 0), case['id']))


def case_snapshot(case):
    result = deepcopy(validate_case(case))
    result.update(is_demo=False, is_case_study=True, source_kind='真实账号公开快照（案例展示，非实时）')
    result['scope'] += '\n' + NOTICE
    result['warnings'] = [NOTICE, *result.get('warnings', [])]
    for note in result['notes']:
        note['数据性质'] = NOTICE
    return result
