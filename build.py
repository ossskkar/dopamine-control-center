#!/usr/bin/env python3
"""Encrypt app.html into index.html behind a passphrase lock screen.

Usage:  python3 build.py            (prompts for passphrase)
        python3 build.py <pass>     (passphrase as argument)

Deploy index.html to GitHub Pages. Keep app.html out of git (.gitignore).
"""
import base64, os, sys, getpass, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 600_000

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>PROJECT 100K</title>
<style>
:root{--ink:#0d0b1e;--ink-2:#161330;--ink-3:#201b42;--line:#2d2756;--moss:#8b86b8;--fog:#cfcbe8;--white:#f4f2ff;--amber:#fb5fa6;--grad:linear-gradient(135deg,#7c3aed,#fb5fa6)}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--ink);color:var(--fog);font-family:"Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background-image:radial-gradient(ellipse 90% 40% at 15% -5%, #7c3aed33 0%, transparent 55%),radial-gradient(ellipse 70% 35% at 95% 0%, #fb5fa622 0%, transparent 55%)}
.lock{background:var(--ink-2);border:1px solid var(--line);border-radius:18px;padding:30px 26px;width:100%;max-width:360px;box-shadow:0 8px 24px #05041077;text-align:center}
.brand{font-family:"Arial Narrow","Helvetica Neue Condensed","Segoe UI",sans-serif;font-stretch:condensed;font-weight:800;font-size:1.55rem;letter-spacing:.12em;color:var(--white);text-transform:uppercase;margin-bottom:6px}
.brand span{background:linear-gradient(90deg,#a78bfa,#fb5fa6);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{font-size:.62rem;text-transform:uppercase;letter-spacing:.22em;color:var(--moss);margin-bottom:22px}
input{width:100%;background:var(--ink-3);border:1px solid var(--line);border-radius:10px;color:var(--white);padding:13px 14px;font-size:1rem;font-family:inherit;outline:none;text-align:center;margin-bottom:12px}
input:focus{border-color:var(--amber)}
button{width:100%;background:var(--grad);color:#fff;border:none;border-radius:10px;padding:13px;font-size:.75rem;text-transform:uppercase;letter-spacing:.15em;font-weight:800;cursor:pointer;font-family:inherit;box-shadow:0 4px 18px #7c3aed55}
button:disabled{opacity:.5}
.err{font-size:.72rem;color:#ff6b5e;margin-top:12px;min-height:1em}
</style>
</head>
<body>
<form class="lock" id="f">
  <div class="brand">PROJECT <span>100K</span></div>
  <div class="sub">Private — enter passphrase</div>
  <input type="password" id="pw" autocomplete="current-password" autofocus>
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
  try{sessionStorage.setItem('p100k_k',btoa(String.fromCharCode(...new Uint8Array(rk))));}catch(e){}
  show(html);
}
async function tryCached(){
  const k=sessionStorage.getItem('p100k_k'); if(!k)return;
  try{
    const raw=b64(PAYLOAD), iv=raw.slice(16,28), ct=raw.slice(28);
    const key=await crypto.subtle.importKey('raw',b64(k),{name:'AES-GCM'},false,['decrypt']);
    show(await decrypt(key,iv,ct));
  }catch(e){sessionStorage.removeItem('p100k_k');}
}
document.getElementById('f').addEventListener('submit',async ev=>{
  ev.preventDefault();
  const btn=document.getElementById('go'),err=document.getElementById('err');
  btn.disabled=true;btn.textContent='Unlocking…';err.textContent='';
  try{await unlock(document.getElementById('pw').value);}
  catch(e){err.textContent='Wrong passphrase';btn.disabled=false;btn.textContent='Unlock';document.getElementById('pw').select();}
});
if(!crypto.subtle)document.getElementById('err').textContent='Needs HTTPS or localhost to unlock.';
else if(document.readyState==='complete')tryCached();
else window.addEventListener('load',tryCached);
</script>
</body>
</html>
"""

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, 'app.html'), 'rb').read()
    pw = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass('Passphrase: ')
    if not pw:
        sys.exit('Empty passphrase, aborting.')
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, ITER, dklen=32)
    ct = AESGCM(key).encrypt(iv, src, None)
    payload = base64.b64encode(salt + iv + ct).decode()
    out = TEMPLATE.replace('__PAYLOAD__', payload).replace('__ITER__', str(ITER))
    open(os.path.join(here, 'index.html'), 'w').write(out)
    print(f'index.html written ({len(out)//1024} KB) — deploy it, keep app.html private.')

if __name__ == '__main__':
    main()
