"""Signed public releases. No account credentials are shipped to listeners."""
import base64, hashlib, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION='0.14'
REPOSITORY='s4t0sh1-ops/pulse-releases'
MANIFEST_URL=f'https://github.com/{REPOSITORY}/releases/latest/download/pulse-update.json'
PUBLIC_KEY='rn5s1pF4Gt8eQE+dV7su19Kj7o3re5fGVvAf3U1l1QE='
MAX_SIZE=900*1024*1024

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?',value):raise ValueError('version')
    return tuple((list(map(int,value.split('.')))+[0,0,0])[:3])

def verify_manifest(envelope,current=VERSION):
    payload=envelope['release'];signature=base64.b64decode(envelope['signature'],validate=True)
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY)).verify(signature,canonical)
    newer=version_tuple(payload['version'])>version_tuple(current)
    url=urlparse(payload['url'])
    prefix=f'/{REPOSITORY}/releases/download/v{payload["version"]}/'
    if url.scheme!='https' or url.netloc!='github.com' or not url.path.startswith(prefix) or not url.path.endswith('.exe') or url.query or url.fragment:raise ValueError('url')
    if not re.fullmatch('[a-f0-9]{64}',payload['sha256']) or not 1000000<=payload['size']<=MAX_SIZE:raise ValueError('file')
    return payload if newer else None

def check_release(current=VERSION):
    response=requests.get(MANIFEST_URL,timeout=(6,15),headers={'User-Agent':'Pulse/'+VERSION},stream=True)
    if response.status_code==404:return None
    response.raise_for_status();raw=b''
    try:
        for chunk in response.iter_content(8192):
            raw+=chunk
            if len(raw)>65536:raise ValueError('manifest_size')
    finally:response.close()
    return verify_manifest(json.loads(raw),current)

def download_release(release,folder,progress=lambda _:None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    path=folder/('Pulse-'+release['version']+'.exe');partial=path.with_suffix('.part')
    digest=hashlib.sha256();count=0
    try:
        with requests.get(release['url'],stream=True,timeout=(8,25),headers={'User-Agent':'Pulse/'+VERSION}) as response:
            response.raise_for_status()
            with partial.open('wb') as out:
                for chunk in response.iter_content(256*1024):
                    count+=len(chunk)
                    if count>release['size'] or count>MAX_SIZE:raise ValueError('size')
                    digest.update(chunk);out.write(chunk);progress(int(count*100/release['size']))
        if count!=release['size'] or digest.hexdigest()!=release['sha256']:raise ValueError('checksum')
        partial.replace(path);return path
    except Exception:
        partial.unlink(missing_ok=True);raise

def install_release(path,release,target=None,pid=None):
    """Replace only this running EXE after it exits, with rollback on failure."""
    target=Path(target or sys.executable).resolve();path=Path(path).resolve()
    if not getattr(sys,'frozen',False) and pid is None:raise RuntimeError('source_run')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=release['sha256']:raise ValueError('checksum')
    def quote(value):return "'"+str(value).replace("'","''")+"'"
    script=path.parent/('install-'+str(int(time.time()))+'.ps1')
    backup=target.with_suffix('.previous.exe')
    content=f'''$ErrorActionPreference = 'Stop'
$target={quote(target)}
$source={quote(path)}
$backup={quote(backup)}
try {{ Wait-Process -Id {int(pid or os.getpid())} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
if (Get-Process -Id {int(pid or os.getpid())} -ErrorAction SilentlyContinue) {{ exit 1 }}
try {{
  $hasher=[System.Security.Cryptography.SHA256]::Create()
  $stream=[System.IO.File]::OpenRead($source)
  try {{ $hash=[System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }} finally {{ $stream.Dispose(); $hasher.Dispose() }}
  if ($hash -ne {quote(release['sha256'])}) {{ throw 'Invalid update' }}
  Copy-Item -LiteralPath $target -Destination $backup -Force
  $installed=$false
  for ($attempt=0; $attempt -lt 30; $attempt++) {{
    try {{ Copy-Item -LiteralPath $source -Destination $target -Force; $installed=$true; break }} catch {{ Start-Sleep -Milliseconds 300 }}
  }}
  if (-not $installed) {{ throw 'Application is still locked' }}
  $env:PYINSTALLER_RESET_ENVIRONMENT='1'
  Start-Process -FilePath $target
}} catch {{
  [System.IO.File]::WriteAllText(($source+'.install-error.txt'),[string]$_)
  if (Test-Path -LiteralPath $backup) {{ Copy-Item -LiteralPath $backup -Destination $target -Force; Start-Process -FilePath $target }}
}}
'''
    script.write_text(content,encoding='utf-8-sig')
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=str(path.parent))
