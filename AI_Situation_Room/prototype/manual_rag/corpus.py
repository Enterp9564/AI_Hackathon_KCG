"""Validate and freeze the curated public summaries; never index raw PDFs implicitly."""
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_SOURCE = Path(__file__).parents[1] / 'manuals/library/international'


class CorpusError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Corpus:
    def __init__(self, root=DEFAULT_SOURCE):
        self.root = Path(root).resolve()
        try:
            source_data = (self.root/'sources.json').read_bytes()
            chunk_data = (self.root/'chunks.jsonl').read_bytes()
            sources = json.loads(source_data)['sources']
            self.sources = {}
            for source in sources:
                sid = source['source_id']
                path = (self.root/source['original_path']).resolve()
                if sid in self.sources or not path.is_relative_to(self.root):
                    raise CorpusError('중복 출처 또는 허용되지 않은 원본 경로입니다.')
                if digest(path.read_bytes()) != source['original_sha256']:
                    raise CorpusError('원본 PDF 무결성 확인에 실패했습니다.')
                if urlparse(source['source_url']).scheme != 'https':
                    raise CorpusError('공식 출처 URL을 확인하세요.')
                self.sources[sid] = copy.deepcopy(source)
            items, seen = [], set()
            for line in chunk_data.decode('utf-8').splitlines():
                if not line.strip(): continue
                row = json.loads(line)
                source = self.sources[row['source_id']]
                cid = row['chunk_id']
                if not isinstance(cid, str) or not cid or cid in seen:
                    raise CorpusError('구절 ID가 누락되었거나 중복되었습니다.')
                seen.add(cid)
                if row['scope'] != 'shared_public_reference' or row.get('external_use', 'allow') != 'allow':
                    raise CorpusError('첫 버전에는 등록된 공개 자료만 사용할 수 있습니다.')
                if row['operational_authority'] is not False or row['content_kind'] != 'korean_authored_summary':
                    raise CorpusError('공개 매뉴얼 한국어 초안만 지원합니다.')
                if row['review_status'] != 'draft_needs_domain_review':
                    raise CorpusError('지원하지 않는 검토 상태입니다.')
                if not isinstance(row['content'], str) or not row['content'].strip():
                    raise CorpusError('구절 본문이 없습니다.')
                if digest(row['content'].encode()) != row['content_sha256']:
                    raise CorpusError('구절 본문 무결성 확인에 실패했습니다.')
                if row['original_sha256'] != source['original_sha256'] or row['original_path'] != source['original_path']:
                    raise CorpusError('구절과 원본의 판본이 일치하지 않습니다.')
                pages = row['pdf_pages']
                if not isinstance(pages, list) or not pages or any(type(p) is not int or not 1 <= p <= source['pages'] for p in pages):
                    raise CorpusError('구절의 원문 페이지가 잘못되었습니다.')
                for field in ('limitations', 'tags', 'roles'):
                    if not isinstance(row[field], list) or not row[field] or any(not isinstance(x, str) or not x for x in row[field]):
                        raise CorpusError('구절의 조건·태그·역할이 누락되었습니다.')
                for field in ('title', 'locator', 'document_id', 'version'):
                    if not isinstance(row[field], str) or not row[field]:
                        raise CorpusError('구절의 출처 설명이 누락되었습니다.')
                # Display URLs are taken from the verified source registry.
                row.update(source_url=source['source_url'], source_title=source['title'],
                           source_version=source.get('edition') or source.get('published_at'),
                           external_use='allow')
                items.append(row)
            if not items: raise CorpusError('수록된 매뉴얼 구절이 없습니다.')
            self._items = items
            self.generation = digest(source_data + b'\n' + chunk_data)
        except CorpusError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CorpusError('매뉴얼 자료를 읽거나 검증하지 못했습니다.') from exc

    @property
    def items(self):
        return copy.deepcopy(self._items)

    def evidence(self, row):
        fields = ('chunk_id', 'document_id', 'title', 'content', 'source_id', 'source_title',
                  'source_version', 'source_url', 'locator', 'pdf_pages', 'review_status',
                  'limitations', 'content_sha256', 'original_sha256', 'scope', 'external_use', 'content_kind')
        result = {key: copy.deepcopy(row[key]) for key in fields}
        result['id'] = 'sar:' + digest(json.dumps(result, ensure_ascii=False, sort_keys=True).encode())[:32]
        return result
