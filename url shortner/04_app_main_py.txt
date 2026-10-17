from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import cache, db
from .codes import LinkError, encode, is_safe, normalise_url, validate_custom

app = FastAPI(title="url-shortener")


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


@app.get("/", response_class=HTMLResponse)
def index():
    """Interactive Web Dashboard for URL shortening, link management, and analytics."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>URL Shortener & Click Analytics</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --accent: #10b981;
      --danger: #ef4444;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
      padding: 2rem 1rem;
      min-height: 100vh;
    }
    .container { max-width: 900px; margin: 0 auto; }
    header { margin-bottom: 2rem; text-align: center; }
    h1 { font-size: 2.2rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem; }
    p.subtitle { color: var(--text-muted); font-size: 1rem; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .form-group { display: flex; flex-direction: column; gap: 0.75rem; }
    .input-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    input[type="text"], input[type="url"] {
      flex: 1;
      min-width: 200px;
      padding: 0.75rem 1rem;
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: #fff;
      font-size: 1rem;
    }
    input:focus { outline: 2px solid var(--primary); border-color: transparent; }
    button {
      padding: 0.75rem 1.5rem;
      border-radius: 8px;
      border: none;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      transition: background-color 0.15s ease;
    }
    .btn-primary { background: var(--primary); color: #0f172a; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-danger { background: var(--danger); color: #fff; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
    .btn-secondary { background: #334155; color: #fff; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
    .btn-secondary:hover { background: #475569; }
    .status-msg { margin-top: 1rem; padding: 0.75rem; border-radius: 8px; display: none; font-size: 0.95rem; }
    .status-success { background: rgba(16, 185, 129, 0.2); border: 1px solid var(--accent); color: #34d399; }
    .status-error { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #f87171; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
    th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
    td { font-size: 0.95rem; vertical-align: middle; }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: #0284c7;
      color: #fff;
      cursor: pointer;
    }
    .badge:hover { background: var(--primary); }
    a.link { color: var(--primary); text-decoration: none; word-break: break-all; }
    a.link:hover { text-decoration: underline; }
    .actions-cell { display: flex; gap: 0.5rem; align-items: center; }
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      align-items: center;
      justify-content: center;
      padding: 1rem;
      z-index: 100;
    }
    .modal-content {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      max-width: 500px;
      width: 100%;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
    .close-btn { background: transparent; border: none; color: var(--text-muted); font-size: 1.5rem; cursor: pointer; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>URL Shortener & Click Analytics</h1>
      <p class="subtitle">Cloud-native URL shortener with real-time analytics, caching & branch promotion</p>
    </header>

    <div class="card">
      <h2 style="font-size: 1.25rem; margin-bottom: 1rem;">Create a Short Link</h2>
      <div class="form-group">
        <div class="input-row">
          <input type="url" id="target-url" placeholder="https://example.com/very/long/url" required />
          <input type="text" id="custom-code" placeholder="custom code (optional)" style="max-width: 220px;" />
          <button class="btn-primary" onclick="createLink()">Shorten</button>
        </div>
        <p style="font-size: 0.82rem; color: var(--text-muted); margin-top: 0.35rem;">
          💡 <strong>Tip:</strong> Custom code is <em>optional</em> (auto-generated if empty). Allowed: 3–32 alphanumeric chars (no symbols; excludes confusing <code>0, o, O, 1, l, I</code>).
        </p>
        <div style="display: flex; gap: 0.6rem; margin-top: 0.2rem; font-size: 0.82rem; color: var(--text-muted); align-items: center;">
          <span>Demo examples:</span>
          <button type="button" class="btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="setDemo('https://github.com', 'github')">github</button>
          <button type="button" class="btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="setDemo('https://fastapi.tiangolo.com', 'fast')">fast</button>
          <button type="button" class="btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="setDemo('https://en.wikipedia.org', 'speed')">speed</button>
          <button type="button" class="btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="setDemo('https://example.com/demo-test', 'mycup')">mycup</button>
        </div>
        <div id="status-box" class="status-msg"></div>
      </div>
    </div>

    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <h2 style="font-size: 1.25rem;">Active Links</h2>
        <button class="btn-secondary" onclick="loadLinks()">Refresh</button>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Short Code</th>
              <th>Destination URL</th>
              <th>Clicks</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="links-tbody">
            <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Loading links...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Stats Modal -->
  <div id="stats-modal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="stats-title">Link Analytics</h3>
        <button class="close-btn" onclick="closeModal('stats-modal')">&times;</button>
      </div>
      <div id="stats-body" style="font-size: 0.95rem;">Loading analytics...</div>
    </div>
  </div>

  <!-- Edit Modal -->
  <div id="edit-modal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="edit-title">Update Destination URL</h3>
        <button class="close-btn" onclick="closeModal('edit-modal')">&times;</button>
      </div>
      <input type="hidden" id="edit-code" />
      <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;">
        <input type="url" id="edit-url" placeholder="https://new-destination.com" style="width: 100%;" />
        <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
          <button class="btn-secondary" onclick="closeModal('edit-modal')">Cancel</button>
          <button class="btn-primary" onclick="submitEdit()">Save Changes</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    function setDemo(url, code) {
      document.getElementById('target-url').value = url;
      document.getElementById('custom-code').value = code;
    }

    async function loadLinks() {
      const tbody = document.getElementById('links-tbody');
      try {
        const res = await fetch('/api/links');
        const data = await res.json();
        if (!data.links || data.links.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No links created yet.</td></tr>';
          return;
        }
        tbody.innerHTML = data.links.map(l => `
          <tr>
            <td>
              <a class="link" href="/${l.code}" target="_blank">/${l.code}</a>
            </td>
            <td>
              <span title="${l.url}">${l.url.length > 40 ? l.url.substring(0, 40) + '...' : l.url}</span>
            </td>
            <td>
              <span class="badge" onclick="showStats('${l.code}')" title="View click analytics">${l.clicks} clicks</span>
            </td>
            <td class="actions-cell">
              <button class="btn-secondary" onclick="openEdit('${l.code}', '${l.url}')">Edit</button>
              <button class="btn-danger" onclick="deleteLink('${l.code}')">Delete</button>
            </td>
          </tr>
        `).join('');
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="color: var(--danger);">Failed to load links: ${err.message}</td></tr>`;
      }
    }

    async function createLink() {
      const urlInput = document.getElementById('target-url');
      const customInput = document.getElementById('custom-code');
      const statusBox = document.getElementById('status-box');
      const url = urlInput.value.trim();
      const custom = customInput.value.trim();

      if (!url) {
        showStatus('Please enter a target URL.', 'error');
        return;
      }

      try {
        const payload = { url };
        if (custom) payload.custom = custom;
        const res = await fetch('/shorten', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Failed to shorten URL');
        }
        showStatus(`Link created: <a class="link" href="/${data.code}" target="_blank">/${data.code}</a> &rarr; ${data.url}`, 'success');
        urlInput.value = '';
        customInput.value = '';
        loadLinks();
      } catch (err) {
        showStatus(err.message, 'error');
      }
    }

    async function deleteLink(code) {
      if (!confirm(`Are you sure you want to delete /${code}?`)) return;
      try {
        const res = await fetch(`/api/links/${code}`, { method: 'DELETE' });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || 'Failed to delete');
        }
        loadLinks();
      } catch (err) {
        alert(err.message);
      }
    }

    function openEdit(code, currentUrl) {
      document.getElementById('edit-code').value = code;
      document.getElementById('edit-url').value = currentUrl;
      document.getElementById('edit-title').innerText = `Update /${code}`;
      document.getElementById('edit-modal').style.display = 'flex';
    }

    async function submitEdit() {
      const code = document.getElementById('edit-code').value;
      const newUrl = document.getElementById('edit-url').value.trim();
      if (!newUrl) return;

      try {
        const res = await fetch(`/api/links/${code}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: newUrl })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Update failed');
        closeModal('edit-modal');
        loadLinks();
      } catch (err) {
        alert(err.message);
      }
    }

    async function showStats(code) {
      const modal = document.getElementById('stats-modal');
      const body = document.getElementById('stats-body');
      document.getElementById('stats-title').innerText = `Analytics for /${code}`;
      modal.style.display = 'flex';
      body.innerHTML = 'Loading...';

      try {
        const res = await fetch(`/api/links/${code}/stats`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Could not load stats');

        let html = `<p style="margin-bottom: 0.75rem;"><strong>Target:</strong> <a class="link" href="${data.url}" target="_blank">${data.url}</a></p>`;
        html += '<h4 style="margin-top: 1rem; margin-bottom: 0.5rem; color: var(--primary);">Top Referrers</h4>';
        if (data.referrers.length === 0) {
          html += '<p style="color: var(--text-muted);">No referrers recorded yet.</p>';
        } else {
          html += '<ul>' + data.referrers.map(r => `<li>${r.referrer}: <strong>${r.clicks}</strong> clicks</li>`).join('') + '</ul>';
        }

        html += '<h4 style="margin-top: 1rem; margin-bottom: 0.5rem; color: var(--primary);">Clicks Per Day</h4>';
        if (data.per_day.length === 0) {
          html += '<p style="color: var(--text-muted);">No daily activity recorded yet.</p>';
        } else {
          html += '<ul>' + data.per_day.map(d => `<li>${d.day}: <strong>${d.clicks}</strong> clicks</li>`).join('') + '</ul>';
        }
        body.innerHTML = html;
      } catch (err) {
        body.innerHTML = `<p style="color: var(--danger);">${err.message}</p>`;
      }
    }

    function closeModal(id) {
      document.getElementById(id).style.display = 'none';
    }

    function showStatus(msg, type) {
      const box = document.getElementById('status-box');
      box.innerHTML = msg;
      box.className = `status-msg status-${type}`;
      box.style.display = 'block';
    }

    window.onclick = function(e) {
      if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
      }
    };

    loadLinks();
  </script>
</body>
</html>
"""


