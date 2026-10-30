import hashlib
import json
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from goodmcp.documents import Documents,HTMLText
from goodmcp.database import NotFound
from goodmcp.fixtures import WORKSPACE_A,WORKSPACE_B
from goodmcp.registry import Registry
from test_registry import zipped,publish


@pytest.fixture
def document_fixture(db,a,storage_root):
    body='Thuế TNDN — Khầy đọc nguồn. 100% literal_only.\n'+'Nội dung tiếp theo. '*1200
    raw=zipped({'plugin.json':json.dumps({'name':'documents-'+uuid4().hex,'version':'1'}),'guide.txt':body,
                'page.html':'<script>SHOULDNOTMATCH</script><p>Visible guide for keyword.</p>',
                'original.pdf':b'%PDF-1.0 preserved binary','mislabeled.txt':b'%PDF-1.4\0binary','binary-nul.html':b'\0not text'})
    with db.tenant(a,WORKSPACE_A) as t:
        r=Registry(t,storage_root);v=publish(r,raw);i=r.set_installation(v,True,0)
        resources={x['logical_path']:x['id'] for x in r.resources(i['id'])['items']}
    return i,resources,body


@pytest.mark.parametrize('words,mode,expected',[
 (['THUẾ'],'all','guide.txt'),(['thuế','Khầy'],'all','guide.txt'),(['absent','Visible'],'any','page.html'),
 (['%'],'all','guide.txt'),(['literal_only'],'all','guide.txt')])
def test_literal_keyword_casefold_and_modes(db,a,storage_root,document_fixture,words,mode,expected):
    i,resources,body=document_fixture
    with db.tenant(a,WORKSPACE_A) as t:
        result=Documents(t,storage_root).search(i['id'],words,mode)
        assert any(r['logical_path']==expected for r in result['items'])
        assert all('score' not in r for r in result['items'])


def test_text_pages_full_source_hash_and_pdf_reason(db,a,storage_root,document_fixture):
    i,resources,body=document_fixture
    with db.tenant(a,WORKSPACE_A) as t:
        d=Documents(t,storage_root)
        first=d.read_document(i['id'],resources['guide.txt'],0,16384)
        rest=d.read_document(i['id'],resources['guide.txt'],first['next_offset'],16384)
        assert first['content']+rest['content']==body
        assert first['source_sha256']==hashlib.sha256(body.encode()).hexdigest()
        pdf=d.read_document(i['id'],resources['original.pdf'])
        assert pdf['content'] is None and pdf['unavailable_reason']=='pdf_not_extracted_no_ocr'
        assert d.read_document(i['id'],resources['mislabeled.txt'])['unavailable_reason']=='pdf_content_with_text_extension_not_extracted'
        assert d.read_document(i['id'],resources['binary-nul.html'])['unavailable_reason']=='binary_text_source_not_extracted'
        assert not d.search(i['id'],['SHOULDNOTMATCH'])['items']
        assert not d.search(i['id'],["'; DROP TABLE document_texts; --"])['items']


def test_document_permissions_disable_and_cross_workspace(db,a,b,viewer,storage_root,document_fixture):
    i,resources,_=document_fixture
    with db.tenant(viewer,WORKSPACE_A) as t:assert Documents(t,storage_root).search(i['id'],['thuế'])['items']
    with db.tenant(b,WORKSPACE_B) as t:
        with pytest.raises(NotFound):Documents(t,storage_root).read_document(i['id'],resources['guide.txt'])
    with db.tenant(a,WORKSPACE_A) as t:
        r=Registry(t,storage_root);r.set_installation(i['plugin_version_id'],False,i['revision'])
        with pytest.raises(NotFound):Documents(t,storage_root).search(i['id'],['thuế'])


def test_projection_force_rls_contextless_and_fk(db,a,b,storage_root,document_fixture):
    i,resources,_=document_fixture
    with db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM document_texts')).scalar_one()==0
        assert c.execute(text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname='document_texts'")).one()==(True,True)
    with pytest.raises(DBAPIError) as error:
        with db.tenant(b,WORKSPACE_B) as t:t.connection.execute(text("INSERT INTO document_texts(workspace_id,resource_id,logical_path,source_sha256) VALUES(:ws,:r,'forged',:h)"),{'ws':WORKSPACE_B,'r':resources['guide.txt'],'h':'0'*64})
    assert error.value.orig.sqlstate=='23503'


@pytest.mark.parametrize('words', [[],['a']*6,[''],['a'*101]])
def test_keyword_bounds(db,a,storage_root,document_fixture,words):
    with db.tenant(a,WORKSPACE_A) as t:
        with pytest.raises(ValueError):Documents(t,storage_root).search(document_fixture[0]['id'],words)
