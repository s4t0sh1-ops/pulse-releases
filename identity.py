"""Provider-confirmed sign in. Provider passwords and access tokens are not saved."""
import base64,hashlib,hmac,json,secrets,time,re
from http.server import HTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlencode,urlparse,parse_qs
import requests
import jwt

class SignInError(Exception):pass

class GoogleSignIn:
    def __init__(self,config):
        self.config=config;self.state=secrets.token_urlsafe(32);self.nonce=secrets.token_urlsafe(32)
        self.verifier=secrets.token_urlsafe(64);self.code=None;self.denied=False;self.cancelled=False
        flow=self;path='/callback/'+secrets.token_urlsafe(20)
        class Callback(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                url=urlparse(self.path);query=parse_qs(url.query)
                valid=url.path==path and len(query.get('state',[]))==1 and hmac.compare_digest(query['state'][0],flow.state)
                if not valid:self.send_error(400);return
                if query.get('error'):flow.denied=True
                elif len(query.get('code',[]))==1 and len(query['code'][0])<8192:flow.code=query['code'][0]
                else:self.send_error(400);return
                body='<meta charset="utf-8"><title>Pulse</title><body style="background:#111a1e;color:white;font:20px system-ui;padding:60px">Вернись в Pulse, чтобы завершить вход.</body>'.encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        self.server=HTTPServer(('127.0.0.1',0),Callback);self.server.timeout=.5
        self.redirect='http://127.0.0.1:'+str(self.server.server_port)+path
        challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('=')
        self.url='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(dict(client_id=config['client_id'],redirect_uri=self.redirect,response_type='code',scope='openid email profile',state=self.state,nonce=self.nonce,code_challenge=challenge,code_challenge_method='S256',prompt='select_account'))
    def wait(self):
        try:
            deadline=time.monotonic()+180
            while not self.code and not self.denied and not self.cancelled and time.monotonic()<deadline:self.server.handle_request()
            if not self.code or self.cancelled:raise SignInError()
            response=requests.post('https://oauth2.googleapis.com/token',data=dict(client_id=self.config['client_id'],client_secret=self.config.get('client_secret',''),code=self.code,code_verifier=self.verifier,grant_type='authorization_code',redirect_uri=self.redirect),timeout=(5,12))
            response.raise_for_status();token=response.json()['id_token']
            key=jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs',timeout=10).get_signing_key_from_jwt(token)
            identity=jwt.decode(token,key.key,algorithms=['RS256'],audience=self.config['client_id'],issuer=['https://accounts.google.com','accounts.google.com'],options={'require':['exp','iat','sub','aud','iss','nonce']})
            if not hmac.compare_digest(identity['nonce'],self.nonce) or identity.get('email_verified') is not True:raise SignInError()
            return {'provider':'google','provider_id':identity['sub'],'name':identity.get('name') or identity['email'].split('@')[0],'email':identity['email']}
        finally:self.server.server_close()

class TelegramSignIn:
    def __init__(self,config):self.base=config['server'].rstrip('/');self.cancelled=False;self.folder=config.get('_data_dir')
    def begin(self):
        response=requests.post(self.base+'/challenge',json={},timeout=(5,10));response.raise_for_status();self.challenge=response.json()
        url=self.challenge['url']
        if not re.fullmatch(r'[a-f0-9]{48}',self.challenge.get('id','')) or url!='https://t.me/PulseMusicHelpBot?start='+self.challenge['id']:raise SignInError()
        return url
    def wait(self):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline and not self.cancelled:
            response=requests.post(self.base+'/poll',json={'id':self.challenge['id'],'secret':self.challenge['secret']},timeout=(5,10))
            response.raise_for_status();result=response.json()
            if result.get('identity'):
                if result.get('session') and self.folder:
                    from cloud_sync import save_session
                    save_session(self.folder,result['identity']['provider_id'],result['session']['token'])
                return dict(result['identity'],provider='telegram')
            if result.get('cancelled'):raise SignInError()
            time.sleep(2)
        raise SignInError()