@app.post("/shorten", status_code=201)
def shorten(payload: dict = Body(...)):
    try:
        url = normalise_url(payload.get("url"))
    except LinkError as e:
        raise HTTPException(400, str(e))
    if not is_safe(url):
        raise HTTPException(400, "that host is not allowed")

    custom = payload.get("custom")
    if custom:
        try:
            code = validate_custom(custom)
        except LinkError as e:
            raise HTTPException(400, str(e))
        if db.one("SELECT 1 FROM links WHERE code = %s", (code,)):
            raise HTTPException(409, f"{code!r} is already taken")
        try:
            row = db.one("INSERT INTO links (code, url) VALUES (%s,%s) RETURNING id, code",
                         (code, url))
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise HTTPException(409, f"{code!r} is already taken")
            raise
    else:
        row = db.one("INSERT INTO links (code, url) VALUES ('', %s) RETURNING id", (url,))
        code = encode(row["id"])
        db.query("UPDATE links SET code = %s WHERE id = %s", (code, row["id"]), fetch=False)

    cache.drop(f"link:{code}")
    return {"code": code, "url": url, "short": f"/{code}"}


@app.get("/api/links")
def list_links():
    return {"links": db.query(
        "SELECT l.code, l.url, l.created_at,"
        " (SELECT count(*) FROM clicks c WHERE c.link_id = l.id) AS clicks"
        " FROM links l WHERE l.code <> '' ORDER BY l.id DESC LIMIT 200")}


