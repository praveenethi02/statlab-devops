"""Original account assertions plus platform persistence and security regressions."""
import hashlib
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pypdf import PdfReader
from werkzeug.test import EnvironBuilder

import database
from server import create_app, password_hash


class PlatformTests(unittest.TestCase):
    def setUp(self):
        Path('.runtime').mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir='.runtime')
        self.path = str(Path(self.folder.name)/'test.sqlite3')
        self.config = {'DATABASE':self.path, 'TESTING':True, 'SECRET_KEY':'test-only-secret'}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/me').json['csrf_token']

    def tearDown(self):
        self.folder.cleanup()

    def send(self, method, path, data=None, client=None, csrf=None, **kwargs):
        response = (client or self.client).open(path, method=method, json=data, buffered=True,
                                              headers={'X-CSRF-Token':csrf or self.csrf}, **kwargs)
        response.close()
        return response

    def register(self, username='Test_User', client=None, csrf=None):
        account = {'username':username,'email':username+'@example.com','password':'sample-password-123'}
        self.assertEqual(self.send('POST','/api/signup',account,client,csrf).status_code,201)
        return account

    def login(self, account=None, remember=False, client=None, csrf=None):
        account = account or self.register(client=client,csrf=csrf)
        response = self.send('POST','/api/login',{'identifier':account['username'],'password':account['password'],'remember':remember},client,csrf)
        self.assertEqual(response.status_code,200)
        return response

    def dataset(self, name='Experiment 01', client=None, csrf=None):
        response = self.send('POST','/api/datasets',{'name':name,'text':'10, 20, 30, 40, 50'},client,csrf)
        self.assertEqual(response.status_code,201)
        return response.json['dataset']

    def analysis(self, dataset):
        response = self.send('POST','/api/analyses',{'name':'Reference analysis','dataset_id':dataset['id'],'dataset_revision':dataset['revision'],'settings':{}})
        self.assertEqual(response.status_code,201)
        return response.json['analysis']

    def test_complete_account_lifecycle(self):
        account = self.register()
        self.assertEqual(self.send('POST','/api/signup',account).status_code,409)
        self.assertEqual(self.send('POST','/api/signup',{**account,'username':'different'}).status_code,409)
        self.assertIsNone(self.client.get('/api/me').json['user'])
        self.assertEqual(self.send('POST','/api/login',{'identifier':'Test_User','password':'wrong'}).status_code,401)
        self.assertEqual(self.send('POST','/api/login',{'identifier':'missing','password':'wrong'}).status_code,401)
        response = self.login({**account,'username':'TEST_USER'})
        self.assertEqual(response.json['user']['username'],'Test_User')
        cookie = response.headers.get('Set-Cookie')
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Strict',cookie)
        self.assertNotIn('Max-Age',cookie)
        self.assertEqual(self.client.get('/api/me').json['user'],response.json['user'])
        self.assertEqual(self.send('POST','/api/logout',{}).status_code,200)
        self.assertIsNone(self.client.get('/api/me').json['user'])
        response = self.send('POST','/api/login',{'identifier':account['email'].upper(),'password':account['password'],'remember':True})
        self.assertEqual(response.status_code,200)
        self.assertIn('Max-Age=2592000',response.headers.get('Set-Cookie'))
        with closing(database.connect(self.path)) as db, db:
            row = db.execute('SELECT * FROM users').fetchone()
            self.assertNotEqual(row['password_hash'],account['password'].encode())
            db.execute('UPDATE sessions SET expires=0')
        self.assertIsNone(self.client.get('/api/me').json['user'])
        self.assertEqual(self.client.get('/api/datasets').status_code,401)

    def test_validation_and_private_files(self):
        account = {'username':'valid_name','email':'valid@example.com','password':'long-password'}
        for field,value in [('username','x'),('email','bad'),('password','short'),('password',42)]:
            self.assertEqual(self.send('POST','/api/signup',{**account,field:value}).status_code,400)
        self.assertEqual(self.send('POST','/api/signup',[1,2]).status_code,400)
        for path in ('/accounts.sqlite3','/server.py','/accounts.secret','/migrations/001_platform.sql','/.env'):
            self.assertEqual(self.client.get(path).status_code,404)
        with self.client.get('/hrml') as response:
            self.assertEqual(response.status_code,200)

    def test_api_only_deployment(self):
        app = create_app({**self.config, 'SERVE_FRONTEND':False})
        client = app.test_client()
        for path in ('/', '/hrml', '/static/app.js'):
            self.assertEqual(client.get(path).status_code,404)
        self.assertEqual(client.get('/api/health').json,{'status':'ok'})
        csrf = client.get('/api/me').json['csrf_token']
        self.login(client=client,csrf=csrf)
        dataset = self.dataset(client=client,csrf=csrf)
        result = self.send('POST','/api/statistics/calculate',{'dataset_id':dataset['id']},client,csrf)
        self.assertEqual(result.json['calculation']['results']['mean'],30)

    def test_csrf_and_origins(self):
        self.assertEqual(self.client.post('/api/signup',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/signup',json={},headers={'X-CSRF-Token':'forged'}).status_code,403)
        self.assertEqual(self.client.post('/api/logout',json={},headers={'X-CSRF-Token':self.csrf,'Origin':'https://example.com'}).status_code,403)
        self.client.set_cookie('csrf','unsigned-attacker-cookie')
        self.assertEqual(self.client.post('/api/signup',json={},headers={'X-CSRF-Token':'unsigned-attacker-cookie'}).status_code,403)

    def test_host_and_security_headers(self):
        response = self.client.get('/')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        response.close()
        self.assertEqual(self.client.get('/api/me',headers={'Host':'evil.example'}).status_code,403)
        app = create_app({**self.config,'COOKIE_SECURE':True,'ALLOWED_HOSTS':['server.example']})
        response = app.test_client().get('/api/me',base_url='https://server.example')
        self.assertIn('Secure',response.headers['Set-Cookie'])
        self.assertIn('Strict-Transport-Security',response.headers)

    def test_required_end_to_end_and_restart(self):
        account = self.register()
        self.login(account)
        dataset = self.dataset()
        calculation = self.send('POST','/api/statistics/calculate',{'dataset_id':dataset['id']}).json['calculation']
        self.assertEqual(calculation['results']['mean'],30)
        self.assertEqual(calculation['results']['population_variance'],200)
        self.assertEqual(calculation['results']['sample_variance'],250)
        analysis = self.analysis(dataset)
        response = self.send('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Experimental Error','value':2.5,'unit':'%'})
        self.assertEqual(response.status_code,201)
        parameter = response.json['parameter']
        self.send('POST','/api/logout',{})
        restarted = create_app(self.config)
        client = restarted.test_client()
        csrf = client.get('/api/me').json['csrf_token']
        self.login(account,client=client,csrf=csrf)
        restored = client.get(f"/api/datasets/{dataset['id']}").json['dataset']
        self.assertEqual(restored['parameters'][0]['value'],2.5)
        self.assertEqual(client.get(f"/api/analyses/{analysis['id']}").json['analysis']['calculation']['results']['mean'],30)
        edited = self.send('PUT',f"/api/datasets/{dataset['id']}",{'name':'Experiment 01','text':'10, 20, 30, 40, 100','revision':1},client,csrf)
        self.assertEqual(edited.status_code,200)
        self.assertEqual(edited.json['dataset']['revision'],2)
        latest = self.send('POST','/api/statistics/calculate',{'dataset_id':dataset['id']},client,csrf).json['calculation']
        self.assertEqual(latest['results']['mean'],40)
        historical = client.get(f"/api/analyses/{analysis['id']}").json['analysis']
        self.assertTrue(historical['historical'])
        self.assertEqual(historical['calculation']['results']['mean'],30)
        self.assertEqual(historical['parameters'][0]['id'],parameter['id'])
        self.assertEqual(historical['snapshot']['data']['rows'][-1],[50])
        pdf = client.get(f"/api/analyses/{analysis['id']}/export?format=pdf")
        self.assertEqual(pdf.status_code,200)
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.data)).pages)
        for word in ('Experiment 01','Experimental Error','Historical','Methodology','population'):
            self.assertIn(word,text)

    def test_cross_user_protection_all_resources(self):
        self.login()
        dataset = self.dataset()
        analysis = self.analysis(dataset)
        parameter = self.send('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Error','value':1}).json['parameter']
        other = self.app.test_client()
        csrf = other.get('/api/me').json['csrf_token']
        self.login(self.register('Other_User',other,csrf),client=other,csrf=csrf)
        self.assertEqual(other.get('/api/datasets').json['datasets'],[])
        self.assertEqual(other.get('/api/analyses').json['analyses'],[])
        paths = [('GET',f"/api/datasets/{dataset['id']}",None),('PUT',f"/api/datasets/{dataset['id']}",{}),
                 ('DELETE',f"/api/datasets/{dataset['id']}",None),('POST',f"/api/datasets/{dataset['id']}/duplicate",{}),
                 ('GET',f"/api/datasets/{dataset['id']}/export",None),('GET',f"/api/datasets/{dataset['id']}/parameters",None),
                 ('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Bad','value':1}),
                 ('GET',f"/api/analyses/{analysis['id']}",None),('GET',f"/api/analyses/{analysis['id']}/export?format=pdf",None),
                 ('DELETE',f"/api/analyses/{analysis['id']}",None),('POST',f"/api/analyses/{analysis['id']}/duplicate",{}),
                 ('PUT',f"/api/parameters/{parameter['id']}",{'name':'Bad','value':1}),('DELETE',f"/api/parameters/{parameter['id']}",None),
                 ('POST','/api/statistics/calculate',{'dataset_id':dataset['id']}),
                 ('POST','/api/analyses',{'dataset_id':dataset['id'],'name':'Bad'}),
                 ('POST','/api/datasets/compare',{'selections':[{'dataset_id':dataset['id']},{'dataset_id':dataset['id']}]})]
        for method,path,data in paths:
            with self.subTest(path=path,method=method):
                self.assertEqual(self.send(method,path,data,other,csrf).status_code,404)

    def test_unauthenticated_resources(self):
        for method,path,data in [('GET','/api/datasets',None),('POST','/api/datasets',{}),('GET','/api/analyses',None),('POST','/api/statistics/calculate',{})]:
            self.assertEqual(self.send(method,path,data).status_code,401)

    def test_custom_parameter_lifecycle_and_associations(self):
        self.login()
        dataset = self.dataset()
        analysis = self.analysis(dataset)
        other = self.dataset('Other dataset')
        payload = {'name':'Experimental Error','value':2.5,'unit':'%','formula':'error / value','description':'Measured separately','analysis_id':analysis['id']}
        response = self.send('POST',f"/api/datasets/{dataset['id']}/parameters",payload)
        parameter = response.json['parameter']
        self.assertEqual(self.send('POST',f"/api/datasets/{other['id']}/parameters",payload).status_code,400)
        response = self.send('PUT',f"/api/parameters/{parameter['id']}",{**payload,'value':'± 3%','name':'Uncertainty'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['parameter']['value'],'± 3%')
        self.assertEqual(self.send('POST','/api/statistics/calculate',{'dataset_id':dataset['id']}).status_code,200)
        self.assertEqual(len(self.client.get(f"/api/datasets/{dataset['id']}/parameters").json['parameters']),1)
        self.assertEqual(self.send('DELETE',f"/api/parameters/{parameter['id']}").status_code,200)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset['id']}/parameters").json['parameters'],[])

    def test_revision_conflict_and_rename(self):
        self.login()
        dataset = self.dataset()
        analysis = self.analysis(dataset)
        self.assertEqual(self.send('PUT',f"/api/datasets/{dataset['id']}",{'name':'Renamed','data':dataset['data'],'revision':1}).status_code,200)
        self.assertFalse(self.client.get(f"/api/analyses/{analysis['id']}").json['analysis']['historical'])
        self.assertEqual(self.send('PUT',f"/api/datasets/{dataset['id']}",{'name':'Changed','text':'1,2,3','revision':1}).status_code,200)
        self.assertEqual(self.send('PUT',f"/api/datasets/{dataset['id']}",{'name':'Stale','text':'5,6','revision':1}).status_code,409)
        self.assertEqual(self.send('POST','/api/analyses',{'name':'Stale','dataset_id':dataset['id'],'dataset_revision':1}).status_code,409)

    def test_duplicate_delete_and_cascades(self):
        self.login()
        dataset = self.dataset()
        analysis = self.analysis(dataset)
        self.send('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Shared','value':2})
        self.send('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Specific','value':3,'analysis_id':analysis['id']})
        copy = self.send('POST',f"/api/datasets/{dataset['id']}/duplicate",{}).json['dataset']
        self.assertEqual(copy['parameters'][0]['name'],'Shared')
        self.assertEqual(copy['analysis_count'],0)
        copied_analysis = self.send('POST',f"/api/analyses/{analysis['id']}/duplicate",{}).json['analysis']
        self.assertEqual(len(copied_analysis['parameters']),2)
        self.send('DELETE',f"/api/analyses/{analysis['id']}")
        self.assertEqual(len(self.client.get(f"/api/datasets/{dataset['id']}/parameters").json['parameters']),3)
        self.send('DELETE',f"/api/datasets/{dataset['id']}")
        self.assertEqual(self.client.get(f"/api/analyses/{copied_analysis['id']}").status_code,404)
        with closing(database.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_parameters WHERE dataset_id=?',(dataset['id'],)).fetchone()[0],0)

    def test_password_change_invalidates_all_sessions(self):
        account = self.register()
        self.login(account)
        other = self.app.test_client()
        csrf = other.get('/api/me').json['csrf_token']
        self.login(account,client=other,csrf=csrf)
        self.assertEqual(self.send('POST','/api/profile/password',{'current_password':'wrong','new_password':'new-password-123'}).status_code,401)
        self.assertEqual(self.send('POST','/api/profile/password',{'current_password':account['password'],'new_password':'new-password-123'}).status_code,200)
        self.assertIsNone(other.get('/api/me').json['user'])
        self.assertEqual(self.send('POST','/api/login',{'identifier':account['username'],'password':account['password']}).status_code,401)
        self.assertEqual(self.send('POST','/api/login',{'identifier':account['username'],'password':'new-password-123'}).status_code,200)

    def test_login_rate_limiting(self):
        for i in range(10):
            self.assertEqual(self.send('POST','/api/login',{'identifier':'missing','password':'wrong'}).status_code,401)
        response = self.send('POST','/api/login',{'identifier':'missing','password':'wrong'})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'900')
        with closing(database.connect(self.path)) as db, db:
            db.execute('UPDATE login_attempts SET attempted_at=0')
        self.assertEqual(self.send('POST','/api/login',{'identifier':'missing','password':'wrong'}).status_code,401)

    def test_password_whitespace_is_preserved(self):
        account = {'username':'Whitespace','email':'space@example.com','password':'  spaced password  '}
        self.assertEqual(self.send('POST','/api/signup',account).status_code,201)
        self.assertEqual(self.send('POST','/api/login',{'identifier':account['username'],'password':account['password']}).status_code,200)
        self.assertEqual(self.send('POST','/api/login',{'identifier':account['username'],'password':account['password'].strip()}).status_code,401)
        account = {**account,'username':'SpacesOnly','email':'allspace@example.com','password':' '*8}
        self.assertEqual(self.send('POST','/api/signup',account).status_code,201)
        self.assertEqual(self.send('POST','/api/login',{'identifier':account['username'],'password':account['password']}).status_code,200)

    def test_csv_import_and_limits(self):
        self.login()
        def upload(content, filename='data.csv', header='true'):
            builder = EnvironBuilder(path='/api/import/csv',method='POST',data={'file':(io.BytesIO(content),filename),'header':header},headers={'X-CSRF-Token':self.csrf})
            environ = builder.get_environ()
            try:
                response = self.client.open(environ,buffered=True)
                response.close()
                return response
            finally:
                environ['wsgi.input'].close()
                builder.close()
        response = upload(b'X,Y\n1,2\n3,\n')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['data']['rows'][1],['3',None])
        self.assertEqual(upload(b'1,2\n3,4\n',header='false').json['data']['columns'],['Column 1','Column 2'])
        for content,filename in [(b'', 'empty.csv'),(b'\xff','bad.csv'),(b'X,Y\n1\n','ragged.csv'),(b'a,a\n1,2','duplicate.csv'),(b'X\n\x00','binary.csv'),(b'X\n1','data.exe'),(b'X\n'+b'1\n'*10001,'large.csv')]:
            self.assertEqual(upload(content,filename).status_code,400)
        self.assertEqual(upload(b'a'*(2*1024*1024+1)).status_code,413)

    def test_csv_exports_and_formula_injection(self):
        self.login()
        response = self.send('POST','/api/datasets',{'name':"'; DROP TABLE users; --",'data':{'columns':['Label','Value'],'rows':[['=HYPERLINK("bad")',1],[' @command',2]]}})
        identifier = response.json['dataset']['id']
        exported = self.client.get(f'/api/datasets/{identifier}/export')
        self.assertIn("'=HYPERLINK",exported.data.decode('utf-8-sig'))
        self.assertIn("'@command",exported.data.decode('utf-8-sig'))
        dataset = self.dataset()
        analysis = self.analysis(dataset)
        self.assertEqual(self.client.get(f"/api/analyses/{analysis['id']}/export").status_code,200)
        self.assertEqual(self.client.get(f"/api/analyses/{analysis['id']}/export?format=invalid").status_code,400)
        self.assertEqual(self.send('POST','/api/login',{'identifier':"' OR 1=1 --",'password':'wrong'}).status_code,401)
        numeric = self.send('POST','/api/datasets',{'name':'Signed values','data':{'columns':['X'],'rows':[['-10'],['+20']]}}).json['dataset']
        with self.client.get(f"/api/datasets/{numeric['id']}/export") as exported:
            content = exported.data.decode('utf-8-sig')
            self.assertIn('-10\r\n',content)
            self.assertNotIn("'-10",content)

    def test_comparison_preview_and_catalog(self):
        self.login()
        first, second = self.dataset(), self.dataset('Experiment 02')
        result = self.send('POST','/api/datasets/compare',{'selections':[{'dataset_id':first['id']},{'dataset_id':second['id']}]})
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(result.json['comparisons']),2)
        self.assertEqual(self.send('POST','/api/statistics/preview',{'text':'1 2 3'}).json['calculation']['results']['mean'],2)
        self.assertIn('mean',self.client.get('/api/statistics/catalog').json['metrics'])

    def test_large_pdf_pagination(self):
        self.login()
        dataset = self.send('POST','/api/datasets',{'name':'Large report','data':{'columns':['Value'],'rows':[[i] for i in range(1000)]}}).json['dataset']
        analysis = self.analysis(dataset)
        self.send('POST',f"/api/datasets/{dataset['id']}/parameters",{'name':'Long annotation','value':'v'*1000,'formula':'f'*500,'description':'d'*2000})
        with self.client.get(f"/api/analyses/{analysis['id']}/export?format=pdf") as response:
            self.assertEqual(response.status_code,200)
            reader = PdfReader(io.BytesIO(response.data))
            self.assertGreater(len(reader.pages),1)
            text = '\n'.join(page.extract_text() for page in reader.pages)
            self.assertIn('First 40 of 1000',text)
            self.assertIn('full detail in CSV export',' '.join(text.split()))
            self.assertIn('xbar',text)

    def test_consistent_invalid_input_errors(self):
        self.login()
        for payload in ({}, {'name':'Bad','text':'1,,2'}, {'name':'Bad','data':{'columns':['X'],'rows':[]}}, {'name':'Bad','data':{'columns':['X'],'rows':[[True]]}}):
            response = self.send('POST','/api/datasets',payload)
            self.assertEqual(response.status_code,400)
            self.assertIn('error',response.json)
        self.assertEqual(self.send('POST','/api/statistics/calculate',{'dataset_id':[1]}).status_code,400)
        self.assertEqual(self.client.post('/api/datasets',data='invalid',headers={'X-CSRF-Token':self.csrf,'Content-Type':'application/json'}).status_code,400)

    def test_migration_preserves_legacy_users_and_sessions(self):
        legacy_path = str(Path(self.folder.name)/'legacy.sqlite3')
        salt = b'legacy-salt-12345'
        digest = password_hash('legacy-password',salt)
        token = 'existing-session-token'
        with closing(sqlite3.connect(legacy_path)) as db, db:
            db.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT COLLATE NOCASE UNIQUE,email TEXT COLLATE NOCASE UNIQUE,salt BLOB,password_hash BLOB);
                CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires REAL);''')
            db.execute('INSERT INTO users VALUES(1,?,?,?,?)',('Legacy','legacy@example.com',salt,digest))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),1,9999999999))
        app = create_app({**self.config,'DATABASE':legacy_path})
        client = app.test_client()
        client.set_cookie('session',token)
        self.assertEqual(client.get('/api/me').json['user']['username'],'Legacy')
        database.initialize(legacy_path)  # Idempotent migration.
        with closing(database.connect(legacy_path)) as db:
            self.assertEqual(db.execute('SELECT password_hash FROM users').fetchone()[0],digest)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],1)
        target = str(Path(self.folder.name)/'backup.sqlite3')
        database.backup(legacy_path,target)
        with closing(database.connect(target)) as db:
            self.assertEqual(db.execute('SELECT username FROM users').fetchone()[0],'Legacy')


if __name__ == '__main__':
    unittest.main()
