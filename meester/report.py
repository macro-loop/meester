"""Turn the local job store into something a person can actually read.

The store is JSONL and the CLI prints a terminal table. Neither is usable by the
person the system exists for. This writes a self-contained HTML file she opens by
double-clicking - no terminal, no server, works offline.

Deliberately does no ranking. Ranking needs her resume, and inventing a relevance
score without one would be worse than honest chronological order. What it does
instead is make filtering instant, because a few hundred unranked roles becomes
browsable the moment you narrow to one function.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# json embedded in a <script> must not be able to close the tag early; a job
# description or title containing "</script>" would otherwise break the page.
_JSON_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}


def _safe_json(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, esc in _JSON_ESCAPES.items():
        text = text.replace(char, esc)
    return text


def _age_days(row: dict) -> float | None:
    stamp = row.get("posted_at") or row.get("first_seen")
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _prepare(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        age = _age_days(r)
        out.append(
            {
                "t": r.get("title") or "",
                "c": r.get("company") or "",
                "l": r.get("location_raw") or ", ".join(r.get("locations") or []) or "Remote",
                "u": r.get("apply_url") or r.get("url") or "",
                "d": r.get("department") or r.get("team") or "",
                "s": r.get("salary_raw") or "",
                "k": sorted(r.get("remote_countries") or []),
                "a": round(age, 1) if age is not None else None,
                "f": r.get("first_seen") or "",
            }
        )
    # Newest first; unknown ages last rather than pretending they are fresh.
    out.sort(key=lambda x: (x["a"] is None, x["a"] if x["a"] is not None else 0))
    return out


def render_report_html(rows: list[dict], server_token: str | None = None) -> str:
    """The jobs page. Two variants of one template:

    server_token=None  -> the offline Desktop file. No secret in it, ever - it
                          lives in a folder Finder can reach and gets no writes.
    server_token=str   -> the same page served from localhost, where the token
                          lets the update button actually install.
    """
    jobs = _prepare(rows)
    companies = sorted({j["c"] for j in jobs})
    generated = datetime.now().strftime("%A %d %B, %H:%M")
    fresh_24h = sum(1 for j in jobs if j["a"] is not None and j["a"] <= 1)

    return _TEMPLATE.format(
        generated=html.escape(generated),
        total=len(jobs),
        fresh=fresh_24h,
        companies=len(companies),
        data=_safe_json(jobs),
        server_token=json.dumps(server_token),
    )


def build_report(rows: list[dict], out_path: Path) -> Path:
    page = render_report_html(rows, server_token=None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    return out_path


def build_companies_page(token: str) -> str:
    """The watchlist editor. Content is fetched from the API so it is never stale."""
    return _COMPANIES_TEMPLATE.replace("__SHARED_CSS__", _SHARED_CSS).replace(
        "__TOKEN__", token
    )


_SHARED_CSS = """
  :root {
    --ground:#F2F5F7; --surface:#FFFFFF; --ink:#14202B; --soft:#35485A;
    --muted:#5A6B7A; --line:#CBD6DE; --line-soft:#E1E8ED; --accent:#0B6E8C;
    --accent-soft:#E2EFF4; --fresh:#0B6E8C; --bad:#B5502A; --bad-soft:#F7E9E3;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme:dark) {
    :root:not([data-theme="light"]) {
      --ground:#0E1720; --surface:#16222D; --ink:#DCE6EC; --soft:#B4C4CF;
      --muted:#8496A4; --line:#2A3C4C; --line-soft:#1E2E3C; --accent:#4FB3D0;
      --accent-soft:#16303C; --fresh:#4FB3D0; --bad:#E5946B; --bad-soft:#33211A;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
    font-size:15px;line-height:1.5;padding:0 16px 80px;-webkit-font-smoothing:antialiased}
  .wrap{max-width:820px;margin:0 auto}
  h1{font-size:clamp(24px,4vw,32px);letter-spacing:-.02em;margin:0 0 6px;font-weight:640}
  .sub{color:var(--muted);font-size:14px;margin:0}
  a.back{display:inline-block;margin:26px 0 18px;color:var(--accent);
    text-decoration:none;font-size:14px}
  a.back:hover{text-decoration:underline}
"""


_COMPANIES_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Companies watched</title>
<style>
__SHARED_CSS__
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;
    padding:20px;margin:22px 0}
  .panel h2{font-size:17px;margin:0 0 4px;font-weight:640}
  .panel p.hint{color:var(--muted);font-size:13.5px;margin:0 0 16px}
  form{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
  label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.12em;
    text-transform:uppercase;color:var(--muted);margin-bottom:5px}
  input[type=text],select{padding:10px 12px;font-size:16px;font-family:inherit;
    color:var(--ink);background:var(--ground);border:1px solid var(--line);
    border-radius:6px;-webkit-appearance:none}
  input[type=text]{flex:1 1 240px;min-width:0}
  input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
  button{font-family:inherit;font-size:15px;font-weight:600;padding:10px 18px;
    border-radius:6px;border:1px solid var(--accent);background:var(--accent);
    color:#fff;cursor:pointer}
  button:disabled{opacity:.55;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) button{color:#0A121A}
  }
  .msg{margin-top:14px;padding:11px 14px;border-radius:6px;font-size:14px;display:none}
  .msg.ok{display:block;background:var(--accent-soft);border-left:2px solid var(--accent)}
  .msg.err{display:block;background:var(--bad-soft);border-left:2px solid var(--bad)}
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:26px 0 18px}
  .topbar a.back{margin:0}
  .upill{background:var(--accent);color:#fff;border:0;border-radius:6px;
    padding:8px 14px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;
    font-family:inherit}
  .upill:disabled{opacity:.6;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) .upill{color:#0A121A}
  }
  .found{margin-top:14px;display:flex;flex-direction:column;gap:8px}
  .hit{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:11px 14px;border:1px solid var(--accent);border-radius:6px;
    background:var(--accent-soft)}
  .hit.off{border-color:var(--line);background:var(--ground);opacity:.7}
  .hit b{font-size:15px}
  .hit span{display:block;font-size:12.5px;color:var(--muted);margin-top:1px}
  .hit .pick{padding:7px 15px;font-size:14px}
  .group{margin-top:26px}
  .group h3{font-family:var(--mono);font-size:10.5px;letter-spacing:.13em;
    text-transform:uppercase;color:var(--muted);margin:0 0 10px;font-weight:500}
  ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
  li{display:flex;align-items:center;gap:8px;background:var(--surface);
    border:1px solid var(--line);border-radius:20px;padding:5px 6px 5px 13px;font-size:14px}
  li.mine{border-color:var(--accent)}
  li .x{border:0;background:none;color:var(--muted);font-size:17px;line-height:1;
    padding:2px 7px;cursor:pointer;border-radius:50%}
  li .x:hover{color:var(--bad);background:var(--bad-soft)}
  .count{color:var(--muted);font-size:13px;margin:0}
  .empty{color:var(--muted);font-size:14px}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div><a class="back" href="/jobs">&larr; Back to jobs</a>&ensp;&middot;&ensp;<a class="back" href="/profile">Your profile</a></div>
    <button class="upill" id="upill" hidden>Update available &mdash; install</button>
  </div>
  <h1>Companies watched</h1>
  <p class="sub">Their careers pages are checked every hour. <span id="total"></span></p>

  <div class="panel">
    <h2>Add a company</h2>
    <p class="hint">Type a company name &mdash; or paste the link to their jobs page if you
      have it. Their careers page is looked up and checked before anything is saved.</p>
    <form id="add">
      <div style="flex:1 1 260px">
        <label for="q">Company name or link</label>
        <input type="text" id="q" placeholder="Figma &mdash; or jobs.lever.co/brex"
               autocomplete="off" spellcheck="false">
      </div>
      <div>
        <label>&nbsp;</label>
        <button type="submit" id="go">Find</button>
      </div>
    </form>
    <div class="msg" id="msg"></div>
    <div id="results"></div>
  </div>

  <div id="lists"></div>
</div>

<script>
const TOKEN = "__TOKEN__";
const msg = document.getElementById('msg');
const go = document.getElementById('go');

function say(text, ok) {
  msg.textContent = text;
  msg.className = 'msg ' + (ok ? 'ok' : 'err');
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type':'application/json','X-Meester-Token':TOKEN} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('request failed (' + res.status + ')'));
  return data;
}

function draw(snap) {
  document.getElementById('total').textContent =
    snap.total + (snap.total === 1 ? ' company' : ' companies');

  const mine = snap.added || {};
  const mineCount = Object.values(mine).reduce((n, v) => n + v.length, 0);
  let html = '';

  if (mineCount) {
    html += '<div class="group"><h3>Added by you</h3><ul>';
    for (const [ats, list] of Object.entries(mine))
      for (const t of list)
        html += '<li class="mine">' + esc(t)
          + ' <button class="x" data-ats="' + ats + '" data-token="' + esc(t)
          + '" title="Remove">&times;</button></li>';
    html += '</ul></div>';
  }

  for (const [ats, list] of Object.entries(snap.all || {})) {
    const own = new Set(mine[ats] || []);
    const rest = list.filter(t => !own.has(t));
    if (!rest.length) continue;
    html += '<div class="group"><h3>' + ats + ' &middot; ' + rest.length + '</h3><ul>';
    for (const t of rest)
      html += '<li>' + esc(t)
        + ' <button class="x" data-ats="' + ats + '" data-token="' + esc(t)
        + '" title="Stop watching">&times;</button></li>';
    html += '</ul></div>';
  }

  document.getElementById('lists').innerHTML = html || '<p class="empty">Nothing yet.</p>';
  document.querySelectorAll('.x').forEach(b => b.addEventListener('click', async () => {
    b.disabled = true;
    try {
      draw(await api('/api/companies/remove',
        {ats: b.dataset.ats, token: b.dataset.token}));
      say('Stopped watching ' + b.dataset.token + '.', true);
    } catch (e) { say(e.message, false); b.disabled = false; }
  }));
}

const results = document.getElementById('results');

async function confirmAdd(ats, token, btn) {
  btn.disabled = true;
  say('Adding ' + token + '\\u2026', true);
  try {
    const snap = await api('/api/companies/add', {ats, token});
    say(snap.jobs
        ? 'Added ' + token + ' \\u2014 ' + snap.jobs + ' remote '
          + (snap.jobs === 1 ? 'role' : 'roles')
          + ' open there right now. They appear in your list within the hour.'
        : 'Added ' + token + ', but they have no remote roles open at the moment. '
          + 'It will keep checking, and anything new shows up automatically.', true);
    results.innerHTML = '';
    document.getElementById('q').value = '';
    draw(snap);
  } catch (e) {
    say(e.message, false);
    btn.disabled = false;
  }
}

document.getElementById('add').addEventListener('submit', async ev => {
  ev.preventDefault();
  const field = document.getElementById('q');
  const query = field.value.trim();
  if (!query) return;
  go.disabled = true;
  results.innerHTML = '';
  say('Looking for their careers page\\u2026', true);
  try {
    const res = await api('/api/companies/search', {query});
    if (!res.matches.length) {
      say('Couldn\\u2019t find a careers page for that. Try their exact company name, '
          + 'or search the web for "' + query + ' careers" and paste the link here.', false);
    } else if (res.matches.length === 1 && res.matches[0].watched) {
      say('You\\u2019re already watching ' + res.matches[0].token + '.', true);
    } else {
      say('Found ' + (res.matches.length === 1 ? 'their careers page.'
          : res.matches.length + ' possible matches \\u2014 pick the right one.'), true);
      results.innerHTML = '<div class="found">' + res.matches.map(m =>
        m.watched
          ? '<div class="hit off"><b>' + esc(m.token) + '</b><span>on '
            + esc(m.ats) + ' \\u00b7 already watching</span></div>'
          : '<div class="hit"><div><b>' + esc(m.token) + '</b><span>on '
            + esc(m.ats) + '</span></div>'
            + '<button class="pick" data-ats="' + esc(m.ats) + '" data-token="'
            + esc(m.token) + '">Add</button></div>'
      ).join('') + '</div>';
      document.querySelectorAll('.pick').forEach(b => b.addEventListener('click',
        () => confirmAdd(b.dataset.ats, b.dataset.token, b)));
    }
  } catch (e) {
    say(e.message, false);
  }
  go.disabled = false;
});

api('/api/companies').then(draw).catch(e => say(e.message, false));

// Update pill - same behaviour as the jobs page.
const upill = document.getElementById('upill');
fetch('/api/status').then(r => r.json()).then(s => {
  if (s && s.behind) upill.hidden = false;
}).catch(() => {});
upill.addEventListener('click', async () => {
  upill.disabled = true;
  upill.textContent = 'Installing…';
  try {
    const d = await api('/api/update', {});
    if (!d.ok) { say(d.error || 'Update failed', false); upill.textContent = 'Update failed'; return; }
    if (!d.changed) { upill.textContent = 'Already up to date'; return; }
    upill.textContent = 'Restarting…';
    say('Update installed — the app is restarting, this page reloads itself.', true);
    const wait = setInterval(() => {
      fetch('/api/ping').then(r => {
        if (r.ok) { clearInterval(wait); location.reload(); }
      }).catch(() => {});
    }, 1500);
  } catch (e) {
    say(e.message, false);
    upill.disabled = false;
  }
});
</script>
</body>
</html>
"""


def build_resume_page(token: str) -> str:
    """Upload + the facts-ledger editor: the one place her history is recorded."""
    return _RESUME_TEMPLATE.replace("__SHARED_CSS__", _SHARED_CSS).replace(
        "__TOKEN__", token
    )


_RESUME_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your CV</title>
<style>
__SHARED_CSS__
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:26px 0 18px}
  .topbar a.back{margin:0}
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;
    padding:20px;margin:18px 0}
  .panel h2{font-size:16px;margin:0 0 6px;font-weight:640}
  .panel p.hint{color:var(--muted);font-size:13.5px;margin:0 0 14px}
  button{font-family:inherit;font-size:14.5px;font-weight:600;padding:9px 16px;
    border-radius:6px;border:1px solid var(--accent);background:var(--accent);
    color:#fff;cursor:pointer}
  button.ghost{background:none;color:var(--accent)}
  button.tiny{padding:4px 9px;font-size:12.5px;font-weight:550}
  button:disabled{opacity:.55;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) button{color:#0A121A}
    :root:not([data-theme="light"]) button.ghost{color:var(--accent)}
  }
  .filemeta{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:14.5px}
  .filemeta b{font-weight:640}
  .filemeta a{color:var(--accent)}
  label{display:block;font-size:13px;font-weight:600;margin-bottom:4px}
  input[type=text],textarea{width:100%;padding:9px 11px;font-size:14.5px;
    font-family:inherit;color:var(--ink);background:var(--ground);
    border:1px solid var(--line);border-radius:6px;-webkit-appearance:none}
  textarea{resize:vertical;line-height:1.5}
  input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .grid4{display:grid;grid-template-columns:2fr 2fr 1fr 1fr;gap:10px}
  @media (max-width:640px){.grid4{grid-template-columns:1fr 1fr}}
  .field{margin-bottom:14px}
  .card{border:1px solid var(--line);border-radius:8px;padding:14px;margin:12px 0;
    background:var(--ground)}
  .cardbar{display:flex;justify-content:flex-end;gap:6px;margin-bottom:8px}
  .cardbar .spacer{margin-right:auto;font-family:var(--mono);font-size:10.5px;
    letter-spacing:.1em;text-transform:uppercase;color:var(--muted);align-self:center}
  .savebar{position:sticky;bottom:0;background:var(--ground);padding:14px 0 18px;
    border-top:1px solid var(--line);display:flex;gap:14px;align-items:center}
  .msg{padding:10px 14px;border-radius:6px;font-size:14px;display:none;flex:1}
  .msg.ok{display:block;background:var(--accent-soft);border-left:2px solid var(--accent)}
  .msg.err{display:block;background:var(--bad-soft);border-left:2px solid var(--bad)}
  .verified{font-size:12.5px;color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div><a class="back" href="/jobs">&larr; Back to jobs</a>&ensp;&middot;&ensp;<a class="back" href="/profile">Your profile</a>&ensp;&middot;&ensp;<a class="back" href="/letters">Letters</a></div>
  </div>
  <h1>Your CV</h1>
  <p class="sub">The file you send out, and the record of what's actually in it.
    Both stay on this Mac.</p>

  <div class="panel">
    <h2>The file</h2>
    <p class="hint">Upload the CV you actually send out. It's read for facts,
      never rewritten &mdash; tailored versions are built as new documents.</p>
    <div class="filemeta" id="filemeta">Loading&hellip;</div>
    <input type="file" id="file" accept=".pdf,.docx" hidden>
  </div>

  <div class="panel">
    <h2>The record</h2>
    <p class="hint">This is what matching and (later) tailored applications treat
      as the truth about your history &mdash; nothing gets claimed that isn't in
      here. The read-in is rough on purpose: <b>correct it, don't trust it.</b></p>
    <div id="editorwrap"><p class="hint" id="editorempty">Upload the file above,
      then read it in &mdash; or start from scratch.</p>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button id="extract" disabled>Read my CV into the editor</button>
        <button class="ghost" id="scratch">Start from scratch</button>
      </div>
    </div>
    <div id="editor" hidden></div>
  </div>

  <div class="savebar" id="savebar" hidden>
    <button id="save">Save the record</button>
    <div class="msg" id="msg"></div>
    <span class="verified" id="verified"></span>
  </div>
</div>

<script>
const TOKEN = "__TOKEN__";
const msg = document.getElementById('msg');

function say(text, ok) {
  msg.textContent = text;
  msg.className = 'msg ' + (ok ? 'ok' : 'err');
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type':'application/json','X-Meester-Token':TOKEN} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('request failed (' + res.status + ')'));
  return data;
}

// ---- the file -------------------------------------------------------------

const fileInput = document.getElementById('file');
let HAS_RESUME = false;

function drawFile(resume) {
  HAS_RESUME = !!resume;
  document.getElementById('extract').disabled = !HAS_RESUME;
  const el = document.getElementById('filemeta');
  if (!resume) {
    el.innerHTML = '<button id="upl">Upload your CV</button>'
      + '<span class="hint" style="margin:0">PDF or Word, up to 15 MB</span>';
  } else {
    el.innerHTML = '<b>resume.' + esc(resume.kind) + '</b>'
      + '<span>' + Math.round(resume.bytes / 1024) + ' KB</span>'
      + '<a href="/files/resume" target="_blank" rel="noopener">Open</a>'
      + '<button class="ghost" id="upl">Replace</button>';
  }
  document.getElementById('upl').addEventListener('click', () => fileInput.click());
}

fileInput.addEventListener('change', () => {
  const f = fileInput.files[0];
  if (!f) return;
  if (f.size > 15000000) { say('That file is over 15 MB.', false); return; }
  say('Uploading ' + f.name + '\\u2026', true);
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const b64 = String(reader.result).split(',')[1] || '';
      const res = await api('/api/profile/resume', {content_b64: b64});
      if (!res.ok) { say(res.error, false); return; }
      say('Uploaded. Now read it into the editor and correct what it got wrong.', true);
      drawFile({kind: res.kind, bytes: res.bytes});
    } catch (e) { say(e.message, false); }
    fileInput.value = '';
  };
  reader.readAsDataURL(f);
});

