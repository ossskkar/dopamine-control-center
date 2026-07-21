#!/usr/bin/env python3
"""Encrypt app.html into index.html, locked with your GitHub token.

The token is the single secret: it decrypts the page AND is used by the
app to sync data to the private p100k-data repo. Rotating the token means
re-running this script and pushing the new index.html.

Usage:  python3 build.py            (prompts for token)
        python3 build.py <token>    (token as argument)

Deploy index.html to GitHub Pages. Keep app.html out of git (.gitignore).
"""
import base64, os, sys, getpass, hashlib, urllib.request
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 600_000

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Dopamine Control Center</title>
<style>
/* the lock screen is the hub's front door, so it wears the hub's blue/cyan —
   not Project 100K's violet. Type sizes match .hub-title / .hub-tag exactly. */
:root{--ink:#0d0b1e;--ink-2:#161330;--ink-3:#201b42;--line:#26386b;--fog:#cfcbe8;--white:#f4f2ff;--cyan:#38dbd0;--grad:linear-gradient(135deg,#2d6cf6,#38dbd0)}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{background:var(--ink);color:var(--fog);font-family:"Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background-image:radial-gradient(ellipse 90% 40% at 15% -5%, #2d6cf633 0%, transparent 55%),radial-gradient(ellipse 70% 35% at 95% 0%, #38dbd022 0%, transparent 55%)}
.lock{background:var(--ink-2);border:1px solid var(--line);border-radius:24px;padding:34px 26px 30px;width:100%;max-width:360px;box-shadow:0 8px 24px #05041077;text-align:center;position:relative;overflow:hidden}
.lock::after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse 80% 50% at 80% -10%, #2d6cf62e, transparent 60%);pointer-events:none}
.brand{font-family:"Arial Narrow","Helvetica Neue Condensed","Segoe UI",sans-serif;font-stretch:condensed;font-weight:800;font-size:2rem;line-height:1.15;letter-spacing:.14em;color:var(--white);text-transform:uppercase}
.brand span{background:linear-gradient(90deg,#7fb3ff,#38dbd0);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{font-size:.66rem;text-transform:uppercase;letter-spacing:.3em;color:#7f9fca;margin:8px 0 26px}
input{position:relative;z-index:1;width:100%;background:var(--ink-3);border:1px solid var(--line);border-radius:10px;color:var(--white);padding:13px 14px;font-size:1rem;font-family:inherit;outline:none;text-align:center;margin-bottom:12px}
input:focus{border-color:var(--cyan)}
button{position:relative;z-index:1;width:100%;background:var(--grad);color:#fff;border:none;border-radius:10px;padding:13px;font-size:.75rem;text-transform:uppercase;letter-spacing:.15em;font-weight:800;cursor:pointer;font-family:inherit;box-shadow:0 4px 18px #2d6cf655}
button:active{transform:scale(.98)}
button:disabled{opacity:.5}
.err{font-size:.72rem;color:#ff6b5e;margin-top:12px;min-height:1em}
</style>
</head>
<body>
<form class="lock" id="f">
  <div class="brand">Dopamine<br><span>Control Center</span></div>
  <div class="sub">Private — enter your token</div>
  <input type="password" id="pw" autocomplete="off" autofocus>
  <button id="go">Unlock</button>
  <div class="err" id="err"></div>
</form>
<script>
const PAYLOAD='__PAYLOAD__';
const ITER=__ITER__;
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
function show(html){document.open();document.write(html);document.close();}
async function decrypt(key,iv,ct){
  const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv},key,ct);
  return new TextDecoder().decode(pt);
}
async function unlock(pass){
  const raw=b64(PAYLOAD), salt=raw.slice(0,16), iv=raw.slice(16,28), ct=raw.slice(28);
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pass),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:ITER,hash:'SHA-256'},km,{name:'AES-GCM',length:256},true,['decrypt']);
  const html=await decrypt(key,iv,ct);
  const rk=await crypto.subtle.exportKey('raw',key);
  try{
    localStorage.setItem('p100k_k',btoa(String.fromCharCode(...new Uint8Array(rk))));
    // the token doubles as the sync credential — hand it to the app
    let c={}; try{c=JSON.parse(localStorage.getItem('p100k_sync_v1'))||{}}catch(e){}
    if(c.token!==pass) localStorage.setItem('p100k_sync_v1',JSON.stringify({token:pass,owner:''}));
  }catch(e){}
  show(html);
}
async function tryCached(){
  const k=localStorage.getItem('p100k_k'); if(!k)return;
  try{
    const raw=b64(PAYLOAD), iv=raw.slice(16,28), ct=raw.slice(28);
    const key=await crypto.subtle.importKey('raw',b64(k),{name:'AES-GCM'},false,['decrypt']);
    show(await decrypt(key,iv,ct));
  }catch(e){localStorage.removeItem('p100k_k');}
}
document.getElementById('f').addEventListener('submit',async ev=>{
  ev.preventDefault();
  const btn=document.getElementById('go'),err=document.getElementById('err');
  btn.disabled=true;btn.textContent='Unlocking…';err.textContent='';
  try{await unlock(document.getElementById('pw').value);}
  catch(e){err.textContent='Wrong token';btn.disabled=false;btn.textContent='Unlock';document.getElementById('pw').select();}
});
if(!crypto.subtle)document.getElementById('err').textContent='Needs HTTPS or localhost to unlock.';
else if(document.readyState==='complete')tryCached();
else window.addEventListener('load',tryCached);
</script>
</body>
</html>
"""

def token_expiry(pw):
    """When does this token expire? Returns ISO-8601 UTC, or None.

    The app can't ask GitHub itself — the expiry header isn't CORS-exposed to
    browser JS — so we stamp it into the page at build time. Classic PATs with
    no expiry return None, and the reminder simply never fires.
    """
    try:
        req = urllib.request.Request('https://api.github.com/user', headers={
            'Authorization': 'Bearer ' + pw,
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'p100k-build',
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.headers.get('github-authentication-token-expiration')
    except Exception:
        return None
    if not raw:
        return None
    try:
        # header looks like '2026-10-18 20:12:57 UTC'
        return datetime.strptime(raw.strip().replace(' UTC', ''),
                                 '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, 'app.html'), 'rb').read()
    tokenfile = os.path.join(here, '.token')
    if len(sys.argv) > 1:
        pw = sys.argv[1]
    elif os.path.exists(tokenfile):
        pw = open(tokenfile).read().strip()
    else:
        pw = getpass.getpass('GitHub token: ')
    if not pw:
        sys.exit('Empty token, aborting.')
    exp = token_expiry(pw)
    if exp:
        src = src.replace(b'__TOKEN_EXP__', exp.encode())
        left = (datetime.strptime(exp, '%Y-%m-%dT%H:%M:%SZ') - datetime.utcnow()).days
        print(f'token expires {exp} ({left} days) — reminder fires with 7 days left')
    else:
        print('could not read token expiry (offline, or a token that never expires) — no reminder')
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, ITER, dklen=32)
    ct = AESGCM(key).encrypt(iv, src, None)
    payload = base64.b64encode(salt + iv + ct).decode()
    out = TEMPLATE.replace('__PAYLOAD__', payload).replace('__ITER__', str(ITER))
    outpath = os.path.join(here, 'index.html')
    srcpath = os.path.join(here, 'app.html')
    stale = os.path.getmtime(outpath) - os.path.getmtime(srcpath) if os.path.exists(outpath) else None
    open(outpath, 'w').write(out)
    if stale is not None and stale < 0:
        mins = int(-stale // 60)
        print(f'app.html had been {mins} min ahead of the old index.html — now rebuilt.')
    print(f'index.html written ({len(out)//1024} KB) — deploy it, keep app.html private.')

if __name__ == '__main__':
    main()
