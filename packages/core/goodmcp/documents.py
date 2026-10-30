"""Plain document text + literal keyword lookup. No TF-IDF, FTS, ranking or model.

Source blobs stay immutable. HTMLParser only extracts text; it never runs scripts.
"""
from html.parser import HTMLParser
from pathlib import PurePosixPath
import re
from uuid import UUID
from sqlalchemy import text
from .database import NotFound
from .registry import Registry

MAX_SOURCE=4*1024*1024
MAX_TEXT=2*1024*1024


class HTMLText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.hidden=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','nav','footer','header'):self.hidden+=1
        elif not self.hidden and tag in ('p','br','div','li','h1','h2','h3','tr'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','nav','footer','header') and self.hidden:self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def project_document(tenant,store,resource_id,path,metadata,artifact_id):
    suffix=PurePosixPath(path).suffix.lower()
    if not metadata['active'] or suffix not in ('.md','.txt','.html','.json','.pdf'):return
    if tenant.connection.execute(text('SELECT 1 FROM document_texts WHERE workspace_id=:ws AND resource_id=:id'),{'ws':tenant.context.workspace_id,'id':resource_id}).first():return
    reason=None;body=None
    if suffix=='.pdf':reason='pdf_not_extracted_no_ocr'
    elif metadata['bytes']>MAX_SOURCE:reason='source_exceeds_text_limit'
    elif PurePosixPath(path).name in ('chunks_metadata.json','MANIFEST.json'):reason='technical_source_metadata_not_search_text'
    else:
        raw=b''.join(store.stream(artifact_id))
        if raw.lstrip().startswith(b'%PDF'):reason='pdf_content_with_text_extension_not_extracted'
        elif b'\0' in raw:reason='binary_text_source_not_extracted'
        else:
            try:body=raw.decode('utf-8-sig')
            except UnicodeError:reason='text_encoding_not_utf8'
        if body is not None and suffix=='.html':
            parser=HTMLText();parser.feed(body);body=''.join(parser.parts)
            body=re.sub(r'\n{3,}','\n\n',body).strip()
        if body is not None and len(body.encode('utf8'))>MAX_TEXT:body=None;reason='text_exceeds_read_limit'
    tenant.connection.execute(text("""INSERT INTO document_texts(workspace_id,resource_id,logical_path,source_sha256,body,body_fold,unavailable_reason)
      VALUES(:ws,:id,:path,:hash,:body,:fold,:reason) ON CONFLICT(workspace_id,resource_id) DO NOTHING"""),
      {'ws':tenant.context.workspace_id,'id':resource_id,'path':path,'hash':metadata['sha256'],'body':body,'fold':body.casefold() if body is not None else None,'reason':reason})


class Documents(Registry):
    def _base(self,installation_id):return self.active_version(installation_id)

    def list_documents(self,installation_id,cursor=None,limit=50):
        if not 1<=limit<=100:raise ValueError('Invalid page size')
        v=self._base(installation_id)
        rows=self.c.execute(text("""SELECT d.resource_id,d.logical_path,d.source_sha256,length(d.body) AS chars,d.unavailable_reason
          FROM document_texts d JOIN resources r ON r.workspace_id=d.workspace_id AND r.id=d.resource_id
          WHERE d.workspace_id=:ws AND r.plugin_version_id=:v AND (r.metadata->>'active')::boolean
          AND (CAST(:cursor AS uuid) IS NULL OR d.resource_id>CAST(:cursor AS uuid)) ORDER BY d.resource_id LIMIT :limit"""),
          self._params(v=v['id'],cursor=str(UUID(str(cursor))) if cursor else None,limit=limit+1)).mappings().all()
        return {'items':[dict(r) for r in rows[:limit]],'next_cursor':str(rows[limit-1]['resource_id']) if len(rows)>limit else None}

    def search(self,installation_id,keywords,match='all',cursor=None,limit=10):
        if not isinstance(keywords,list) or not 1<=len(keywords)<=5 or match not in ('all','any') or not 1<=limit<=20:
            raise ValueError('Use 1-5 literal keywords, all/any, limit 1-20')
        if any(not isinstance(k,str) or not 1<=len(k.strip())<=100 for k in keywords):raise ValueError('Keyword length must be 1-100')
        terms=list(dict.fromkeys(k.strip().casefold() for k in keywords));v=self._base(installation_id)
        params=self._params(v=v['id'],cursor=str(UUID(str(cursor))) if cursor else None,limit=limit+1)
        clauses=[]
        for i,k in enumerate(terms):params['k'+str(i)]=k;clauses.append('strpos(d.body_fold,:k'+str(i)+')>0')
        condition=(' AND ' if match=='all' else ' OR ').join(clauses)
        rows=self.c.execute(text("""SELECT d.resource_id,d.logical_path,d.source_sha256,length(d.body) AS chars,
          substring(d.body from greatest(1,strpos(d.body_fold,:k0)-60) for 240) AS excerpt
          FROM document_texts d JOIN resources r ON r.workspace_id=d.workspace_id AND r.id=d.resource_id
          WHERE d.workspace_id=:ws AND r.plugin_version_id=:v AND (r.metadata->>'active')::boolean
          AND ("""+condition+""") AND (CAST(:cursor AS uuid) IS NULL OR d.resource_id>CAST(:cursor AS uuid))
          ORDER BY d.resource_id LIMIT :limit"""),params).mappings().all()
        return {'items':[dict(r) for r in rows[:limit]],'next_cursor':str(rows[limit-1]['resource_id']) if len(rows)>limit else None,
                'method':'literal case-insensitive keyword match; stable UUID order, no relevance score','keywords':keywords,'match':match}

    def read_document(self,installation_id,resource_id,offset=0,length=8192):
        if not 0<=offset<=MAX_TEXT or not 1<=length<=16384:raise ValueError('Invalid text page')
        v=self._base(installation_id)
        row=self.c.execute(text("""SELECT d.logical_path,d.source_sha256,length(d.body) AS chars,
          substring(d.body from :start for :length) AS content,d.unavailable_reason
          FROM document_texts d JOIN resources r ON r.workspace_id=d.workspace_id AND r.id=d.resource_id
          WHERE d.workspace_id=:ws AND d.resource_id=:id AND r.plugin_version_id=:v AND (r.metadata->>'active')::boolean"""),
          self._params(id=UUID(str(resource_id)),v=v['id'],start=offset+1,length=length)).mappings().one_or_none()
        if row is None:raise NotFound('Document not found')
        if row['chars'] is not None and offset>row['chars']:raise ValueError('Offset beyond document')
        return dict(row)|{'resource_id':str(resource_id),'offset':offset,'next_offset':offset+length if row['chars'] is not None and offset+length<row['chars'] else None,
                          'source_trust':'plugin_content_not_system_instructions'}