// ---- the editor -----------------------------------------------------------

function bulletsText(list) { return (list || []).join('\\n'); }

function jobCard(e, i, n) {
  return '<div class="card" data-kind="job">'
    + '<div class="cardbar"><span class="spacer">Job ' + (i + 1) + '</span>'
    + (i > 0 ? '<button class="tiny ghost" data-act="up">\\u2191</button>' : '')
    + (i < n - 1 ? '<button class="tiny ghost" data-act="down">\\u2193</button>' : '')
    + '<button class="tiny ghost" data-act="del">Remove</button></div>'
    + '<div class="grid4">'
    + '<div><label>Employer</label><input type="text" data-f="employer" value="' + esc(e.employer) + '"></div>'
    + '<div><label>Title</label><input type="text" data-f="title" value="' + esc(e.title) + '"></div>'
    + '<div><label>From</label><input type="text" data-f="start" placeholder="2021" value="' + esc(e.start) + '"></div>'
    + '<div><label>Until</label><input type="text" data-f="end" placeholder="present" value="' + esc(e.end) + '"></div>'
    + '</div>'
    + '<div style="margin-top:10px"><label>What you did there \\u2014 one point per line</label>'
    + '<textarea rows="4" data-f="bullets">' + esc(bulletsText(e.bullets)) + '</textarea></div>'
    + '</div>';
}

