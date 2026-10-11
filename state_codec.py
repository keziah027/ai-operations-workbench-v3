"""用于存档与内容指纹的确定性 JSON 数据，不加载可执行对象。"""
from datetime import date,datetime
import hashlib
import json
import math
import pandas as pd

def plain(value):
    if isinstance(value,pd.DataFrame):
        return {'columns':list(value.columns),'records':plain(value.to_dict('records'))}
    if isinstance(value,pd.Series): return plain(value.tolist())
    if isinstance(value,dict): return {str(key):plain(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)): return [plain(item) for item in value]
    if isinstance(value,set): return sorted(plain(item) for item in value)
    if value is None or value is pd.NA or value is pd.NaT: return None
    if isinstance(value,(datetime,date)): return value.isoformat()
    if hasattr(value,'item'): return plain(value.item())
    if isinstance(value,float):
        if not math.isfinite(value): return None
        return int(value) if value.is_integer() else value
    if isinstance(value,(str,int,bool)): return value
    raise ValueError('数据包含不支持的类型：'+type(value).__name__)

def encoded(value): return json.dumps(plain(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fingerprint(value): return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()

def without_secrets(value):
    if isinstance(value,dict):
        return {key:without_secrets(item) for key,item in value.items()
                if not any(word in str(key).lower() for word in ['cookie','password','authorization','storage_state','api_key','apikey','密码','验证码'])}
    if isinstance(value,list): return [without_secrets(item) for item in value]
    return value
