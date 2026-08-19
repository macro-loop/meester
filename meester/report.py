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


def _prepare(
    rows: list[dict],
    prefs: dict | None = None,
    ledger: dict | None = None,
    statuses: dict[str, dict] | None = None,
    judge: dict[str, dict] | None = None,
) -> list[dict]:
    scoring = False
    if prefs:
        from .score.gates import has_usable_preferences, score_job

        scoring = has_usable_preferences(prefs)
    statuses = statuses or {}

    out = []
    for r in rows:
        age = _age_days(r)
        fp = r.get("fingerprint") or ""
        job = {
            "id": fp,
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
        if fp in statuses:
            job["st"] = statuses[fp]["state"]
        if judge and fp in judge:
            job["fit"] = judge[fp]["fit"]
            if judge[fp].get("evidence"):
                job["ev"] = judge[fp]["evidence"][0]
        if scoring:
            verdict = score_job(r, prefs, ledger)
            # Hard-excluded rows (her own never-show list) drop out entirely.
            if verdict["score"] <= -900:
                continue
            job["m"] = 1 if verdict["match"] else 0
            job["sc"] = verdict["score"]
            job["dr"] = 1 if verdict["dream"] else 0
            if verdict["reasons"]:
                job["r"] = verdict["reasons"]
        out.append(job)
    # Newest first; unknown ages last rather than pretending they are fresh.
    out.sort(key=lambda x: (x["a"] is None, x["a"] if x["a"] is not None else 0))
    return out


def render_report_html(
    rows: list[dict],
    server_token: str | None = None,
    prefs: dict | None = None,
    ledger: dict | None = None,
    statuses: dict[str, dict] | None = None,
    judge: dict[str, dict] | None = None,
    has_key: bool = False,
) -> str:
    """The jobs page. Two variants of one template:

    server_token=None  -> the offline Desktop file. No secret in it, ever - it
                          lives in a folder Finder can reach and gets no writes.
    server_token=str   -> the same page served from localhost, where the token
                          lets the update button actually install.

    With usable preferences, every job carries a score and the page opens on
    the For-you view. Scoring happens here, at render time, so a preference
    edit re-ranks on the next page load instead of the next harvest.
    """
    jobs = _prepare(rows, prefs, ledger, statuses, judge)
    companies = sorted({j["c"] for j in jobs})
    generated = datetime.now().strftime("%A %d %B, %H:%M")
    fresh_24h = sum(1 for j in jobs if j["a"] is not None and j["a"] <= 1)
    matches = sum(1 for j in jobs if j.get("m"))

    foryou_stat = (
        f'<div class="stat"><b>{matches}</b><span>For you</span></div>' if matches else ""
    )

    # The judge note tells the truth about WHY there are no fit percentages,
    # instead of always blaming a missing key. Empty means "say nothing".
    if judge:
        judge_hint = ""  # fits exist; note stays hidden
    elif not has_key:
        judge_hint = ("AI judge is off — add an Anthropic key under Your "
                      "profile for fit percentages and evidence.")
    elif ledger is None or not ledger.get("verified"):
        judge_hint = ("AI judge needs your CV — upload and save it under Your "
                      "CV, then it runs on the next harvest.")
    else:
        judge_hint = ("AI judge is on — fit percentages appear after the next "
                      "harvest (usually within the hour).")

    return _TEMPLATE.format(
        generated=html.escape(generated),
        total=len(jobs),
        fresh=fresh_24h,
        companies=len(companies),
        foryou_stat=foryou_stat,
        data=_safe_json(jobs),
        server_token=json.dumps(server_token),
        judge_hint=json.dumps(judge_hint),
    )


def build_report(
    rows: list[dict],
    out_path: Path,
    prefs: dict | None = None,
    ledger: dict | None = None,
    statuses: dict[str, dict] | None = None,
    judge: dict[str, dict] | None = None,
    has_key: bool = False,
) -> Path:
    page = render_report_html(
        rows, server_token=None, prefs=prefs, ledger=ledger, statuses=statuses,
        has_key=has_key,
        judge=judge,
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


def build_queue_page(token: str) -> str:
    """The approve queue: nothing acts in her name except through here."""
    return _QUEUE_TEMPLATE.replace("__SHARED_CSS__", _SHARED_CSS).replace(
        "__TOKEN__", token
    )


_QUEUE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approve queue</title>
<style>
__SHARED_CSS__
  .topbar{display:flex;justify-content:space-between;align-items:center;margin:26px 0 18px;
    gap:10px;flex-wrap:wrap}
  .topbar a.back{margin:0}
  button{font-family:inherit;font-size:14.5px;font-weight:600;padding:10px 18px;
    border-radius:6px;border:1px solid var(--accent);background:var(--accent);
    color:#fff;cursor:pointer;min-height:42px}
  button.ghost{background:none;color:var(--accent)}
  button.warn{border-color:var(--bad);background:none;color:var(--bad)}
  button:disabled{opacity:.5;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) button{color:#0A121A}
    :root:not([data-theme="light"]) button.ghost{color:var(--accent)}
    :root:not([data-theme="light"]) button.warn{color:var(--bad)}
  }
  h2{font-size:15px;font-weight:640;margin:26px 0 8px;color:var(--soft)}
  .count{font-family:var(--mono);font-size:11px;color:var(--muted)}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:10px;
    padding:16px;margin:10px 0}
  .card h3{font-size:16px;margin:0}
  .card h3 a{color:var(--ink);text-decoration:none}
  .card h3 a:hover{color:var(--accent)}
  .co{color:var(--muted);font-size:13.5px;margin:2px 0 0}
  .chipline{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
  .state{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
    text-transform:uppercase;border-radius:3px;padding:2px 7px}
  .state.proposed{background:var(--accent-soft);color:var(--accent)}
  .state.needs_human{background:var(--bad-soft);color:var(--bad)}
  .state.approved{background:var(--accent);color:#fff}
  .state.submitted{background:var(--line-soft);color:var(--soft)}
  .state.failed,.state.expired,.state.skipped{background:var(--line-soft);color:var(--muted)}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) .state.approved{color:#0A121A}
  }
  .why{font-size:12.5px;color:var(--accent)}
  .needs{font-size:13.5px;color:var(--bad);margin:8px 0;padding:9px 12px;
    background:var(--bad-soft);border-radius:6px}
  details{margin:10px 0}
  summary{font-size:13px;color:var(--accent);cursor:pointer}
  textarea{width:100%;padding:9px 11px;font-size:14px;font-family:inherit;
    color:var(--ink);background:var(--ground);border:1px solid var(--line);
    border-radius:6px;line-height:1.5;resize:vertical;margin-top:8px}
  label{display:block;font-size:12.5px;font-weight:600;margin-top:8px}
  .buttons{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
  .blank-warn{font-size:12.5px;color:var(--bad)}
  .msg{padding:10px 14px;border-radius:6px;font-size:14px;display:none;margin:12px 0}
  .msg.ok{display:block;background:var(--accent-soft);border-left:2px solid var(--accent)}
  .msg.err{display:block;background:var(--bad-soft);border-left:2px solid var(--bad)}
  .empty{color:var(--muted);font-size:14px;padding:8px 0}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div><a class="back" href="/jobs">&larr; Jobs</a>&ensp;&middot;&ensp;<a class="back" href="/profile">Profile</a></div>
    <button class="ghost" id="run">Submit approved now</button>
  </div>
  <h1>Approve queue</h1>
  <p class="sub">Nothing is sent anywhere without your tap. Approving an
    application means it submits on the next run &mdash; exactly what the card
    shows, no more.</p>
  <div class="msg" id="msg"></div>
  <div id="lists"><p class="empty">Loading&hellip;</p></div>
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

function finalLetter(item) {
  return (item.letter_body || '')
    .replace(/\\{company\\}/g, (item.job || {}).company || '')
    .replace(/\\{role\\}/g, (item.job || {}).title || '')
    .replace(/\\{why_them\\}/g, item.why_them || '{why_them}');
}

function hasBlanks(item) {
  return /\\{[a-zA-Z_]+\\}/.test(finalLetter(item));
}

function outreachBody(item) {
  if (item.note_body != null) return item.note_body;
  try { return (JSON.parse(item.note || '{}').body) || ''; } catch (e) { return ''; }
}

function outreachCard(item) {
  const job = item.job || {};
  const contact = item.contact || {};
  const editable = ['proposed', 'needs_human'].includes(item.state);
  const body = outreachBody(item);
  const hasBlank = /\\[[^\\]]+\\]/.test(body);
  let buttons = '';
  if (item.state === 'proposed')
    buttons = '<button data-act="approve"' + (hasBlank ? ' disabled' : '')
      + '>Send this note</button>'
      + '<button class="ghost" data-act="skip">Skip</button>'
      + (hasBlank ? '<span class="blank-warn">Fill the [bracketed] part first</span>' : '');
  return '<div class="card" data-id="' + esc(item.id) + '" data-kind="outreach">'
    + '<h3>' + esc(contact.name || 'Hiring contact') + '</h3>'
    + '<p class="co">' + esc(contact.title || '') + (contact.title ? ' at ' : '')
    + esc(job.company || '') + ' &middot; ' + esc(contact.email || '') + '</p>'
    + '<div class="chipline"><span class="state ' + esc(item.state) + '">'
    + esc(item.state.replace('_', ' ')) + '</span>'
    + '<span class="why">outreach after applying to ' + esc(job.title || '') + '</span></div>'
    + '<label>The note that will be sent from your email</label>'
    + '<textarea data-f="note_body" rows="8" ' + (editable ? '' : 'readonly') + '>'
    + esc(body) + '</textarea>'
    + (editable ? '<div class="buttons"><button class="ghost" data-act="update">Save note</button></div>' : '')
    + (buttons ? '<div class="buttons">' + buttons + '</div>' : '')
    + '</div>';
}

function card(item) {
  if (item.kind === 'outreach') return outreachCard(item);
  const job = item.job || {};
  const editable = ['proposed', 'approved', 'needs_human'].includes(item.state);
  const blanks = item.letter_body && hasBlanks(item);
  let buttons = '';
  if (item.state === 'proposed')
    buttons = '<button data-act="approve"' + (blanks ? ' disabled' : '') + '>Approve</button>'
      + '<button class="ghost" data-act="skip">Skip</button>'
      + (blanks ? '<span class="blank-warn">Fill the letter blank below first</span>' : '');
  else if (item.state === 'needs_human')
    buttons = '<a href="' + esc(job.apply_url || job.url) + '" target="_blank" rel="noopener">'
      + '<button class="ghost" type="button">Open the application</button></a>'
      + '<button data-act="did-it-myself">I applied by hand</button>'
      + '<button class="ghost" data-act="retry">Try again</button>'
      + '<button class="warn" data-act="skip">Skip</button>';
  else if (item.state === 'approved')
    buttons = '<button class="warn" data-act="skip">Withdraw</button>';

  const letter = item.letter_body ? (
    '<details' + (blanks ? ' open' : '') + '><summary>Cover letter'
    + (blanks ? ' - has a blank to fill' : '') + '</summary>'
    + (editable && (item.letter_body || '').includes('{why_them}')
       ? '<label>Why them - one true sentence (fills {why_them})</label>'
         + '<textarea data-f="why_them" rows="2">' + esc(item.why_them || '') + '</textarea>'
       : '')
    + '<label>Letter as it would be sent</label>'
    + '<textarea data-f="letter" rows="7" ' + (editable ? '' : 'readonly')
    + '>' + esc(editable ? item.letter_body : finalLetter(item)) + '</textarea>'
    + (editable ? '<div class="buttons"><button class="ghost" data-act="update">Save letter</button></div>' : '')
    + '</details>') : '';

  return '<div class="card" data-id="' + esc(item.id) + '">'
    + '<h3><a href="' + esc(job.url || '') + '" target="_blank" rel="noopener">'
    + esc(job.title || '?') + '</a></h3>'
    + '<p class="co">' + esc(job.company || '') + '</p>'
    + '<div class="chipline"><span class="state ' + esc(item.state) + '">'
    + esc(item.state.replace('_', ' ')) + '</span>'
    + '<span class="why">' + (item.reasons || []).map(esc).join(' \\u00b7 ') + '</span></div>'
    + (item.needs ? '<div class="needs">' + esc(item.needs) + '</div>' : '')
    + (item.note ? '<p class="co">' + esc(item.note) + '</p>' : '')
    + letter
    + (buttons ? '<div class="buttons">' + buttons + '</div>' : '')
    + '</div>';
}

function section(title, items, emptyText) {
  return '<h2>' + title + ' <span class="count">' + items.length + '</span></h2>'
    + (items.length ? items.map(card).join('') : '<p class="empty">' + emptyText + '</p>');
}

let DATA = null;

function draw() {
  document.getElementById('lists').innerHTML =
    section('Waiting for you', DATA.waiting, 'Nothing needs you right now.')
    + section('Approved - will submit on the next run', DATA.approved, 'None approved.')
    + section('Recently done', DATA.done, 'Nothing yet.');
  document.querySelectorAll('.card [data-act]').forEach(b =>
    b.addEventListener('click', () => act(b)));
}

async function act(button) {
  const cardEl = button.closest('.card');
  const id = cardEl.dataset.id;
  const action = button.dataset.act;
  const body = {id, action};
  if (action === 'update') {
    const letterEl = cardEl.querySelector('[data-f="letter"]');
    const whyEl = cardEl.querySelector('[data-f="why_them"]');
    const noteEl = cardEl.querySelector('[data-f="note_body"]');
    if (letterEl) body.letter_body = letterEl.value;
    if (whyEl) body.why_them = whyEl.value;
    if (noteEl) body.note_body = noteEl.value;
  }
  button.disabled = true;
  try {
    const res = await api('/api/queue/action', body);
    if (!res.ok) { say(res.error, false); button.disabled = false; return; }
    say(action === 'approve' ? 'Approved - it submits on the next run.'
        : action === 'update' ? 'Saved.' : 'Done.', true);
    await load();
  } catch (e) { say(e.message, false); button.disabled = false; }
}

async function load() {
  DATA = await api('/api/queue');
  draw();
}

document.getElementById('run').addEventListener('click', async () => {
  try {
    await api('/api/queue/run', {});
    say('Submitting approved applications in the background - this page will '
        + 'show results as they land. Reload in a few minutes.', true);
  } catch (e) { say(e.message, false); }
});

load().catch(e => say(e.message, false));
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
  .savebar button,.panel button{font-family:inherit;font-size:15px;font-weight:600;
    padding:11px 22px;border-radius:6px;border:1px solid var(--accent);
    background:var(--accent);color:#fff;cursor:pointer}
  .panel button.ghostbtn{background:none;color:var(--accent);padding:8px 16px}
  .savebar button:disabled,.panel button:disabled{opacity:.55;cursor:default}
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]) .savebar button,
    :root:not([data-theme="light"]) .panel button{color:#0A121A}
    :root:not([data-theme="light"]) .panel button.ghostbtn{color:var(--accent)}
  }
  input[type=password]{width:100%;padding:10px 12px;font-size:15px;font-family:var(--mono);
    color:var(--ink);background:var(--ground);border:1px solid var(--line);
    border-radius:6px;-webkit-appearance:none}
  input[type=password]:focus{outline:2px solid var(--accent);outline-offset:1px}
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

  <div class="panel">
    <h2>AI judge</h2>
    <p class="help" style="margin:0 0 12px">With an Anthropic API key, each matching
      job gets a fit percentage and evidence drawn from your CV &mdash; roughly
      $5&ndash;15 a month. Without one, matching still works, just without the
      percentages. The key is stored only on this Mac.</p>
    <div id="aikey"></div>
  </div>

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
      + (o ? esc(o) : esc(f.empty_label || 'No preference')) + '</option>').join('') + '</select>';
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

// The AI key panel. The key is never echoed back - only presence + tail.
function drawKey(k) {
  const el = document.getElementById('aikey');
  if (k && k.present) {
    el.innerHTML = '<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">'
      + '<span>Key present &middot; ends <b>' + esc(k.tail) + '</b></span>'
      + '<button class="ghostbtn" id="keyrm" type="button">Remove</button></div>';
    document.getElementById('keyrm').addEventListener('click', async () => {
      try {
        const res = await api('/api/profile/apikey', {key: null});
        if (res.ok) { drawKey({present: false}); say('Key removed.', true); }
      } catch (e) { say(e.message, false); }
    });
  } else {
    el.innerHTML = '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start">'
      + '<div style="flex:1;min-width:220px"><input type="password" id="keyin" '
      + 'placeholder="sk-ant-..." autocomplete="off"><p class="ferr" id="keyerr"></p></div>'
      + '<button id="keysave" type="button">Save key</button></div>';
    document.getElementById('keysave').addEventListener('click', async () => {
      document.getElementById('keyerr').textContent = '';
      try {
        const res = await api('/api/profile/apikey',
                              {key: document.getElementById('keyin').value});
        if (res.ok) { drawKey(res); say('Key saved. The judge runs on the next harvest.', true); }
        else document.getElementById('keyerr').textContent = res.error || 'Save failed';
      } catch (e) { say(e.message, false); }
    });
  }
}

api('/api/profile/preferences')
  .then(d => { render(d.fields, d.values); drawKey(d.api_key); })
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
  .star{{color:var(--accent)}}
  .why{{font-size:12.5px;color:var(--accent);margin-top:4px}}
  .acts{{display:flex;gap:4px;align-items:center}}
  .act{{border:1px solid var(--line);background:var(--surface);color:var(--muted);
    border-radius:6px;min-width:34px;min-height:30px;font-size:14px;cursor:pointer;
    padding:2px 8px}}
  .act.on{{background:var(--accent);border-color:var(--accent);color:#fff}}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]) .act.on{{color:#0A121A}}
  }}
  .act:disabled{{opacity:.5}}
  .badge{{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
    text-transform:uppercase;color:var(--muted);border:1px solid var(--line);
    border-radius:3px;padding:1px 5px;white-space:nowrap}}
  .upill{{align-self:center;background:var(--accent);color:#fff;border:0;border-radius:6px;
    padding:8px 14px;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;
    font-family:inherit}}
  .upill:disabled{{opacity:.6;cursor:default}}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]) .upill{{color:#0A121A}}
  }}
  .navlinks{{margin-left:auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
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
      {foryou_stat}
      <div class="navlinks" id="navlinks" hidden>
        <a class="manage" href="http://127.0.0.1:8765/profile">Your profile</a>
        <a class="manage" href="http://127.0.0.1:8765/resume">Your CV</a>
        <a class="manage" href="http://127.0.0.1:8765/letters">Letters</a>
        <a class="manage" href="http://127.0.0.1:8765/queue">Queue</a>
        <a class="manage" href="http://127.0.0.1:8765/companies">Add companies &rarr;</a>
        <button class="upill" id="upill" hidden>Update available</button>
      </div>
    </div>
  </header>

  <div class="controls">
    <input type="search" id="q" placeholder="Search title, company or location&hellip;" autocomplete="off">
    <div class="chips">
      <button class="chip" id="f-you"   aria-pressed="false" hidden>For you</button>
      <button class="chip" id="f-all"   aria-pressed="true">Everything</button>
      <button class="chip" id="f-today" aria-pressed="false">New today</button>
      <button class="chip" id="f-week"  aria-pressed="false">This week</button>
      <button class="chip" id="f-pay"   aria-pressed="false">Salary shown</button>
      <button class="chip" id="f-applied" aria-pressed="false" hidden>Applied</button>
      <button class="chip" id="f-hidden"  aria-pressed="false" hidden>Hidden</button>
    </div>
  </div>

  <p class="count" id="count"></p>
  <p class="count" id="judgenote" hidden></p>
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
// The honest reason there are no fit percentages yet (empty = there are some).
const JUDGE_HINT = {judge_hint};
const list = document.getElementById('list');
const countEl = document.getElementById('count');
const emptyEl = document.getElementById('empty');
const q = document.getElementById('q');
let filter = 'all';

const chips = {{ you:'f-you', all:'f-all', today:'f-today', week:'f-week', pay:'f-pay',
                 applied:'f-applied', hidden:'f-hidden' }};
Object.entries(chips).forEach(([key, id]) => {{
  document.getElementById(id).addEventListener('click', () => {{
    filter = key;
    Object.values(chips).forEach(i =>
      document.getElementById(i).setAttribute('aria-pressed', String(i === id)));
    render();
  }});
}});
q.addEventListener('input', render);

// The For-you view exists only when scoring produced matches. Hidden - not
// empty - otherwise: an empty tab would read as "nothing fits you".
const HAS_MATCHES = JOBS.some(j => j.m);
if (HAS_MATCHES) {{
  document.getElementById('f-you').hidden = false;
  filter = 'you';
  document.getElementById('f-you').setAttribute('aria-pressed', 'true');
  document.getElementById('f-all').setAttribute('aria-pressed', 'false');
}}

// Applied and Hidden chips appear only once she has used them.
function refreshStatusChips() {{
  document.getElementById('f-applied').hidden = !JOBS.some(j => j.st === 'applied');
  document.getElementById('f-hidden').hidden = !JOBS.some(j => j.st === 'hidden');
}}
refreshStatusChips();

// Her verdict buttons. Only the served page can write (it carries the token);
// the offline Desktop file shows read-only badges instead.
function actions(j) {{
  if (!SERVED_TOKEN) {{
    if (j.st === 'applied') return '<span class="badge">Applied</span>';
    if (j.st === 'starred') return '<span class="badge">\\u2605</span>';
    return '';
  }}
  const btn = (set, glyph, label) =>
    '<button class="act' + (j.st === set ? ' on' : '') + '" data-fp="' + esc(j.id)
    + '" data-set="' + set + '" title="' + label + '">' + glyph + '</button>';
  // Queue only where it makes sense: a For-you match she has not already
  // applied to. The click handler POSTs /api/queue/propose.
  const queue = (j.m && j.st !== 'applied')
    ? '<button class="act" data-fp="' + esc(j.id)
      + '" data-queue="1" title="Draft an application for approval">Queue</button>'
    : '';
  return '<span class="acts">'
    + queue
    + btn('starred', '\\u2605', 'Star it')
    + btn('applied', '\\u2713', 'Mark applied')
    + btn('hidden', '\\u2715', 'Hide it')
    + '</span>';
}}

document.getElementById('list').addEventListener('click', async ev => {{
  const b = ev.target.closest('.act');
  if (!b || !SERVED_TOKEN) return;
  ev.preventDefault();
  const j = JOBS.find(x => x.id === b.dataset.fp);
  if (!j) return;
  if (b.dataset.queue) {{
    b.disabled = true;
    try {{
      const res = await fetch('/api/queue/propose', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json', 'X-Meester-Token': SERVED_TOKEN}},
        body: JSON.stringify({{fingerprint: j.id}})
      }});
      const d = await res.json();
      b.textContent = d.ok ? 'Queued \u2713' : (d.error || 'Failed');
    }} catch (e) {{ b.disabled = false; }}
    return;
  }}
  const next = j.st === b.dataset.set ? null : b.dataset.set;
  b.disabled = true;
  try {{
    const res = await fetch('/api/jobs/status', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', 'X-Meester-Token': SERVED_TOKEN}},
      body: JSON.stringify({{fingerprint: j.id, state: next}})
    }});
    if (res.ok) {{
      if (next) j.st = next; else delete j.st;
      refreshStatusChips();
      render();
    }}
  }} catch (e) {{}}
  b.disabled = false;
}});

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
  let rows = JOBS.filter(j => {{
    const st = j.st || '';
    // Hidden means hidden everywhere except its own chip; a job she has
    // already applied to has no business back in "For you".
    if (filter === 'hidden') {{ if (st !== 'hidden') return false; }}
    else if (st === 'hidden') return false;
    if (filter === 'applied' && st !== 'applied') return false;
    if (filter === 'you'   && (!j.m || st === 'applied')) return false;
    if (filter === 'today' && !(j.a !== null && j.a <= 1)) return false;
    if (filter === 'week'  && !(j.a !== null && j.a <= 7)) return false;
    if (filter === 'pay'   && !j.s) return false;
    if (!term) return true;
    return (j.t + ' ' + j.c + ' ' + j.l + ' ' + j.d).toLowerCase().includes(term);
  }});

  // For-you ranks by fit (dream companies pinned); every other view is by age.
  if (filter === 'you')
    rows = rows.slice().sort((a, b) =>
      (b.dr || 0) - (a.dr || 0) || (b.fit ?? -1) - (a.fit ?? -1)
      || (b.sc || 0) - (a.sc || 0) || (a.a ?? 999) - (b.a ?? 999));

  countEl.textContent = rows.length + (rows.length === 1 ? ' role' : ' roles')
    + (filter === 'you' ? ' that fit your profile' : '');
  const judgeOff = filter === 'you' && rows.length > 0 && !rows.some(r => r.fit != null);
  const note = document.getElementById('judgenote');
  note.textContent = JUDGE_HINT;
  note.hidden = !judgeOff || !JUDGE_HINT;
  emptyEl.hidden = rows.length > 0;

  list.innerHTML = rows.map(j => {{
    const isNew = j.a !== null && j.a <= 1;
    const bits = [j.l, j.d, j.s].filter(Boolean).map(esc);
    const star = j.dr ? '<span class="star" title="Dream company">\\u2605</span> ' : '';
    let whyBits = (j.r || []).map(esc);
    if (j.fit != null) whyBits.unshift('<b>' + j.fit + '% fit</b>');
    if (j.ev) whyBits.push(esc(j.ev));
    const why = whyBits.length
      ? '<div class="why">' + whyBits.join(' \\u00b7 ') + '</div>' : '';
    return '<li><div class="main">'
      + '<a href="' + esc(j.u) + '" target="_blank" rel="noopener">' + esc(j.t) + '</a>'
      + '<div class="meta">' + star + '<span class="co">' + esc(j.c) + '</span>'
      + bits.map(b => '<span>' + b + '</span>').join('')
      + '</div>' + why + '</div>'
      + (isNew ? '<span class="new">New</span>' : '')
      + actions(j)
      + '<span class="age">' + age(j.a) + '</span></li>';
  }}).join('');
}}

render();

// Only offer the Companies screen if the local helper is actually running.
// A dead link is worse than no link for someone who won't debug it.
fetch('http://127.0.0.1:8765/api/ping', {{mode: 'cors'}})
  .then(r => {{
    if (!r.ok) return;
    document.getElementById('navlinks').hidden = false;
    // This offline file is read-only by design (it must never carry the write
    // token). When the app is up, say so - otherwise the star/queue buttons
    // just look mysteriously missing.
    if (!SERVED_TOKEN) {{
      document.querySelector('header .sub').insertAdjacentHTML('beforeend',
        ' \\u00b7 <a href="http://127.0.0.1:8765/">open the live app</a>'
        + ' to star, hide or queue jobs');
    }}
  }})
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
        upill.textContent = 'Update failed \\u2014 ask Claude in the dev folder';
        upill.disabled = false;
      }}
    }});
  }})
  .catch(() => {{}});
</script>
</body>
</html>
"""