function eduCard(e, i, n) {
  return '<div class="card" data-kind="edu">'
    + '<div class="cardbar"><span class="spacer">Education ' + (i + 1) + '</span>'
    + '<button class="tiny ghost" data-act="del">Remove</button></div>'
    + '<div class="grid4">'
    + '<div><label>School</label><input type="text" data-f="school" value="' + esc(e.school) + '"></div>'
    + '<div><label>Degree</label><input type="text" data-f="degree" value="' + esc(e.degree) + '"></div>'
    + '<div><label>From</label><input type="text" data-f="start" value="' + esc(e.start) + '"></div>'
    + '<div><label>Until</label><input type="text" data-f="end" value="' + esc(e.end) + '"></div>'
    + '</div></div>';
}

function render(L) {
  const el = document.getElementById('editor');
  el.innerHTML =
    '<div class="grid2" style="margin-top:6px">'
    + '<div class="field"><label>Name</label><input type="text" id="l_name" value="' + esc(L.name) + '"></div>'
    + '<div class="field"><label>Email on applications</label><input type="text" id="l_email" value="' + esc(L.email) + '"></div>'
    + '<div class="field"><label>Phone</label><input type="text" id="l_phone" value="' + esc(L.phone) + '"></div>'
    + '<div class="field"><label>Location</label><input type="text" id="l_location" placeholder="City, Country" value="' + esc(L.location) + '"></div>'
    + '</div>'
    + '<div class="field"><label>Links \\u2014 one per line</label><textarea rows="2" id="l_links">' + esc((L.links || []).join('\\n')) + '</textarea></div>'
    + '<div class="field"><label>Summary</label><textarea rows="3" id="l_summary">' + esc(L.summary) + '</textarea></div>'
    + '<h2 style="margin-top:22px">Employment</h2>'
    + '<div id="jobs">' + (L.employment || []).map((e, i, a) => jobCard(e, i, a.length)).join('') + '</div>'
    + '<button class="ghost" id="addjob">+ Add a job</button>'
    + '<h2 style="margin-top:22px">Education</h2>'
    + '<div id="edus">' + (L.education || []).map((e, i, a) => eduCard(e, i, a.length)).join('') + '</div>'
    + '<button class="ghost" id="addedu">+ Add education</button>'
    + '<div class="grid2" style="margin-top:22px">'
    + '<div class="field"><label>Skills \\u2014 one per line</label><textarea rows="6" id="l_skills">' + esc((L.skills || []).join('\\n')) + '</textarea></div>'
    + '<div class="field"><label>Certifications \\u2014 one per line</label><textarea rows="6" id="l_certs">' + esc((L.certifications || []).join('\\n')) + '</textarea></div>'
    + '</div>';
  el.hidden = false;
  document.getElementById('editorwrap').hidden = true;
  document.getElementById('savebar').hidden = false;

  document.getElementById('addjob').addEventListener('click', () => {
    const L2 = collect();
    L2.employment.push({employer:'', title:'', start:'', end:'', bullets:[]});
    render(L2);
  });
  document.getElementById('addedu').addEventListener('click', () => {
    const L2 = collect();
    L2.education.push({school:'', degree:'', start:'', end:''});
    render(L2);
  });
  el.querySelectorAll('.card [data-act]').forEach(b => b.addEventListener('click', () => {
    const card = b.closest('.card');
    const kind = card.dataset.kind;
    const list = Array.from(el.querySelectorAll('.card[data-kind="' + kind + '"]'));
    const idx = list.indexOf(card);
    const L2 = collect();
    const arr = kind === 'job' ? L2.employment : L2.education;
    if (b.dataset.act === 'del') arr.splice(idx, 1);
    if (b.dataset.act === 'up' && idx > 0) arr.splice(idx - 1, 0, arr.splice(idx, 1)[0]);
    if (b.dataset.act === 'down' && idx < arr.length - 1) arr.splice(idx + 1, 0, arr.splice(idx, 1)[0]);
    render(L2);
  }));
}

