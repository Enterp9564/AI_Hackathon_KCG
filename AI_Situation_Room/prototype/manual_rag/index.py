"""Immutable generations. The caller owns all access on one search worker."""
import json
from pathlib import Path
import tempfile
import uuid
from .corpus import digest
from .embedding import LocalEmbedder

COLLECTION = 'public_sar'


def passage(row):
    return row['title']+'\n'+' '.join(row['tags'])+'\n'+row['content']


def build_index(corpus, embedder, output_dir):
    from qdrant_client import QdrantClient, models
    target = Path(output_dir).resolve()
    if target.exists(): raise FileExistsError('새 인덱스 세대 경로를 지정하세요.')
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = corpus.items
    vectors = embedder.encode_passages([passage(r) for r in rows])
    if len(vectors) != len(rows) or not vectors: raise ValueError('벡터 개수가 일치하지 않습니다.')
    with tempfile.TemporaryDirectory(prefix='.sar-build-', dir=target.parent) as temporary:
        staging = Path(temporary)/'generation'; staging.mkdir()
        client = QdrantClient(path=str(staging/'vectors'))
        try:
            client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=len(vectors[0]), distance=models.Distance.COSINE))
            client.upsert(COLLECTION, points=[models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, r['chunk_id'])), vector=v,
                payload={'row':i, 'chunk_id':r['chunk_id'], 'scope':'shared_public_reference', 'external_use':'allow'})
                for i, (r,v) in enumerate(zip(rows,vectors))], wait=True)
            if client.count(COLLECTION, exact=True).count != len(rows): raise ValueError('인덱스 저장 건수가 일치하지 않습니다.')
        finally: client.close()
        manifest = dict(schema_version=1, corpus_generation=corpus.generation, model_fingerprint=embedder.fingerprint,
                        model_dir=str(embedder.model_dir), count=len(rows), dimension=len(vectors[0]),
                        chunk_ids=[r['chunk_id'] for r in rows])
        manifest['generation'] = digest(json.dumps(manifest, sort_keys=True).encode())
        (staging/'manifest.json').write_text(json.dumps(manifest, indent=2))
        staging.rename(target)
    return manifest


class LocalIndex:
    def __init__(self, directory, corpus, embedder=None):
        from qdrant_client import QdrantClient
        root = Path(directory).resolve()
        manifest = json.loads((root/'manifest.json').read_text())
        unsigned = {k:v for k,v in manifest.items() if k != 'generation'}
        if manifest['generation'] != digest(json.dumps(unsigned, sort_keys=True).encode()):
            raise ValueError('인덱스 manifest가 변경되었습니다.')
        if manifest['corpus_generation'] != corpus.generation or manifest['chunk_ids'] != [r['chunk_id'] for r in corpus.items]:
            raise ValueError('인덱스와 매뉴얼 판본이 다릅니다.')
        self.embedder = embedder or LocalEmbedder(manifest['model_dir'])
        if manifest['model_fingerprint'] != self.embedder.fingerprint:
            raise ValueError('인덱스와 임베딩 모델 판본이 다릅니다.')
        if not (root/'vectors').is_dir(): raise ValueError('벡터 저장소가 없습니다.')
        self.client = QdrantClient(path=str(root/'vectors'))
        try:
            if self.client.count(COLLECTION, exact=True).count != manifest['count']:
                raise ValueError('인덱스 개수가 일치하지 않습니다.')
        except Exception:
            self.client.close(); raise
        self.generation = manifest['generation']

    def search(self, text, limit=12):
        from qdrant_client import models
        vector = self.embedder.encode_queries([text])[0]
        hits = self.client.query_points(COLLECTION, query=vector, limit=limit, with_payload=True,
            query_filter=models.Filter(must=[models.FieldCondition(key='scope',match=models.MatchValue(value='shared_public_reference')),
                models.FieldCondition(key='external_use',match=models.MatchValue(value='allow'))])).points
        return [(p.payload['row'], float(p.score)) for p in hits]

    def close(self): self.client.close()
