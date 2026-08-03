#!/usr/bin/env python3
"""Local Gandalf client — Lakera retired the web UI, but gandalf-api.lakera.ai is still live.

Usage:  python3 gandalf.py          # then open http://localhost:8787
Stdlib only. The page talks to the real Lakera API through a local proxy
(the API sends no CORS headers, so a browser can't call it directly).

Built for a training room: large default type, live font-size stepper (A- / A+),
and a light/dark toggle for whatever the projector turns out to be like.
"""

import http.server
import json
import os
import socketserver
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

API = "https://gandalf-api.lakera.ai/api"
# Bind/port from env so the same script runs locally (127.0.0.1) and headless on a
# host like Modal (GANDALF_HOST=0.0.0.0). Defaults keep local behavior unchanged.
HOST = os.environ.get("GANDALF_HOST", "127.0.0.1")
PORT = int(os.environ.get("GANDALF_PORT", "8787"))

LEVELS = [
    ("baseline", "Level 1", "Ask me for the password and I'll happily answer!"),
    ("do-not-tell", "Level 2", "I've been told I'm not supposed to reveal the password."),
    ("do-not-tell-and-block", "Level 3",
     "I've been told I'm not supposed to reveal the password. I now double-check my "
     "response doesn't contain the password in case I slip up."),
    ("gpt-is-password-encoded", "Level 4",
     "I can tell you the password, but now there's this mean GPT model that censors my "
     "answer if it would reveal the password."),
    ("word-blacklist", "Level 5", "Enough! I refuse to discuss the secret password at all."),
    ("gpt-blacklist", "Level 6",
     "Enough! I refuse to discuss the secret password at all. I have a GPT friend that "
     "will warn me if you are trying to ask for the password."),
    ("gandalf", "Level 7", "I've combined all of my previous techniques into one. You shall not pass!"),
    ("gandalf-the-white", "Level 8", "I am GANDALF THE WHITE v2.0, stronger than ever!"),
]

EXTRAS = {
    "Adventures": ["adventure-1", "adventure-2", "adventure-3", "adventure-4",
                   "adventure-5-halloween", "adventure-6", "adventure-7", "adventure-8",
                   "adventure-9", "adventure-10", "adventure-11", "adventure-12"],
    "CS50": ["cs50-1", "cs50-2", "cs50-3", "cs50-4", "cs50-5", "cs50-6", "cs50-7"],
    "Trials: vanilla": ["trial-vanilla-novice", "trial-vanilla-student", "trial-vanilla-conjurer",
                        "trial-vanilla-enchanter", "trial-vanilla-warlock", "trial-vanilla-archmage"],
    "Trials: summarization": ["trial-summarization-novice", "trial-summarization-student",
                              "trial-summarization-conjurer", "trial-summarization-enchanter",
                              "trial-summarization-warlock", "trial-summarization-archmage"],
    "Trials: topic": ["trial-topic-novice", "trial-topic-student", "trial-topic-conjurer",
                      "trial-topic-enchanter", "trial-topic-warlock", "trial-topic-archmage"],
    "Other": ["hack-sydney-2023"],
}