function lines(id) {
  return document.getElementById(id).value.split('\\n').map(s => s.trim()).filter(Boolean);
}

function collect() {
  const el = document.getElementById('editor');
  const grab = (card, f) => card.querySelector('[data-f="' + f + '"]').value.trim();
  return {
    name: document.getElementById('l_name').value.trim(),
    email: document.getElementById('l_email').value.trim(),
    phone: document.getElementById('l_phone').value.trim(),
    location: document.getElementById('l_location').value.trim(),
    links: lines('l_links'),
    summary: document.getElementById('l_summary').value.trim(),
    employment: Array.from(el.querySelectorAll('.card[data-kind="job"]')).map(c => ({
      employer: grab(c, 'employer'), title: grab(c, 'title'),
      start: grab(c, 'start'), end: grab(c, 'end'),
      bullets: c.querySelector('[data-f="bullets"]').value.split('\\n').map(s => s.trim()).filter(Boolean),
    })),
    education: Array.from(el.querySelectorAll('.card[data-kind="edu"]')).map(c => ({
      school: grab(c, 'school'), degree: grab(c, 'degree'),
      start: grab(c, 'start'), end: grab(c, 'end'),
    })),
    skills: lines('l_skills'),
    certifications: lines('l_certs'),
  };
}

document.getElementById('extract').addEventListener('click', async () => {
  const btn = document.getElementById('extract');
  if (!document.getElementById('editor').hidden
      && !confirm('Replace what is in the editor with a fresh read of the file?')) return;
  btn.disabled = true;
  say('Reading the file\\u2026', true);
  try {
    const res = await api('/api/profile/resume/extract', {});
    if (!res.ok) { say(res.error, false); btn.disabled = false; return; }
    render(res.draft);
    say('Read in. Now correct it \\u2014 employer names, dates and bullets \\u2014 then save.', true);
  } catch (e) { say(e.message, false); }
  btn.disabled = false;
});

document.getElementById('scratch').addEventListener('click', () => {
  render({name:'',email:'',phone:'',location:'',links:[],summary:'',
          employment:[{employer:'',title:'',start:'',end:'',bullets:[]}],
          education:[], skills:[], certifications:[]});
});

