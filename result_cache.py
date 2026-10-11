"""有数量及容量上限的内存缓存；失败不入缓存，不记录正文或链接。"""
from collections import OrderedDict
from threading import RLock
from time import perf_counter
from state_codec import encoded,fingerprint

EXPORT_VERSION='v3-report-1'

class BoundedCache:
    def __init__(self,max_entries=12,max_bytes=24*1024*1024):
        self.max_entries=max_entries; self.max_bytes=max_bytes; self.entries=OrderedDict(); self.bytes=0
        self.hits=0; self.misses=0; self.failures=0; self.seconds=0.; self.lock=RLock()

    def get(self,namespace,payload,producer):
        key=namespace+':'+fingerprint(payload)
        with self.lock:
            if key in self.entries:
                self.hits+=1; self.entries.move_to_end(key)
                return self.entries[key][0]
            self.misses+=1; started=perf_counter()
            try: result=producer()
            except Exception:
                self.failures+=1
                raise
            finally: self.seconds+=perf_counter()-started
            size=self.size(result)+len(key)
            if size<=self.max_bytes:
                while self.entries and (len(self.entries)>=self.max_entries or self.bytes+size>self.max_bytes):
                    _,(_,old_size)=self.entries.popitem(last=False); self.bytes-=old_size
                self.entries[key]=(result,size); self.bytes+=size
            return result

    @staticmethod
    def size(value):
        if isinstance(value,bytes): return len(value)
        if isinstance(value,str): return len(value.encode('utf-8'))
        if isinstance(value,(list,tuple)): return sum(BoundedCache.size(v) for v in value)+64
        if isinstance(value,dict): return sum(len(str(k))+BoundedCache.size(v) for k,v in value.items())+64
        return len(encoded(value).encode('utf-8'))

    def info(self):
        return {'命中次数':self.hits,'实际计算次数':self.misses,'失败次数':self.failures,
                '计算耗时（秒）':round(self.seconds,4),'缓存条目':len(self.entries),'缓存字节':self.bytes}

def session_cache(name):
    import streamlit as st
    key='_bounded-cache-'+name
    if key not in st.session_state:
        st.session_state[key]=BoundedCache(max_entries=3 if name=='exports' else 12,
                                         max_bytes=(24 if name=='exports' else 16)*1024*1024)
    return st.session_state[key]

def export_payload(snapshot,analysis):
    public={key:value for key,value in analysis.items() if key!='editing'}
    public['editing']={'packaging':analysis.get('editing',{}).get('packaging',{})}
    return {'format':EXPORT_VERSION,'snapshot':snapshot,'analysis':public}

def report_bytes(cache,snapshot,analysis,markdown_builder):
    def generate():
        from excel_export import public_workbook
        return public_workbook(snapshot,analysis),markdown_builder(snapshot,analysis)
    return cache.get('reports',export_payload(snapshot,analysis),generate)
