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


def build_report(rows: list[dict], out_path: Path) -> Path:
    jobs = _prepare(rows)
    companies = sorted({j["c"] for j in jobs})
    generated = datetime.now().strftime("%A %d %B, %H:%M")
    fresh_24h = sum(1 for j in jobs if j["a"] is not None and j["a"] <= 1)

    page = _TEMPLATE.format(
        generated=html.escape(generated),
        total=len(jobs),
        fresh=fresh_24h,
        companies=len(companies),
        data=_safe_json(jobs),
    )
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
  <a class="back" href="/jobs">&larr; Back to jobs</a>
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
  .manage{{margin-left:auto;align-self:center;color:var(--accent);text-decoration:none;
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
      <a class="manage" id="manage" href="http://127.0.0.1:8765/companies" hidden>Add companies &rarr;</a>
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
  .then(r => r.ok && (document.getElementById('manage').hidden = false))
  .catch(() => {{}});
</script>
</body>
</html>
"""