document.getElementById('save').addEventListener('click', async () => {
  const btn = document.getElementById('save');
  btn.disabled = true;
  try {
    const res = await api('/api/profile/ledger', collect());
    if (res.ok) {
      say('Saved. This is now the record everything else works from.', true);
      drawVerified(res.ledger);
    } else { say(res.error || 'Save failed', false); }
  } catch (e) { say(e.message, false); }
  btn.disabled = false;
});

function drawVerified(L) {
  const el = document.getElementById('verified');
  el.textContent = (L && L.saved_at)
    ? 'Checked by you \\u00b7 ' + L.saved_at.slice(0, 10) : '';
}

api('/api/profile/ledger').then(d => {
  drawFile(d.resume);
  if (d.ledger) { render(d.ledger); drawVerified(d.ledger); }
}).catch(e => say(e.message, false));
</script>
</body>
</html>
"""


def build_letters_page(token: str) -> str:
    """Named cover-letter templates the tailoring stage will fill per job."""
    return _LETTERS_TEMPLATE.replace("__SHARED_CSS__", _SHARED_CSS).replace(
        "__TOKEN__", token
    )


_LETTERS_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cover letters</title>
<style>
__SHARED_CSS__
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:26px 0 18px}
  .topbar a.back{margin:0}
  button{font-family:inherit;font-size:14.5px;font-weight:600;padding:9px 16px;
    border-radius:6px;border:1px solid var(--accent);background:var(--accent);
    color:#fff;cursor:pointer}
  button.ghost{background:none;color:var(--accent)}
  button.tiny{padding:4px 9px;font-size:12.5px;font-weight:550}
  button:disabled{opacity:.55;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) button{color:#0A121A}
    :root:not([data-theme="light"]) button.ghost{color:var(--accent)}
  }
  .legend{background:var(--surface);border:1px solid var(--line);border-radius:8px;
    padding:14px 18px;margin:18px 0;font-size:13.5px;color:var(--soft)}
  .legend code{font-family:var(--mono);font-size:12.5px;background:var(--accent-soft);
    border-radius:4px;padding:1px 6px;color:var(--accent)}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:8px;
    padding:18px;margin:14px 0}
  .cardbar{display:flex;gap:10px;align-items:center;margin-bottom:10px}
  .cardbar input{flex:1;font-weight:600}
  label{display:block;font-size:13px;font-weight:600;margin-bottom:4px}
  input[type=text],textarea{width:100%;padding:9px 11px;font-size:14.5px;
    font-family:inherit;color:var(--ink);background:var(--ground);
    border:1px solid var(--line);border-radius:6px;-webkit-appearance:none}
  textarea{resize:vertical;line-height:1.55;min-height:130px}
  input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
  .meta{display:flex;gap:14px;margin-top:6px;font-size:12.5px;color:var(--muted);
    flex-wrap:wrap}
  .meta .warn{color:var(--bad)}
  .meta .long{color:var(--bad)}
  .preview{margin-top:12px;border-left:2px solid var(--line);padding:2px 0 2px 14px;
    font-size:14px;color:var(--soft);white-space:pre-wrap}
  .preview .fill{color:var(--accent);font-weight:600}
  .preview .todo{background:var(--accent-soft);color:var(--accent);border-radius:4px;
    padding:0 5px;font-size:12.5px}
  .savebar{position:sticky;bottom:0;background:var(--ground);padding:14px 0 18px;
    border-top:1px solid var(--line);display:flex;gap:14px;align-items:center}
  .msg{padding:10px 14px;border-radius:6px;font-size:14px;display:none;flex:1}
  .msg.ok{display:block;background:var(--accent-soft);border-left:2px solid var(--accent)}
  .msg.err{display:block;background:var(--bad-soft);border-left:2px solid var(--bad)}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div><a class="back" href="/jobs">&larr; Back to jobs</a>&ensp;&middot;&ensp;<a class="back" href="/profile">Your profile</a>&ensp;&middot;&ensp;<a class="back" href="/resume">Your CV</a></div>
  </div>
  <h1>Cover letters</h1>
  <p class="sub">A few variations in your own voice &mdash; formal, warmer, role-specific.
    When an application needs a letter, one of these gets picked and filled for
    that exact job. Under 150 words reads best; a letter is a knock on the door,
    not the interview.</p>

  <div class="legend">These fill themselves in per job:
    <code>{company}</code> the company's name &middot;
    <code>{role}</code> the job title &middot;
    <code>{their_product}</code> what they make &middot;
    <code>{why_them}</code> a specific, true reason &mdash; written fresh for each
    application, never boilerplate.</div>

  <div id="cards"></div>
  <button class="ghost" id="add">+ Add a variation</button>

  <div class="savebar">
    <button id="save">Save letters</button>
    <div class="msg" id="msg"></div>
  </div>
</div>

<script>
const TOKEN = "__TOKEN__";
const KNOWN = ['company', 'role', 'their_product', 'why_them'];
let SAMPLE = {company: 'Figma', role: 'Product Designer'};
const msg = document.getElementById('msg');

function say(text, ok) {
  msg.textContent = text;
  msg.className = 'msg ' + (ok ? 'ok' : 'err');
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type':'application/json','X-Meester-Token':TOKEN} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('request failed (' + res.status + ')'));
  return data;
}

function words(text) { return (text.trim().match(/\\S+/g) || []).length; }

function unknownPlaceholders(text) {
  const seen = new Set();
  (text.match(/\\{([a-zA-Z_][a-zA-Z0-9_]*)\\}/g) || []).forEach(m => {
    const name = m.slice(1, -1);
    if (!KNOWN.includes(name)) seen.add(m);
  });
  return Array.from(seen);
}

function previewHtml(text) {
  // Fill company/role from a real posting in her list; mark the per-job parts.
  return esc(text)
    .replace(/\\{company\\}/g, '<span class="fill">' + esc(SAMPLE.company) + '</span>')
    .replace(/\\{role\\}/g, '<span class="fill">' + esc(SAMPLE.role) + '</span>')
    .replace(/\\{their_product\\}/g, '<span class="todo">what they make - written per job</span>')
    .replace(/\\{why_them\\}/g, '<span class="todo">a specific true reason - written per job</span>');
}

function refreshMeta(card) {
  const body = card.querySelector('textarea').value;
  const n = words(body);
  const wEl = card.querySelector('[data-m="words"]');
  wEl.textContent = n + ' words';
  wEl.className = n > 180 ? 'long' : '';
  if (n > 180) wEl.textContent += ' - long for a letter nobody asked for';
  const unknown = unknownPlaceholders(body);
  card.querySelector('[data-m="lint"]').textContent =
    unknown.length ? 'Unknown placeholder ' + unknown.join(', ') + ' - it would appear literally' : '';
  card.querySelector('.preview').innerHTML =
    previewHtml(body) || '<span class="todo">empty</span>';
}

function card(letter) {
  const el = document.createElement('div');
  el.className = 'card';
  el.innerHTML =
    '<div class="cardbar">'
    + '<input type="text" data-f="name" placeholder="Name this variation" value="' + esc(letter.name) + '">'
    + '<button class="tiny ghost" data-act="del">Remove</button></div>'
    + '<textarea data-f="body">' + esc(letter.body) + '</textarea>'
    + '<div class="meta"><span data-m="words"></span><span class="warn" data-m="lint"></span></div>'
    + '<label style="margin-top:12px">How it reads for <b>' + esc(SAMPLE.role) + '</b> at <b>'
    + esc(SAMPLE.company) + '</b> \\u2014 a real posting from your list</label>'
    + '<div class="preview"></div>';
  el.querySelector('textarea').addEventListener('input', () => refreshMeta(el));
  el.querySelector('[data-act="del"]').addEventListener('click', () => {
    if (el.querySelector('textarea').value.trim()
        && !confirm('Remove this letter? Its text is gone once you save.')) return;
    el.remove();
  });
  refreshMeta(el);
  return el;
}

function render(letters) {
  const wrap = document.getElementById('cards');
  wrap.innerHTML = '';
  letters.forEach(l => wrap.appendChild(card(l)));
}

function collect() {
  return {letters: Array.from(document.querySelectorAll('.card')).map(c => ({
    name: c.querySelector('[data-f="name"]').value.trim(),
    body: c.querySelector('[data-f="body"]').value,
  }))};
}

document.getElementById('add').addEventListener('click', () => {
  document.getElementById('cards').appendChild(card({name: '', body: ''}));
});

document.getElementById('save').addEventListener('click', async () => {
  const btn = document.getElementById('save');
  btn.disabled = true;
  try {
    const res = await api('/api/profile/letters', collect());
    if (res.ok) {
      render(res.letters);
      say('Saved \\u2014 ' + res.letters.length + ' letter'
          + (res.letters.length === 1 ? '' : 's') + ' ready to be used.', true);
    } else {
      say(Object.values(res.errors).join(' '), false);
    }
  } catch (e) { say(e.message, false); }
  btn.disabled = false;
});

api('/api/profile/letters').then(d => {
  SAMPLE = d.sample || SAMPLE;
  render(d.letters);
}).catch(e => say(e.message, false));
</script>
</body>
</html>
"""


