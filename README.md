# SVCS Server (a tiny Flask gremlin that holds your commits)

this is the **server** part of SVCS.  
it's basically a small flask app that sits there and accepts your SVCS client's HTTP requests like:

> "hello yes i would like to upload my entire `.svcs` folder and also my working directory please"  
> - the client, probably

it stores "remote repos" on disk under `repos/` and pretends it's a grown-up version control hosting service.
it is not. it is a **filesystem with an attitude**.

---

## What does it do?

this server exists so the SVCS client can:

- **create** a remote repo (`POST /create/<repo>`)
- **push** SVCS data (`objects`, `commits`, `twigs`) (`POST /push/<repo>`)
- **pull** only the SVCS database part (`GET /pull/<repo>`)
- **serve snapshots** of a commit's working tree so `clone` can reconstruct files (`GET /snapshot/<repo>/<commit>`)
- list repos (`GET /repos`)
- vibe-check itself (`GET /health`)

tl;dr: it's the "remote" your client points at when you run `svcs remote add ...`.

---

## Requirements

- python **3.9+**
- flask

install flask:

```bash
pip install flask
```

(yes i know, i could've used a requirements.txt. i didn't. welcome to svcs.)

---

## Run it

from this repo folder:

```bash
python3 server.py
```

it runs on:

- `http://0.0.0.0:5000` (LAN / "oops i exposed it" mode)
- `http://127.0.0.1:5000` (your own machine, where it belongs)

---

## Verify you're running the right thing

this server has a `/health` endpoint that tells you what routes it supports:

```bash
curl http://127.0.0.1:5000/health
```

if you get a flask 404 html blob, congrats: you're not running this server (or you angered the network gods).

expected routes include:

- `POST /create/<repo>`
- `POST /push/<repo>`
- `GET  /pull/<repo>`
- `GET  /snapshot/<repo>/<commit>`
- `GET  /repos`
- `GET  /health`

---

## Where does it store stuff?

it makes a folder called:

```text
repos/<repo>/
```

inside each repo you get:

- `objects/` - blob objects by hash (binary files)
- `commits/` - commit json docs (`<commit>.json`)
- `twigs/` - twig pointers (file name = twig)
- `snapshots/` - working-tree snapshots per commit (`<commit>.json`)
- `HEAD` - default twig name (created as `main`)

so yeah... it's literally "git, if git was a pile of folders".

---

## the API (aka "the endpoints i told flask to babysit")

### `GET /health`
returns `{ ok: true, routes: [...] }` so you can see what the server *thinks* it is.

---

### `POST /create/<repo>`
creates a new remote repo.

- **201**: created
- **400**: already exists

example:

```bash
curl -X POST http://127.0.0.1:5000/create/myrepo
```

---

### `POST /push/<repo>`
uploads SVCS database content *and optionally* a working tree snapshot.

the client usually sends:

```json
{
  "objects": {
    "<sha1>": "<base64-bytes>"
  },
  "commits": {
    "<commitId>": { "... commit json ..." }
  },
  "twigs": {
    "<twigName>": "<commitId>"
  },

  "working_tree": {
    "path/to/file.txt": "<base64-bytes>"
  },
  "snapshot_commit": "<commitId>"
}
```

notes (read these, future-me will thank you):

- `objects`, `commits`, `tiwgs` = the **.svcs database**
- `working_tree` is optional, but if you want `clone` to actually recreate files, you probably want it
- if both `working_tree` and `snapshot_commit` are present, it stores a snapshot at:
  - `repos/<repo>/snapshots/<snapshot_commit>.json`

responses:

- **200**: push successful
- **404**: repo not found
- **400**: invalid base64 object data (aka you sent cursed bytes)

tiny example push (mostly useless but it proves the endpoint exists):

```bash
curl -X POST http://127.0.0.1:5000/push/myrepo \
  -H "Content-Type: application/json" \
  -d '{"objects": {}, "commits": {}, "tiwgs": {}}'
```

---

### `GET /pull/<repo>`
returns **only** the SVCS DB portion:

- objects (base64)
- commits (json)
- tiwgs (strings)

this is *on purpose* so clients can sync `.svcs` without overwriting working files.

example:

```bash
curl http://127.0.0.1:5000/pull/myrepo
```

---

### `GET /snapshot/<repo>/<commit>`
returns the stored working-tree snapshot for that commit id.

this is what makes `svcs clone ...` work without needing a real checkout protocol.

example:

```bash
curl http://127.0.0.1:5000/snapshot/myrepo/a1b2c3d
```

---

### `GET /repos`
lists all repos on disk under `repos/`.

example:

```bash
curl http://127.0.0.1:5000/repos
```

---

## Security warning (aka "please don't put this on the public internet")

this server is intentionally minimal and **not secure**:

- no authentication
- no access control
- no rate limiting
- accepts arbitrary file paths in snapshots (yes, i know)

run it only on your own machine or a trusted network unless you *enjoy* chaos.

---

## Typical workflow (with the SVCS client)

1. start this server
2. on the client:
   - `svcs init`
   - commit some stuff
   - `svcs remote add origin http://127.0.0.1:5000 myrepo`
   - `svcs push origin`
3. on another machine (or folder) clone:
   - `svcs clone http://127.0.0.1:5000 myrepo some-folder`

and then you pretend you built github. (you didn't. but it's cute.)

---

## License

This project is MIT Licensed. Do whatever you want with it, just don't sue me if your files get lost in the time vortex.
