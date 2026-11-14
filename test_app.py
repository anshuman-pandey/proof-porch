import re,sqlite3
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
@pytest.fixture
def app(tmp_path):
 return create_app({'TESTING':True,'SECRET_KEY':'test-secret','ADMIN_PASSWORD_HASH':generate_password_hash('password'),'DATABASE':str(tmp_path/'db'),'SESSION_COOKIE_SECURE':False})
def csrf(c,p): return re.search(r'name="csrf" value="([^"]+)"',c.get(p).text).group(1)
def setup(app):
 c=app.test_client(); c.post('/login',data={'csrf':csrf(c,'/login'),'password':'password'})
 c.post('/admin',data={'csrf':csrf(c,'/admin'),'name':'Customers'})
 with sqlite3.connect(app.config['DATABASE']) as d: b=d.execute('SELECT id FROM boards').fetchone()[0]
 return c,b
def submit(c,b,**extra):
 data={'csrf':csrf(c,'/collect/'+b),'name':'Ada','role':'Founder','quote':'Useful and clear.','consent':'yes'};data.update(extra)
 return c.post('/collect/'+b,data=data)
def item(app):
 with sqlite3.connect(app.config['DATABASE']) as d:return d.execute('SELECT id FROM testimonials').fetchone()[0]
def act(c,b,i,a):return c.post(f'/admin/{b}/{i}/{a}',data={'csrf':csrf(c,'/admin'),'confirm':'yes'})
def test_workflow(app):
 c,b=setup(app);v=app.test_client();r=submit(v,b);assert r.status_code==201
 removal=re.search(r'href="(/remove/[^"]+)"',r.text).group(1)
 assert 'Useful and clear.' not in v.get('/wall/'+b).text
 act(c,b,item(app),'approve');assert 'Useful and clear.' in v.get('/wall/'+b).text
 assert 'Useful and clear.' in c.get(f'/admin/{b}/export.csv').text
 assert v.get(removal).status_code==200
 assert 'Useful and clear.' in v.get('/wall/'+b).text
 assert v.post(removal,data={'csrf':csrf(v,removal)}).status_code==200
 assert 'Useful and clear.' not in v.get('/wall/'+b).text
 assert v.get(removal).status_code==404

def test_consent(app):
 _,b=setup(app);assert submit(app.test_client(),b,consent='no').status_code==400
 with sqlite3.connect(app.config['DATABASE']) as d:assert d.execute('SELECT count(*) FROM testimonials').fetchone()[0]==0

def test_access_csrf(app):
 c,b=setup(app);v=app.test_client()
 assert v.get(f'/admin/{b}/export.csv').status_code==302
 assert v.post('/admin',data={'name':'Injected'}).status_code==400
 assert c.post('/logout').status_code==400
 assert v.get('/admin').status_code==302

def test_xss_csv(app):
 c,b=setup(app);v=app.test_client();submit(v,b,name=' =SUM(1,2)',quote='<script>alert(1)</script>')
 act(c,b,item(app),'approve');r=v.get('/wall/'+b)
 assert '<script>' not in r.text and '&lt;script&gt;' in r.text
 assert "'=SUM" in c.get(f'/admin/{b}/export.csv').text
 assert 'frame-ancestors *' in r.headers['Content-Security-Policy']
 assert c.get('/admin').headers['X-Frame-Options']=='DENY'

def test_reject_delete(app):
 c,b=setup(app);submit(app.test_client(),b);i=item(app)
 act(c,b,i,'approve');act(c,b,i,'reject');assert 'Useful and clear.' not in c.get('/wall/'+b).text
 act(c,b,i,'delete');assert 'Useful and clear.' not in c.get(f'/admin/{b}/export.csv').text

def test_rate_limit(app):
 _,b=setup(app);v=app.test_client()
 for _ in range(10):assert submit(v,b).status_code==201
 assert submit(v,b).status_code==429

def test_validation(app):
 _,b=setup(app);v=app.test_client()
 assert v.get('/collect/missing').status_code==404
 assert submit(v,b,quote='x'*2001).status_code==400

def test_password(app):
 c=app.test_client();assert c.post('/login',data={'csrf':csrf(c,'/login'),'password':'wrong'}).status_code==401
 assert c.get('/admin').status_code==302

def test_backup_restore(app,tmp_path):
 c,b=setup(app);submit(app.test_client(),b);act(c,b,item(app),'approve')
 restored=tmp_path/'restored.sqlite'
 with sqlite3.connect(app.config['DATABASE']) as source,sqlite3.connect(restored) as dest:source.backup(dest)
 recovered=create_app({**app.config,'DATABASE':str(restored)})
 assert 'Useful and clear.' in recovered.test_client().get('/wall/'+b).text


def test_delete_requires_confirmation(app):
 c,b=setup(app);submit(app.test_client(),b);i=item(app)
 r=c.post(f'/admin/{b}/{i}/delete',data={'csrf':csrf(c,'/admin')})
 assert r.status_code==200 and 'Permanently delete' in r.text
 assert item(app)==i

def test_public_links_use_configured_https_origin(app):
 config=dict(app.config);config['PUBLIC_BASE_URL']='https://testimonials.example.test/'
 configured=create_app(config)
 owner,board=setup(configured)
 response=owner.get('/admin/'+board,headers={'X-Forwarded-Proto':'http','X-Forwarded-Host':'untrusted.example'})
 assert f'https://testimonials.example.test/collect/{board}' in response.text
 assert f'https://testimonials.example.test/wall/{board}' in response.text
 assert 'untrusted.example' not in response.text
 visitor=configured.test_client();response=submit(visitor,board)
 assert 'https://testimonials.example.test/remove/' in response.text
 assert 'http://localhost/remove/' not in response.text
 # Normal request routes and security headers remain unchanged.
 assert response.headers['Referrer-Policy']=='no-referrer'
 assert visitor.get('/wall/'+board).status_code==200

@pytest.mark.parametrize('origin',[
 'http://public.example','//public.example','https://user:pass@example.com',
 'https://example.com/subpath','https://example.com?token=secret','https://example.com#fragment',
 'https://example.com?','https://example.com#',
 'https://example.com:invalid','https://example.com\\evil','https://example.com\n.evil','https://example.com:'
])
def test_public_origin_rejects_unsafe_configuration(app,origin):
 config=dict(app.config);config['PUBLIC_BASE_URL']=origin
 with pytest.raises(ValueError,match='HTTPS origin'):create_app(config)

def test_local_link_fallback_still_works(app):
 owner,board=setup(app)
 assert f'http://localhost/collect/{board}' in owner.get('/admin/'+board).text