def build_profile_page(token: str) -> str:
    """The preferences form. Rendered entirely from the schema the server
    sends, so a new preference field needs zero template changes."""
    return _PROFILE_TEMPLATE.replace("__SHARED_CSS__", _SHARED_CSS).replace(
        "__TOKEN__", token
    )


_PROFILE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your profile</title>
<style>
__SHARED_CSS__
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:26px 0 18px}
  .topbar a.back{margin:0}
  .upill{background:var(--accent);color:#fff;border:0;border-radius:6px;
    padding:8px 14px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;
    font-family:inherit}
  .upill:disabled{opacity:.6;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) .upill{color:#0A121A}
  }
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;
    padding:20px;margin:18px 0}
  .panel h2{font-size:16px;margin:0 0 14px;font-weight:640}
  .field{margin-bottom:18px}
  .field:last-child{margin-bottom:4px}
  label{display:block;font-size:14px;font-weight:600;margin-bottom:5px}
  .help{font-size:12.5px;color:var(--muted);margin:4px 0 0}
  .ferr{font-size:12.5px;color:var(--bad);margin:4px 0 0}
  input[type=text],textarea,select{width:100%;padding:10px 12px;font-size:15px;
    font-family:inherit;color:var(--ink);background:var(--ground);
    border:1px solid var(--line);border-radius:6px;-webkit-appearance:none}
  textarea{resize:vertical;min-height:74px;line-height:1.5}
  input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
  .check{display:flex;align-items:center;gap:10px}
  .check input{width:18px;height:18px;accent-color:var(--accent)}
  .check label{margin:0;font-weight:550}
  .savebar{position:sticky;bottom:0;background:var(--ground);padding:14px 0 18px;
    border-top:1px solid var(--line);display:flex;gap:14px;align-items:center}
  .savebar button{font-family:inherit;font-size:15px;font-weight:600;padding:11px 22px;
    border-radius:6px;border:1px solid var(--accent);background:var(--accent);
    color:#fff;cursor:pointer}
  .savebar button:disabled{opacity:.55;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) .savebar button{color:#0A121A}
  }
  .msg{padding:10px 14px;border-radius:6px;font-size:14px;display:none;flex:1}
  .msg.ok{display:block;background:var(--accent-soft);border-left:2px solid var(--accent)}
  .msg.err{display:block;background:var(--bad-soft);border-left:2px solid var(--bad)}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div><a class="back" href="/jobs">&larr; Back to jobs</a>&ensp;&middot;&ensp;<a class="back" href="/resume">Your CV</a>&ensp;&middot;&ensp;<a class="back" href="/letters">Letters</a>&ensp;&middot;&ensp;<a class="back" href="/companies">Companies</a></div>
    <button class="upill" id="upill" hidden>Update available &mdash; install</button>
  </div>
  <h1>Your profile</h1>
  <p class="sub">What the matching uses to rank jobs for you. Everything here stays
    on this Mac. Answer honestly rather than aspirationally &mdash; an inflated
    salary floor produces an empty list.</p>

  <div id="form"><p class="sub" style="margin-top:24px">Loading&hellip;</p></div>

  <div class="savebar" id="savebar" hidden>
    <button id="save">Save</button>
    <div class="msg" id="msg"></div>
  </div>
</div>

<script>
const TOKEN = "__TOKEN__";
const msg = document.getElementById('msg');

function say(text, ok) {
  msg.textContent = text;
  msg.className = 'msg ' + (ok ? 'ok' : 'err');
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: body ? {'Content-Type':'application/json','X-Meester-Token':TOKEN} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ('request failed (' + res.status + ')'));
  return data;
}

let FIELDS = [];

