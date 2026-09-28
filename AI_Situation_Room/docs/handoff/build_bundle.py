"""Build a documentation-only handoff from an explicit file allowlist.
Run from any directory. Never reads runtime, credentials, or environment values.
"""
from pathlib import Path
from urllib.parse import unquote
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/handoff'
DATE = '2026-09-28'
SOURCES = [ROOT/'docs/PROJECT_NAMING.md', ROOT/'docs/implementation/README.md']
SOURCES += sorted((ROOT/'docs/implementation').glob('[0-9][0-9]-*.md'))
SOURCES += [OUT/'REBUILD_PLAN.md', ROOT/'docs/FOLDER_GUIDE.md',
            ROOT/'prototype/manuals/basic-response-manual.md',
            ROOT/'prototype/manuals/donghae_assets.json', ROOT/'prototype/scenarios/cheonghae-fire.md']
CODE = sorted((ROOT/'prototype').glob('*.py'))
CODE += sorted(p for p in (ROOT/'prototype/static').iterdir() if p.suffix in ('.html','.css','.js'))
CODE += sorted(p for p in (ROOT/'prototype/tests').iterdir() if p.suffix in ('.py','.cjs'))

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

anchors = {p.resolve():f'part-{i:02d}' for i,p in enumerate(SOURCES,1)}
parts = ['''# HAEON(해온) 통합 재구현 명세

> 2026-09-28 · 문서만 전달하는 재구현 기준. 최신 사용자 명시적 지시가 우선한다.
> 앱을 재구현할 AI는 이 파일 전체를 읽은 뒤 실행 계획의 작업 단위로 진행한다. 다른 로컬 파일을 필수 입력으로 요구하지 않도록 계약과 기초 데이터를 포함했다.

해양경찰 멀티에이전트 의사결정 지원 시스템. 상황실장과 전문요원이 역할을 나눠 검토하고 사용자의 최종 판단을 돕는다. 이름은 HAEON(해온), AI 오케스트라는 설명이다.

**현재:** 로컬 세션·장부·정정·병렬 요원·검증/종합·가정 비교·자료 검색·수동 기상 경로·고정 상황판·승인형 MCP 수신을 구현한 프로토타입. **미완료:** 경량 배정의 실행 분리·의미 기반 핵심 1~2건·벡터 검색·결과 송신·실제 팀 앱/핫스팟 검증·최신 설정 전체 LIVE 인수.

2026-09-27에 기록된 Python 59개/JS/격리 Chrome DEMO 통과는 과거 시험 기록이다. 2026-09-28에는 코드와 문서 계약을 대조했다. 다른 AI 플랫폼에서 문서만으로 복원하는 시험과 새 LIVE 시험은 하지 않았다. 테스트 목록·코드 존재를 이번 통과로 해석하지 않는다.

**읽는 방법:** 명칭 → 명세 목록 → 01/02/05/06/13 공통 계약 → 기능 03~18 → 화면/인터페이스/예제/개선/프롬프트 19~23 → 실행 계획 → 기초 자료 부록. 현재 코드의 한계와 새로 만들 개선을 섞지 않는다. 본문에 남긴 prototype/... 경로는 만들 파일의 이름이나 추적용 참고다. 링크를 없앤 소스 파일이 없어도 본문 계약으로 구현한다. 외부 출처 링크는 보조 참고이며 이 전달본이 외부 서비스 최신 접근성이나 현장 매뉴얼 승인을 보장하지 않는다.

## 목차
''']
for i,p in enumerate(SOURCES,1):
    title=p.stem if p.suffix=='.json' else p.read_text().splitlines()[0].lstrip('# ')
    parts.append(f'- [{title}](#part-{i:02d})\n')
for i,p in enumerate(SOURCES,1):
    text=p.read_text()
    if p.suffix=='.json':
        text='# 등록 세력 원본 데이터\n\n현재 카탈로그를 복원할 JSON이다. 사용자 제공 함정 14개와 별도 연안구조정 후보 4개를 구별한다. 실시간 가용성 데이터가 아니다.\n\n```json\n'+text.rstrip()+'\n```\n'
    else:
        # Included docs become intra-file links. Code/historical links become plain labels.
        def replace(match):
            label,url=match.group(1),match.group(2)
            if re.match(r'\w+://',url) or url.startswith('#'): return match.group(0)
            path=unquote(url.strip('<>').split('#')[0])
            resolved=(p.parent/path).resolve()
            if resolved in anchors: return f'[{label}](#{anchors[resolved]})'
            return label+'（参照: '+path+'）'
        # Avoid rewriting code fences and inline code.
        chunks=re.split(r'(```[\s\S]*?```|`[^`\n]+`)',text)
        text=''.join(chunk if j%2 else re.sub(r'\[([^\]\n]+)\]\(([^)\n]+)\)',replace,chunk) for j,chunk in enumerate(chunks))
        text=text.replace('（参照: ',' (참조 경로: ').replace('）',')')
    parts.append(f'\n\n---\n\n<a id="part-{i:02d}"></a>\n\n<!-- Source: {p.relative_to(ROOT)} -->\n\n'+text)
spec=OUT/'HAEON_REBUILD_SPEC.md'
spec.write_text(''.join(parts))
manifest={'documentation_date':DATE,'purpose':'documentation-only reconstruction; not a completed rebuild',
          'source_documents':[{'path':str(p.relative_to(ROOT)),'sha256':digest(p)} for p in SOURCES],
          'code_baseline_fingerprints_only':[{'path':str(p.relative_to(ROOT)),'sha256':digest(p)} for p in CODE],
          'bundle_document_sha256':digest(spec),
          'excluded':['prototype/.secrets','prototype/runtime','.env','application source payloads','user credentials'],
          'archive_files':['HAEON_REBUILD_SPEC.md','README.md','manifest.json']}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(OUT/'HAEON_REBUILD_DOCS.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in manifest['archive_files']: archive.write(OUT/name,arcname=name)
print(f'Built {len(SOURCES)} source documents, {len(CODE)} code fingerprints; {spec.stat().st_size:,} bytes')