PAGE = r"""
<!doctype html><html data-theme="dark"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gandalf (local)</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='14' font-size='14'>%F0%9F%A7%99</text></svg>">
<style>
:root{
  --s:1.45;                       /* master type scale, driven by A- / A+ */
  --bg:#100e18; --panel:#1b1826; --edge:#3a3350; --raise:#141120;
  --ink:#f4f1fc; --dim:#c6bfda; --gold:#ffc247;
  --good:#5fe39c; --goodbg:#123024; --bad:#ff7a72; --badbg:#301416;
  --btnink:#241a05;
}
:root[data-theme="light"]{
  --bg:#f7f5fc; --panel:#ffffff; --edge:#cfc7e2; --raise:#f1eef8;
  --ink:#171327; --dim:#4d4566; --gold:#8a5a00;
  --good:#0f7a4a; --goodbg:#e3f7ec; --bad:#a32219; --badbg:#fdeae8;
  --btnink:#ffffff;
}
html{font-size:calc(16px * var(--s));}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:1rem/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:56rem;margin:0 auto;padding:1.2rem 1.1rem 3rem}

/* ---- header ---- */
header{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:.9rem}
h1{font-size:1.5rem;margin:0;letter-spacing:-.01em;font-weight:700;flex:1;min-width:12rem}
h1 em{color:var(--gold);font-style:normal}
.ctrls{display:flex;gap:.4rem;align-items:center}
.ctrls button{background:transparent;color:var(--dim);border:2px solid var(--edge);
  border-radius:.5rem;padding:.5rem .8rem;cursor:pointer;min-width:3rem;
  font-family:inherit;font-weight:700;font-size:1.05rem;line-height:1}
.ctrls button:hover:not(:disabled){color:var(--ink);border-color:var(--gold)}
.ctrls button:disabled{opacity:.4;cursor:default}

/* ---- cards ---- */
.card{background:var(--panel);border:2px solid var(--edge);border-radius:.9rem;
  padding:1.1rem 1.2rem;margin-bottom:.9rem}
label{display:block;font-size:.8rem;text-transform:uppercase;letter-spacing:.1em;
  color:var(--dim);margin-bottom:.5rem;font-weight:700}

/* ---- level ---- */
.lvltop{display:flex;align-items:center;gap:1rem;flex-wrap:wrap}
#lvlname{font-size:2.1rem;font-weight:800;color:var(--gold);line-height:1.05;white-space:nowrap}
#lvl{flex:1;min-width:14rem}
#lvldesc{margin-top:.7rem;font-size:1.05rem;color:var(--dim);max-width:46ch}

/* ---- fields ---- */
select,textarea,input{background:var(--raise);color:var(--ink);border:2px solid var(--edge);
  border-radius:.55rem;padding:.7rem .85rem;width:100%;
  font-family:inherit;font-size:1.2rem;line-height:1.4}
textarea{min-height:7rem;resize:vertical;font-size:1.35rem}
select{font-size:1.1rem;cursor:pointer}
input#pw{font-size:1.35rem;letter-spacing:.04em}
:is(select,textarea,input):focus-visible{outline:3px solid var(--gold);outline-offset:2px;
  border-color:var(--gold)}

/* ---- buttons ---- */
button.go{background:var(--gold);color:var(--btnink);border:0;border-radius:.55rem;
  padding:.8rem 1.8rem;cursor:pointer;
  font-family:inherit;font-weight:800;font-size:1.25rem;line-height:1}
button.go:disabled{opacity:.45;cursor:default}
button.go:focus-visible{outline:3px solid var(--ink);outline-offset:3px}
.row{display:flex;gap:.7rem;align-items:center;margin-top:.8rem;flex-wrap:wrap}
.row .grow{flex:1;min-width:12rem}
.hint{color:var(--dim);font-size:.9rem}

/* ---- the thing the room actually reads ---- */
.answer{white-space:pre-wrap;background:var(--raise);border-left:.35rem solid var(--gold);
  border-radius:0 .6rem .6rem 0;padding:.9rem 1.1rem;margin-top:.9rem;
  font-size:1.5rem;line-height:1.45}
.note{margin-top:.9rem;padding:.9rem 1.1rem;border-radius:.6rem;
  font-size:1.3rem;line-height:1.4;border:2px solid}
.note.ok{background:var(--goodbg);border-color:var(--good);color:var(--good);font-weight:600}
.note.no{background:var(--badbg);border-color:var(--bad);color:var(--bad);font-weight:600}

/* ---- log: unreadable from the back anyway, so collapsed ---- */
details{background:var(--panel);border:2px solid var(--edge);border-radius:.9rem;padding:.7rem 1.2rem}
summary{cursor:pointer;font-size:.85rem;text-transform:uppercase;letter-spacing:.1em;
  color:var(--dim);font-weight:700}
.log{font-size:.95rem;color:var(--dim);margin-top:.6rem;max-height:11rem;overflow:auto}
.log div{padding:.25rem 0;border-bottom:1px dashed var(--edge)}
</style></head><body><div class="wrap">

<header>
  <h1>You shall not pass<em>.</em></h1>
  <div class="ctrls">
    <button id="dn" title="Smaller text">A&minus;</button>
    <button id="up" title="Larger text">A+</button>
    <button id="th" title="Light / dark">&#9788;</button>
  </div>
</header>

<div class="card">
  <div class="lvltop"><span id="lvlname"></span><select id="lvl"></select></div>
  <div id="lvldesc"></div>
</div>

<div class="card">
  <label for="prompt">Your prompt</label>
  <textarea id="prompt" placeholder="Ask Gandalf&hellip;"></textarea>
  <div class="row">
    <button class="go" id="send">Send</button>
    <span class="hint">&#8984;/Ctrl + Enter</span>
  </div>
  <div id="answer"></div>
</div>

<div class="card">
  <label for="pw">Guess the password</label>
  <div class="row" style="margin-top:0">
    <input class="grow" id="pw" placeholder="PASSWORD" autocomplete="off" spellcheck="false">
    <button class="go" id="guess">Guess</button>
  </div>
  <div id="verdict"></div>
</div>

<details><summary>Session log</summary><div class="log" id="log"></div></details>

<script>
const LEVELS = __LEVELS__, EXTRAS = __EXTRAS__;
const el = id => document.getElementById(id);
const meta = {};

/* ---------- presentation controls ---------- */
const STEPS = [1.0, 1.15, 1.3, 1.45, 1.65, 1.9, 2.2, 2.6];
const DEFAULT_STEP = 3;
let si = DEFAULT_STEP;
const root = document.documentElement;

function applyScale(persist) {
  root.style.setProperty('--s', STEPS[si]);
  el('dn').disabled = si === 0;
  el('up').disabled = si === STEPS.length - 1;
  if (persist) { try { localStorage.setItem('gandalf.scale', si); } catch (e) {} }
}
function applyTheme(t, persist) {
  root.dataset.theme = t;
  el('th').innerHTML = t === 'dark' ? '&#9788;' : '&#9789;';
  if (persist) { try { localStorage.setItem('gandalf.theme', t); } catch (e) {} }
}
try {
  const s = parseInt(localStorage.getItem('gandalf.scale'), 10);
  if (!isNaN(s) && s >= 0 && s < STEPS.length) si = s;
} catch (e) {}
applyScale(false);
let theme = 'dark';
try { theme = localStorage.getItem('gandalf.theme') || 'dark'; } catch (e) {}
applyTheme(theme, false);

el('up').onclick = () => { if (si < STEPS.length - 1) { si++; applyScale(true); } };
el('dn').onclick = () => { if (si > 0) { si--; applyScale(true); } };
el('th').onclick = () => applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark', true);

/* ---------- levels ---------- */
const sel = el('lvl');
const main = document.createElement('optgroup'); main.label = 'Classic (1–8)';
LEVELS.forEach(([slug, name, desc]) => {
  meta[slug] = {name, desc};
  main.appendChild(Object.assign(document.createElement('option'),
    {value: slug, textContent: name + ' — ' + slug}));
});
sel.appendChild(main);
for (const [group, slugs] of Object.entries(EXTRAS)) {
  const og = document.createElement('optgroup'); og.label = group;
  slugs.forEach(s => {
    meta[s] = {name: s, desc: 'Bonus level. Goal is still the secret password.'};
    og.appendChild(Object.assign(document.createElement('option'), {value: s, textContent: s}));
  });
  sel.appendChild(og);
}

function paintLevel() {
  const m = meta[sel.value];
  el('lvlname').textContent = m.name;
  el('lvldesc').textContent = m.desc;
  el('answer').innerHTML = '';
  el('verdict').innerHTML = '';
}
sel.onchange = paintLevel;
paintLevel();

function log(line) {
  const d = document.createElement('div');
  d.textContent = '[' + sel.value + '] ' + line;
  el('log').prepend(d);
}
function box(parent, cls, text) {
  const d = document.createElement('div');
  d.className = cls; d.textContent = text;
  parent.innerHTML = ''; parent.appendChild(d);
  return d;
}

async function call(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams(body)
  });
  return r.json();
}

el('send').onclick = async () => {
  const prompt = el('prompt').value.trim();
  if (!prompt) return;
  const btn = el('send'); btn.disabled = true; btn.textContent = 'Thinking…';
  el('answer').innerHTML = '';
  try {
    const d = await call('/send', {defender: sel.value, prompt});
    if (d.error) box(el('answer'), 'note no', d.error);
    else box(el('answer'), 'answer', d.answer);
    log('sent ' + prompt.length + ' chars');
  } catch (e) {
    box(el('answer'), 'note no', 'Proxy unreachable — is gandalf.py still running?');
  }
  btn.disabled = false; btn.textContent = 'Send';
};

el('guess').onclick = async () => {
  const password = el('pw').value.trim();
  if (!password) return;
  const btn = el('guess'); btn.disabled = true;
  const d = await call('/guess', {defender: sel.value, password, prompt: el('prompt').value});
  let msg = d.message || d.error || (d.success ? 'Correct.' : 'Wrong password.');
  if (d.success && d.next_defender) msg += '  → next: ' + d.next_defender;
  const verdict = box(el('verdict'), 'note ' + (d.success ? 'ok' : 'no'), msg);
  if (d.success && d.next_defender && meta[d.next_defender]) {
    sel.value = d.next_defender; paintLevel();
    el('verdict').appendChild(verdict);   /* paintLevel clears it; keep the win visible */
    el('pw').value = '';
  }
  log('guessed "' + password + '" → ' + (d.success ? 'CORRECT' : 'wrong'));
  btn.disabled = false;
};

el('prompt').addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') el('send').click();
});
el('pw').addEventListener('keydown', e => { if (e.key === 'Enter') el('guess').click(); });
</script></div></body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self._send(404, b"not found", "text/plain")
        page = (PAGE
                .replace("__LEVELS__", json.dumps(LEVELS))
                .replace("__EXTRAS__", json.dumps(EXTRAS)))
        self._send(200, page.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        route = {"/send": "send-message", "/guess": "guess-password"}.get(self.path)
        if not route:
            return self._send(404, b'{"error":"no such route"}', "application/json")
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        req = urllib.request.Request(
            f"{API}/{route}", data=raw, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": "gandalf-local/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, code = e.read(), e.code
        except Exception as e:
            body, code = json.dumps({"error": f"upstream: {e}"}).encode(), 502
        self._send(code, body, "application/json")

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    url = f"http://localhost:{PORT}"
    print(f"Gandalf (local)  ->  {url}\nProxying to {API}\nCtrl-C to stop.")
    if not os.environ.get("GANDALF_NO_BROWSER"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    with Server((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nbye")