function control(f, value) {
  const id = 'f_' + f.key;
  if (f.type === 'bool')
    return '<div class="check"><input type="checkbox" id="' + id + '"'
      + (value ? ' checked' : '') + '><label for="' + id + '">' + esc(f.label) + '</label></div>';

  let inner = '<label for="' + id + '">' + esc(f.label) + '</label>';
  const ph = f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : '';
  if (f.type === 'list' || f.type === 'longtext') {
    const text = Array.isArray(value) ? value.join('\\n') : (value || '');
    inner += '<textarea id="' + id + '"' + ph
      + (f.type === 'list' ? ' rows="4"' : ' rows="3"') + '>' + esc(text) + '</textarea>';
  } else if (f.type === 'select') {
    inner += '<select id="' + id + '">' + f.options.map(o =>
      '<option value="' + esc(o) + '"' + (o === (value || '') ? ' selected' : '') + '>'
      + (o ? esc(o) : 'No preference') + '</option>').join('') + '</select>';
  } else {
    const mode = f.type === 'number' ? ' inputmode="numeric"' : '';
    inner += '<input type="text" id="' + id + '"' + ph + mode
      + ' value="' + esc(value == null ? '' : value) + '">';
  }
  if (f.help) inner += '<p class="help">' + esc(f.help) + '</p>';
  inner += '<p class="ferr" id="err_' + f.key + '"></p>';
  return inner;
}

function render(fields, values) {
  FIELDS = fields;
  const sections = [];
  const by = {};
  fields.forEach(f => {
    if (!by[f.section]) { by[f.section] = []; sections.push(f.section); }
    by[f.section].push(f);
  });
  document.getElementById('form').innerHTML = sections.map(s =>
    '<div class="panel"><h2>' + esc(s) + '</h2>'
    + by[s].map(f => '<div class="field">' + control(f, values[f.key]) + '</div>').join('')
    + '</div>').join('');
  document.getElementById('savebar').hidden = false;
}

function collect() {
  const out = {};
  FIELDS.forEach(f => {
    const el = document.getElementById('f_' + f.key);
    if (!el) return;
    out[f.key] = f.type === 'bool' ? el.checked : el.value;
  });
  return out;
}

document.getElementById('save').addEventListener('click', async () => {
  const btn = document.getElementById('save');
  btn.disabled = true;
  document.querySelectorAll('.ferr').forEach(e => e.textContent = '');
  try {
    const res = await api('/api/profile/preferences', collect());
    if (res.ok) {
      say('Saved. Takes effect on the next harvest \\u2014 within the hour.', true);
    } else {
      Object.entries(res.errors || {}).forEach(([k, v]) => {
        const el = document.getElementById('err_' + k);
        if (el) el.textContent = v;
      });
      say('A couple of answers need fixing \\u2014 see the notes in red.', false);
    }
  } catch (e) { say(e.message, false); }
  btn.disabled = false;
});

api('/api/profile/preferences')
  .then(d => render(d.fields, d.values))
  .catch(e => { document.getElementById('form').innerHTML = ''; say(e.message, false); });

