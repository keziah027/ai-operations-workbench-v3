"""规范化账号/笔记标识；去掉链接签名对身份的影响。"""
import hashlib
import re
from urllib.parse import urlsplit
from state_codec import plain

def digest(value): return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:20]

def platform_note_id(note):
    for key in ['笔记ID','笔记id','note_id','noteId']:
        value=plain(note.get(key))
        value='' if value is None else str(value).strip()
        if value and value.lower() not in ['nan','none','<na>']: return value
    try:
        value=plain(note.get('笔记链接'))
        parsed=urlsplit('' if value is None else str(value))
        if parsed.hostname=='xiaohongshu.com' or (parsed.hostname or '').endswith('.xiaohongshu.com'):
            found=re.search(r'/(?:explore|discovery/item)/([a-zA-Z0-9_-]+)',parsed.path)
            if found: return found[1]
    except ValueError: pass
    return ''

def evidence_id(note,index):
    return 'xhs:'+platform_note_id(note) if platform_note_id(note) else str(note.get('_note_id') or f"row:{note.get('序号',index+1)}")
