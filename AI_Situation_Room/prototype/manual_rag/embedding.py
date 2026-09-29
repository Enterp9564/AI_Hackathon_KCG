"""Explicit local model preparation, offline-only inference."""
import hashlib
import json
from pathlib import Path


def model_fingerprint(root):
    records = []
    for p in sorted(Path(root).rglob('*')):
        if not p.is_file() or '.cache' in p.parts or p.name == 'haeon-model.json': continue
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
        records.append((str(p.relative_to(root)), h.hexdigest()))
    if not records: raise ValueError('로컬 임베딩 모델 파일이 없습니다.')
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


class LocalEmbedder:
    def __init__(self, model_dir):
        self.model_dir = Path(model_dir).resolve()
        if not (self.model_dir/'haeon-model.json').is_file():
            raise ValueError('먼저 로컬 임베딩 모델을 준비하세요.')
        metadata = json.loads((self.model_dir/'haeon-model.json').read_text())
        self.fingerprint = model_fingerprint(self.model_dir)
        if metadata['fingerprint'] != self.fingerprint:
            raise ValueError('임베딩 모델 파일이 준비 시점과 다릅니다.')
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(str(self.model_dir), local_files_only=True,
                                         trust_remote_code=False, device='cpu')

    def _encode(self, texts, prefix):
        inputs = [prefix+t for t in texts]
        limit = min(480, self.model.max_seq_length)
        if any(len(self.model.tokenizer.encode(t, truncation=False)) > limit for t in inputs):
            raise ValueError('임베딩 입력이 길어 분할이 필요합니다. 자동으로 자르지 않습니다.')
        return self.model.encode(inputs, normalize_embeddings=True, show_progress_bar=False).tolist()

    def encode_queries(self, texts): return self._encode(texts, 'query: ')
    def encode_passages(self, texts): return self._encode(texts, 'passage: ')


def download_model(destination):
    """Only the explicit CLI preparation command is allowed to download."""
    from huggingface_hub import HfApi, snapshot_download
    root = Path(destination).resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError('새 모델 폴더를 지정하세요. 기존 모델을 덮어쓰지 않습니다.')
    model_id = 'intfloat/multilingual-e5-small'
    revision = HfApi().model_info(model_id).sha
    snapshot_download(model_id, revision=revision, local_dir=str(root),
                      allow_patterns=['*.json','*.txt','*.model','model.safetensors','1_Pooling/*'])
    info = dict(model_id=model_id, revision=revision, fingerprint=model_fingerprint(root),
                query_prefix='query: ', passage_prefix='passage: ', normalized=True)
    (root/'haeon-model.json').write_text(json.dumps(info, indent=2))
    return info