// Update pill - same behaviour as the other pages.
const upill = document.getElementById('upill');
fetch('/api/status').then(r => r.json()).then(s => {
  if (s && s.behind) upill.hidden = false;
}).catch(() => {});
upill.addEventListener('click', async () => {
  upill.disabled = true;
  upill.textContent = 'Installing\\u2026';
  try {
    const d = await api('/api/update', {});
    if (!d.ok) { say(d.error || 'Update failed', false); upill.textContent = 'Update failed'; return; }
    if (!d.changed) { upill.textContent = 'Already up to date'; return; }
    upill.textContent = 'Restarting\\u2026';
    const wait = setInterval(() => {
      fetch('/api/ping').then(r => {
        if (r.ok) { clearInterval(wait); location.reload(); }
      }).catch(() => {});
    }, 1500);
  } catch (e) { say(e.message, false); upill.disabled = false; }
});
</script>
</body>
</html>
"""


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Remote jobs</title>
<style>
  :root {{
    --ground:#F2F5F7; --surface:#FFFFFF; --ink:#14202B; --soft:#35485A;
    --muted:#5A6B7A; --line:#CBD6DE; --line-soft:#E1E8ED; --accent:#0B6E8C;
    --accent-soft:#E2EFF4; --fresh:#0B6E8C;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }}
  @media (prefers-color-scheme:dark) {{
    :root:not([data-theme="light"]) {{
      --ground:#0E1720; --surface:#16222D; --ink:#DCE6EC; --soft:#B4C4CF;
      --muted:#8496A4; --line:#2A3C4C; --line-soft:#1E2E3C; --accent:#4FB3D0;
      --accent-soft:#16303C; --fresh:#4FB3D0;
    }}
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
    font-size:15px;line-height:1.5;padding:0 16px 80px;-webkit-font-smoothing:antialiased}}
  .wrap{{max-width:940px;margin:0 auto}}
  header{{padding:36px 0 18px}}
  h1{{font-size:clamp(24px,4vw,32px);letter-spacing:-.02em;margin:0 0 6px;font-weight:640}}
  .sub{{color:var(--muted);font-size:14px;margin:0}}
  .stats{{display:flex;gap:22px;flex-wrap:wrap;margin:18px 0 0;padding:14px 0;
    border-top:1px solid var(--line);border-bottom:1px solid var(--line)}}
  .stat b{{display:block;font-size:22px;font-variant-numeric:tabular-nums;font-weight:640}}
  .stat span{{font-family:var(--mono);font-size:10px;letter-spacing:.12em;
    text-transform:uppercase;color:var(--muted)}}
  .controls{{position:sticky;top:0;background:var(--ground);padding:16px 0 12px;z-index:5;
    border-bottom:1px solid var(--line-soft)}}
  input[type=search]{{width:100%;padding:12px 14px;font-size:16px;font-family:inherit;
    color:var(--ink);background:var(--surface);border:1px solid var(--line);
    border-radius:6px;-webkit-appearance:none}}
  input[type=search]:focus{{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent}}
  .chips{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
  .chip{{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
    padding:6px 11px;border-radius:20px;border:1px solid var(--line);background:var(--surface);
    color:var(--muted);cursor:pointer}}
  .chip[aria-pressed="true"]{{background:var(--accent);border-color:var(--accent);color:#fff}}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]) .chip[aria-pressed="true"]{{color:#0A121A}}
  }}
  .count{{font-size:13px;color:var(--muted);margin:14px 0 6px;font-variant-numeric:tabular-nums}}
  ul{{list-style:none;margin:0;padding:0}}
  li{{border-bottom:1px solid var(--line-soft);padding:14px 0;display:flex;gap:14px;
    align-items:baseline;flex-wrap:wrap}}
  li a{{color:var(--ink);text-decoration:none;font-weight:600;font-size:15.5px}}
  li a:hover{{color:var(--accent);text-decoration:underline}}
  .main{{flex:1 1 340px;min-width:0}}
  .meta{{color:var(--muted);font-size:13px;margin-top:3px;display:flex;gap:10px;flex-wrap:wrap}}
  .co{{color:var(--soft);font-weight:550}}
  .age{{font-family:var(--mono);font-size:11.5px;color:var(--muted);
    font-variant-numeric:tabular-nums;white-space:nowrap}}
  .new{{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--fresh);border:1px solid var(--fresh);border-radius:3px;padding:1px 5px;
    white-space:nowrap}}
  .pay{{color:var(--soft)}}
  .upill{{align-self:center;background:var(--accent);color:#fff;border:0;border-radius:6px;
    padding:8px 14px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;
    font-family:inherit}}
  .upill:disabled{{opacity:.6;cursor:default}}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]) .upill{{color:#0A121A}}
  }}
  .navlinks{{margin-left:auto;display:flex;gap:12px;align-items:center}}
  .manage{{align-self:center;color:var(--accent);text-decoration:none;
    font-size:14px;font-weight:600;border:1px solid var(--accent);border-radius:6px;
    padding:8px 14px;white-space:nowrap}}
  .manage:hover{{background:var(--accent-soft)}}
  .empty{{padding:50px 0;text-align:center;color:var(--muted)}}
  footer{{margin-top:32px;padding-top:18px;border-top:1px solid var(--line);
    color:var(--muted);font-size:13px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Remote jobs</h1>
    <p class="sub">Updated {generated} &middot; refreshes on its own, just reopen this file</p>
    <div class="stats">
      <div class="stat"><b>{total}</b><span>Open roles</span></div>
      <div class="stat"><b>{fresh}</b><span>New today</span></div>
      <div class="stat"><b>{companies}</b><span>Companies</span></div>
      <div class="navlinks" id="navlinks" hidden>
        <a class="manage" href="http://127.0.0.1:8765/profile">Your profile</a>
        <a class="manage" href="http://127.0.0.1:8765/resume">Your CV</a>
        <a class="manage" href="http://127.0.0.1:8765/letters">Letters</a>
        <a class="manage" href="http://127.0.0.1:8765/companies">Add companies &rarr;</a>
        <button class="upill" id="upill" hidden>Update available</button>
      </div>
    </div>
  </header>

  <div class="controls">
    <input type="search" id="q" placeholder="Search title, company or location&hellip;" autocomplete="off">
    <div class="chips">
      <button class="chip" id="f-all"   aria-pressed="true">Everything</button>
      <button class="chip" id="f-today" aria-pressed="false">New today</button>
      <button class="chip" id="f-week"  aria-pressed="false">This week</button>
      <button class="chip" id="f-pay"   aria-pressed="false">Salary shown</button>
    </div>
  </div>

  <p class="count" id="count"></p>
  <ul id="list"></ul>
  <div class="empty" id="empty" hidden>Nothing matches that. Try a shorter word.</div>

  <footer>
    Collected automatically from company job boards. Nothing has been applied to &mdash;
    these are just the openings found.
  </footer>
</div>

<script>
const JOBS = {data};
// null in the offline Desktop file; the write token when served from localhost.
// The Desktop file must never carry the token - it lives where Finder can reach.
const SERVED_TOKEN = {server_token};
const list = document.getElementById('list');
const countEl = document.getElementById('count');
const emptyEl = document.getElementById('empty');
const q = document.getElementById('q');
let filter = 'all';

const chips = {{ all:'f-all', today:'f-today', week:'f-week', pay:'f-pay' }};
Object.entries(chips).forEach(([key, id]) => {{
  document.getElementById(id).addEventListener('click', () => {{
    filter = key;
    Object.values(chips).forEach(i =>
      document.getElementById(i).setAttribute('aria-pressed', String(i === id)));
    render();
  }});
}});
q.addEventListener('input', render);

function esc(s) {{
  return String(s).replace(/[&<>"']/g, c =>
    ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
}}

function age(a) {{
  if (a === null) return '';
  if (a < 1) return 'today';
  if (a < 2) return 'yesterday';
  return Math.round(a) + 'd ago';
}}

function render() {{
  const term = q.value.trim().toLowerCase();
  const rows = JOBS.filter(j => {{
    if (filter === 'today' && !(j.a !== null && j.a <= 1)) return false;
    if (filter === 'week'  && !(j.a !== null && j.a <= 7)) return false;
    if (filter === 'pay'   && !j.s) return false;
    if (!term) return true;
    return (j.t + ' ' + j.c + ' ' + j.l + ' ' + j.d).toLowerCase().includes(term);
  }});

  countEl.textContent = rows.length + (rows.length === 1 ? ' role' : ' roles');
  emptyEl.hidden = rows.length > 0;

  list.innerHTML = rows.map(j => {{
    const isNew = j.a !== null && j.a <= 1;
    const bits = [j.l, j.d, j.s].filter(Boolean).map(esc);
    return '<li><div class="main">'
      + '<a href="' + esc(j.u) + '" target="_blank" rel="noopener">' + esc(j.t) + '</a>'
      + '<div class="meta"><span class="co">' + esc(j.c) + '</span>'
      + bits.map(b => '<span>' + b + '</span>').join('')
      + '</div></div>'
      + (isNew ? '<span class="new">New</span>' : '')
      + '<span class="age">' + age(j.a) + '</span></li>';
  }}).join('');
}}

render();

// Only offer the Companies screen if the local helper is actually running.
// A dead link is worse than no link for someone who won't debug it.
fetch('http://127.0.0.1:8765/api/ping', {{mode: 'cors'}})
  .then(r => r.ok && (document.getElementById('navlinks').hidden = false))
  .catch(() => {{}});

// Update pill. From the Desktop file it can only point at the app (no token
// here by design); on the served page it actually installs.
const upill = document.getElementById('upill');
fetch('http://127.0.0.1:8765/api/status', {{mode: 'cors'}})
  .then(r => r.json())
  .then(s => {{
    if (!s || !s.behind) return;
    upill.hidden = false;
    if (!SERVED_TOKEN) {{
      upill.textContent = 'Update available \\u2192';
      upill.addEventListener('click', () => location.href = 'http://127.0.0.1:8765/');
      return;
    }}
    upill.textContent = 'Update available \\u2014 install';
    upill.addEventListener('click', async () => {{
      upill.disabled = true;
      upill.textContent = 'Installing\\u2026';
      try {{
        const res = await fetch('/api/update',
          {{method: 'POST', headers: {{'X-Meester-Token': SERVED_TOKEN}}}});
        const d = await res.json();
        if (!d.ok) {{ upill.textContent = d.error || 'Update failed'; return; }}
        if (!d.changed) {{ upill.textContent = 'Already up to date'; return; }}
        upill.textContent = 'Restarting\\u2026';
        const wait = setInterval(() => {{
          fetch('/api/ping').then(r => {{
            if (r.ok) {{ clearInterval(wait); location.reload(); }}
          }}).catch(() => {{}});
        }}, 1500);
      }} catch (e) {{
        upill.textContent = 'Update failed \\u2014 tell William';
        upill.disabled = false;
      }}
    }});
  }})
  .catch(() => {{}});
</script>
</body>
</html>
"""
