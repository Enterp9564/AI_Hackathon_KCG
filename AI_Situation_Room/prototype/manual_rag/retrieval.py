"""Local hybrid retrieval with explicit no-match, partial and degraded outcomes."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
import time
import unicodedata
from .corpus import Corpus, DEFAULT_SOURCE

# Reviewed topic vocabulary: retrieval hints, never an incident-state classifier.
ALIASES = {
    '화재': ('불길', '연기', '불이', '불은', '화염', 'fire'),
    '익수': ('바다에 빠', '물에 빠', '해상 추락', '해상추락', 'overboard'),
    '침수': ('물이 들어', '물이 차', '바닷물', 'flooding'),
    '예인': ('기관 정지', '기관이 멈', '기관고장', 'towing'),
    '실종': ('행방', '찾을 수 없', 'missing'),
    '수색': ('찾아', 'search'), '표류': ('떠내려', 'drift'),
    '종결': ('끝났', '꺼졌', '종료', '중단', '재개'),
    '명부': ('몇 명', '몇명', '승선원', '탑승자', '인원', '명 중', '명중'),
    '재이송': ('재이송', '다시 이송'), '환자': ('부상', '의식', '상태 변화', '응급'),
    '가정': ('추정', '가정'), '헬기': ('항공', 'helicopter'),
    '저체온': ('저체온', 'hypothermia'), '생존시간': ('생존 시간', '생존시간'),
    '기록': ('보고 시각', '보고시각', '기록'), '미수색': ('미수색', '안 찾은'),
    '인계': ('인계', '인수', 'handover'), '구조': ('구조', 'rescue'),
}


def tokens(text):
    text = unicodedata.normalize('NFKC', str(text)).lower()
    stop = {'방법','어떻게','알려줘','알려주세요','검토','해주세요','현재','정보','내용','대한','필요한','함께','the','and','to','of','a','in'}
    result = [word for word in re.findall(r'[a-z0-9]+|[가-힣]{2,}', text) if word not in stop]
    for canonical, words in ALIASES.items():
        if canonical in text or any(word in text for word in words): result.append(canonical)
    # Canonical terms also match Korean postpositions (e.g. 파고는).
    for word in ('파고','파주기','시정','수온','풍향','해류','datum','오차','목격','좌초','지원','안전장소'):
        if word in text: result.append(word)
    return result


def lexical_scores(rows, query):
    docs = [Counter(tokens(' '.join([r['title'], ' '.join(r['tags']), r['content']]))) for r in rows]
    terms = set(tokens(query))
    average = sum(sum(d.values()) for d in docs)/max(len(docs), 1)
    scores = []
    for i, doc in enumerate(docs):
        score = 0.0
        for term in terms:
            freq = doc[term]
            if not freq: continue
            df = sum(term in d for d in docs)
            idf = math.log(1 + (len(docs)-df+.5)/(df+.5))
            score += idf*freq*2.5/(freq+1.5*(.25+.75*sum(doc.values())/average))
        if score > 0: scores.append((i, score))
    return sorted(scores, key=lambda x: (-x[1], rows[x[0]]['chunk_id']))[:12]


class ManualSearch:
    def __init__(self, source=DEFAULT_SOURCE, mode='lexical', index_dir=None, dense_threshold=.83):
        if mode not in ('lexical', 'hybrid'): raise ValueError('지원하지 않는 검색 방식입니다.')
        self.corpus = Corpus(source)
        self.mode = mode
        self.generation = self.corpus.generation
        self.dense_threshold = dense_threshold
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='manual-search')
        self._index = None
        self._degraded = False
        if mode == 'hybrid':
            try:
                self._worker.submit(self._open, index_dir).result()
            except Exception:
                self._degraded = True

    def _open(self, index_dir):
        from .index import LocalIndex
        self._index = LocalIndex(index_dir, self.corpus)
        self.generation = self._index.generation

    @property
    def ready_vector(self):
        return self._index is not None and not self._degraded

    def close(self):
        if self._index is not None: self._worker.submit(self._index.close).result()
        self._worker.shutdown(wait=True)

    def retrieve(self, query, role='sar', incident=None, assignment='', budget_bytes=6000, context_parts=None):
        return self._worker.submit(self._retrieve, query, role, incident, assignment, budget_bytes, context_parts).result()

    def _retrieve(self, query, role, incident, assignment, budget_bytes, context_parts):
        started = time.monotonic()
        # Bound expensive work, but never silently truncate an explicit query.
        if not isinstance(query, str) or len(query) > 12000:
            return self._result('error', [], [], started, reason='검색 질의 크기를 확인하세요.')
        parts = [query]
        # Only the current structured incident is used. Raw history is not searched globally.
        if incident:
            parts.append(json.dumps({k: incident[k] for k in ('conditions',) if k in incident}, ensure_ascii=False))
        parts.extend(context_parts or [])
        if len(parts)>14 or sum(len(p.encode('utf-8')) for p in parts)>44000:
            return self._result('error', [], [], started, reason='검색 사건 정보 한도를 초과했습니다.')
        # Generic assignments must not turn an unrelated user question into a match.
        rows = self.corpus.items
        base = lexical_scores(rows, ' '.join(parts))
        scores = {i: 1/(60+rank) for rank, (i, _) in enumerate(base, 1)}
        dense = []
        query_degraded = self._degraded
        if self._index is not None and not self._degraded:
            try:
                # Each complete labeled field is embedded independently, retaining negation.
                merged = {}
                for part in parts:
                    for i, score in self._index.search(part, limit=12):
                        merged[i] = max(merged.get(i, -1), score)
                dense = sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))[:12]
                for rank, (i, score) in enumerate(dense, 1):
                    if score >= self.dense_threshold: scores[i] = scores.get(i, 0)+1/(60+rank)
            except Exception:
                query_degraded = True
        ranked = sorted(scores, key=lambda i: (-scores[i], role not in rows[i]['roles'], rows[i]['chunk_id']))[:6]
        # Use assignment only to order already relevant candidates, not invent relevance.
        assignment_scores = dict(lexical_scores(rows, assignment)) if assignment else {}
        ranked.sort(key=lambda i: (-scores[i], -assignment_scores.get(i, 0), role not in rows[i]['roles']))
        items, omitted, used = [], [], 0
        for i in ranked:
            item = self.corpus.evidence(rows[i])
            item['retrieval_rank'] = len(items)+1
            size = len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
            if used + size > budget_bytes:
                omitted.append(item['id']); continue
            items.append(item); used += size
        status = 'partial' if omitted else ('ok' if items else 'no_match')
        return self._result(status, items, omitted, started, query_degraded=query_degraded)

    def _result(self, status, items, omitted, started, reason='', query_degraded=False):
        vector_used=self.ready_vector and not query_degraded
        return dict(status=status, reason=reason, generation=self.generation,
                    method='hybrid' if vector_used else 'lexical', items=items,
                    omitted_ids=omitted, latency_ms=round((time.monotonic()-started)*1000, 2),
                    warnings=['degraded'] if self.mode == 'hybrid' and not vector_used else [])