@app.get("/api/links/{code}/stats")
def stats(code: str):
    link = db.one("SELECT id, code, url FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    return {
        "code": code, "url": link["url"],
        "per_day": db.query(
            "SELECT clicked_at::date AS day, count(*) AS clicks FROM clicks"
            " WHERE link_id = %s GROUP BY day ORDER BY day DESC LIMIT 30", (link["id"],)),
        "referrers": db.query(
            "SELECT coalesce(nullif(referrer,''),'(direct)') AS referrer, count(*) AS clicks"
            " FROM clicks WHERE link_id = %s GROUP BY 1 ORDER BY clicks DESC LIMIT 10",
            (link["id"],)),
    }


@app.put("/api/links/{code}")
def update_link(code: str, payload: dict = Body(...)):
    """Update destination URL for an existing link."""
    link = db.one("SELECT id, code, url FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    try:
        new_url = normalise_url(payload.get("url"))
    except LinkError as e:
        raise HTTPException(400, str(e))
    if not is_safe(new_url):
        raise HTTPException(400, "that host is not allowed")

    db.query("UPDATE links SET url = %s WHERE code = %s", (new_url, code), fetch=False)
    cache.drop(f"link:{code}")
    return {"code": code, "url": new_url, "short": f"/{code}"}


@app.delete("/api/links/{code}")
def delete_link(code: str):
    """Delete a link and purge its cache and analytics."""
    link = db.one("SELECT id FROM links WHERE code = %s", (code,))
    if not link:
        raise HTTPException(404, "no such code")
    db.query("DELETE FROM links WHERE code = %s", (code,), fetch=False)
    cache.drop(f"link:{code}", f"clicks:{code}")
    return {"status": "deleted", "code": code}


@app.get("/{code}")
def follow(code: str, request: Request = None):
    """The hot path. Served from Redis so a redirect never queries Postgres."""
    hit = cache.get_json(f"link:{code}")
    if hit:
        link_id, url = hit["id"], hit["url"]
    else:
        link = db.one("SELECT id, url FROM links WHERE code = %s", (code,))
        if not link:
            raise HTTPException(404, "no such code")
        link_id, url = link["id"], link["url"]
        cache.set_json(f"link:{code}", {"id": link_id, "url": url}, ttl=3600)

    referrer = request.headers.get("referer", "") if request else ""
    db.query("INSERT INTO clicks (link_id, referrer) VALUES (%s, %s)", (link_id, referrer),
             fetch=False)
    cache.client().incr(f"clicks:{code}")
    return RedirectResponse(url, status_code=302)
