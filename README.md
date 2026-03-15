# SVCS Server (a tiny Flask gremlin that holds your commits)

this is the **server** part of SVCS.  
it's basically a small flask app that sits there and accepts your SVCS client's HTTP requests like:

> "hello yes i would like to upload my entire `.svcs` folder and also my working directory please"  
> — the client, probably

it stores "remote repos" on disk under `repos/` and pretends it's a grown-up version control hosting service.  
it is not. it is a **filesystem with an attitude**.

as of recently, it also does **login** and **per-user repo scoping**, because apparently we live in a society.

---

## What does it do?

this server exists so the SVCS client can:

- **login** to get a token (`POST /login`)
- **create** a remote repo (`POST /create/<user>/<repo>`)
- **push** SVCS data (`objects`, `commits`, `twigs`) (`POST /push/<user>/<repo>`)
- **pull** only the SVCS database part (`GET /pull/<user>/<repo>`)
- **serve snapshots** of a commit's working tree so `clone` can reconstruct files (`GET /snapshot/<user>/<repo>/<commit>`)
- list repos for a user (`GET /repos/<user>`)
- vibe-check itself (`GET /health`)

tl;dr: it's the "remote" your client points at when you run `svcs remote add ...`, except now it's like:
> "remote add origin http://server myrepo"  
> and then also  
> "btw i'm alice and i have a token"  

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

- `POST /login`
- `POST /create/<user>/<repo>`
- `POST /push/<user>/<repo>`
- `GET  /pull/<user>/<repo>`
- `GET  /snapshot/<user>/<repo>/<commit>`
- `GET  /repos/<user>`
- `GET  /health`

---

## Auth (aka "fine, you get tokens")

### `POST /login`
login returns a token you use for basically everything else.

request:

```bash
curl -X POST http://127.0.0.1:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret"}'
```

response:

```json
{ "token": "....", "username": "alice" }
```

user creation:
- in this toy server, users are typically **auto-created on first login** (aka: "signup by existing")
- user data is stored in `users.json`
- tokens are stored in `tokens.json`

### auth header
all protected routes require:

```text
Authorization: Bearer <token>
```

example:

```bash
TOKEN="...token from /login..."
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/repos/alice
```

---

## Where does it store stuff?

it makes a folder tree like:

```text
repos/<username>/<repo>/
```

inside each repo you get:

- `objects/` - blob objects by hash (binary files)
- `commits/` - commit json docs (`<commit>.json`)
- `twigs/` - twig pointers (file name = twig)
- `snapshots/` - working-tree snapshots per commit (`<commit>.json`)
- `HEAD` - default twig name (created as `main`)

so yeah... it's literally "git, if git was a pile of folders", but now it also believes in *folders per person*.

---

## the API (aka "the endpoints i told flask to babysit")

### `GET /health`
returns `{ ok: true, routes: [...] }` so you can see what the server *thinks* it is.

---

### `POST /create/<user>/<repo>`
creates a new remote repo **under that user**.

- **201**: created
- **400**: already exists
- **401**: missing/invalid token
- **403**: token user != `<user>` in the path (nice try)

example:

```bash
TOKEN="..."
curl -X POST http://127.0.0.1:5000/create/alice/myrepo \
  -H "Authorization: Bearer $TOKEN"
```

---

### `POST /push/<user>/<repo>`
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

- `objects`, `commits`, `twigs` = the **.svcs database**
- `working_tree` is optional, but if you want `clone` to actually recreate files, you probably want it
- if both `working_tree` and `snapshot_commit` are present, it stores a snapshot at:
  - `repos/<user>/<repo>/snapshots/<snapshot_commit>.json`

responses:

- **200**: push successful
- **404**: repo not found
- **400**: invalid base64 object data (aka you sent cursed bytes)
- **401**: unauthorized (no token / bad token)
- **403**: forbidden (wrong user in URL)

tiny example push (mostly useless but it proves the endpoint exists):

```bash
TOKEN="..."
curl -X POST http://127.0.0.1:5000/push/alice/myrepo \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"objects": {}, "commits": {}, "twigs": {}}'
```

---

### `GET /pull/<user>/<repo>`
returns **only** the SVCS DB portion:

- objects (base64)
- commits (json)
- twigs (strings)

this is *on purpose* so clients can sync `.svcs` without overwriting working files.

example:

```bash
TOKEN="..."
curl http://127.0.0.1:5000/pull/alice/myrepo \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /snapshot/<user>/<repo>/<commit>`
returns the stored working-tree snapshot for that commit id.

this is what makes `svcs clone ...` work without needing a real checkout protocol.

example:

```bash
TOKEN="..."
curl http://127.0.0.1:5000/snapshot/alice/myrepo/a1b2c3d \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /repos/<user>`
lists all repos on disk under `repos/<user>/`.

example:

```bash
TOKEN="..."
curl http://127.0.0.1:5000/repos/alice \
  -H "Authorization: Bearer $TOKEN"
```

---

## Security warning (aka "please don't put this on the public internet")

this server is intentionally minimal and **still not secure** in any serious way:

- auth is "basic token + json files"
- no rate limiting
- no lock/transaction safety
- this is a toy. a funny toy. but still a toy.

run it only on your own machine or a trusted network unless you *enjoy* chaos.

---

## Typical workflow (with the SVCS client)

1. start this server
2. on the client (first time):
   - `svcs init`
   - `svcs remote add origin http://127.0.0.1:5000 myrepo`
   - `svcs login http://127.0.0.1:5000 alice secret`
3. commit + push:
   - `svcs add .`
   - `svcs commit "hello from the void"`
   - `svcs push origin --user alice`
4. on another machine (or folder) clone:
   - `svcs clone http://127.0.0.1:5000 myrepo some-folder --user alice`

and then you pretend you built github. (you didn't. but it's cute.)

---

## License

This project is MIT Licensed. Do whatever you want with it, just don't sue me if your files get lost in the time vortex.