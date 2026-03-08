# SVCS Remote Server (Flask)

This is the **SVCS remote server** implementation. It provides a tiny HTTP API that the SVCS client can use to:

- create remote repositories
- **push** SVCS data (`objects`, `commits`, `branches`) plus an optional working-tree snapshot
- **pull** only the SVCS database portion (so clients can sync `.svcs` without overwriting their working files)
- serve a **snapshot** of a commit’s working tree (so `clone` can download the full project files)

Remote repositories are stored on disk under a `repos/` directory.

---

## Requirements

- Python **3.9+**
- Flask

Install:

```bash
pip install flask
```

---

## Run the server

From the directory containing the server script (e.g. `repo_manager.py`):

```bash
python3 repo_manager.py
```

The server listens on:

- `http://0.0.0.0:5000` (accessible on the LAN)
- locally: `http://127.0.0.1:5000`

---

## Verify it’s the right server

This server provides a `/health` endpoint that lists supported routes:

```bash
curl http://127.0.0.1:5000/health
```

Expected output includes:

- `POST /create/<repo>`
- `POST /push/<repo>`
- `GET  /pull/<repo>`
- `GET  /snapshot/<repo>/<commit>`
- `GET  /repos`
- `GET  /health`

If `/health` returns a Flask 404 HTML page, you are not running this server file/process.

---

## On-disk layout

Each remote repo is stored at:

```
repos/<repo>/
```

Inside each repo:

- `objects/` — blob objects by hash (binary files)
- `commits/` — commit JSON documents (`<commit>.json`)
- `branches/` — branch head pointers (file name = branch name)
- `snapshots/` — working-tree snapshots per commit (`<commit>.json`)
- `HEAD` — default branch name (created as `main`)

---

## API

### `GET /health`
Returns basic status and route list.

**Response:** JSON

---

### `POST /create/<repo>`
Create a new remote repository named `<repo>`.

- **201**: created
- **400**: repo already exists

Example:

```bash
curl -X POST http://127.0.0.1:5000/create/myrepo
```

---

### `POST /push/<repo>`
Push SVCS database content to the remote repository.

**Request body (JSON):**

```json
{
  "objects": {
    "<sha1>": "<base64-bytes>"
  },
  "commits": {
    "<commitId>": { "... commit json ..." }
  },
  "branches": {
    "<branchName>": "<commitId>"
  },

  "working_tree": {
    "path/to/file.txt": "<base64-bytes>"
  },
  "snapshot_commit": "<commitId>"
}
```

Notes:

- `objects`, `commits`, `branches` are the **SVCS database portion**.
- `working_tree` is optional but recommended if you want `clone` to reconstruct the full working directory.
- If both `working_tree` and `snapshot_commit` are present, the server stores a snapshot under:
  - `repos/<repo>/snapshots/<snapshot_commit>.json`

**Responses:**
- **200**: push successful
- **404**: repo not found
- **400**: invalid base64 object data (if decoding fails)

Example:

```bash
curl -X POST http://127.0.0.1:5000/push/myrepo \
  -H "Content-Type: application/json" \
  -d '{"objects": {}, "commits": {}, "branches": {}}'
```

---

### `GET /pull/<repo>`
Pull returns **only** the SVCS database portion (`objects`, `commits`, `branches`).

This is intentionally designed so clients can sync `.svcs` without overwriting their working directory files.

**Response (JSON):**

```json
{
  "objects": { "<sha1>": "<base64-bytes>" },
  "commits": { "<commitId>": { "... commit json ..." } },
  "branches": { "<branchName>": "<commitId>" }
}
```

**Responses:**
- **200**: ok
- **404**: repo not found

Example:

```bash
curl http://127.0.0.1:5000/pull/myrepo
```

---

### `GET /snapshot/<repo>/<commit>`
Returns the stored working-tree snapshot for a given commit id.

Used primarily by the client’s `clone` command.

**Responses:**
- **200**: JSON mapping `path -> base64 file contents`
- **404**: repo not found
- **404**: snapshot not found for commit

Example:

```bash
curl http://127.0.0.1:5000/snapshot/myrepo/a1b2c3d
```

---

### `GET /repos`
Lists remote repositories available on the server.

Example:

```bash
curl http://127.0.0.1:5000/repos
```

---

## Security warning

This server is intentionally minimal and **not secure**:

- no authentication
- no access control
- no rate limiting
- accepts arbitrary file paths in snapshots (clients should behave, but don’t expose this publicly)

Run it only in a trusted environment (local machine / private network).

---

## Typical workflow (with SVCS client)

1. Start server
2. Client creates commits locally
3. Client `push` uploads SVCS DB + snapshot
4. Another client `clone` pulls SVCS DB + fetches snapshot to reconstruct files

---