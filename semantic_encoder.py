"""Quantized, CPU-only sentence embeddings. Only public model weights are downloaded;
visitor text is processed in memory and is never sent to a remote inference API.
"""
from functools import lru_cache
from pathlib import Path
from threading import RLock
import hashlib
import os
import tempfile
import urllib.request
import numpy as np

REVISION = '2c4055b12046f11709e9df2c122e59ffbdc2f900'
MODEL = 'Xenova/paraphrase-multilingual-MiniLM-L12-v2'
FILES = {
    'onnx/model_quantized.onnx': (118308126, '66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc'),
    'tokenizer.json': (17082913, 'b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441'),
}
LOCK = RLock()


def model_file(name):
    size, digest = FILES[name]
    directory = Path(os.environ.get('TOPIC_MODEL_CACHE', str(Path(tempfile.gettempdir()) / 'ai-ops-semantic-model'))) / REVISION
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / Path(name).name
    def valid(path):
        return path.exists() and path.stat().st_size == size and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    if valid(target):
        return target
    request = urllib.request.Request(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}?download=true',
                                     headers={'User-Agent': 'AI-Operations-Workbench/3'})
    temporary = None
    try:
        with urllib.request.urlopen(request, timeout=45) as response, tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            written = 0
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > size:
                    raise ValueError('Model download exceeds expected size')
                output.write(chunk)
        if not valid(temporary):
            raise ValueError('Model checksum mismatch')
        temporary.replace(target)
        return target
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@lru_cache(maxsize=1)
def runtime():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    with LOCK:
        tokenizer = Tokenizer.from_file(str(model_file('tokenizer.json')))
        tokenizer.enable_truncation(max_length=128)
        tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        session = ort.InferenceSession(str(model_file('onnx/model_quantized.onnx')), options,
                                       providers=['CPUExecutionProvider'])
        return tokenizer, session


def encode(texts):
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    with LOCK:
        tokenizer, session = runtime()
        names = {item.name for item in session.get_inputs()}
        vectors = []
        for start in range(0, len(texts), 8):
            batch = tokenizer.encode_batch([str(t)[:2400] for t in texts[start:start+8]])
            mask = np.array([t.attention_mask for t in batch], dtype=np.int64)
            feed = {'input_ids': np.array([t.ids for t in batch], dtype=np.int64),
                    'attention_mask': mask, 'token_type_ids': np.array([t.type_ids for t in batch], dtype=np.int64)}
            hidden = session.run(None, {k:v for k,v in feed.items() if k in names})[0]
            pooled = (hidden * mask[..., None]).sum(axis=1) / np.maximum(mask.sum(axis=1, keepdims=True), 1)
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            vectors.extend(pooled.astype(np.float32))
        return np.asarray(vectors)
