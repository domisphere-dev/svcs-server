from flask import Flask, request, jsonify
import os
import json
import base64
import secrets
import hashlib
import hmac
from functools import wraps

app = Flask(__name__)

BASE_DIR = "repos"
os.makedirs(BASE_DIR, exist_ok=True)

# Simple auth storage (toy, but works):
# tokens.json: { "<token>": { "username": "...", "created_at": 1234567890 } }
TOKENS_FILE = "tokens.json"

# Simple user DB (toy):
# users.json: { "<username>": { "password_sha256": "<hex>" } }
USERS_FILE = "users.json"


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _timing_safe_equal(a: str, b: str) -> bool:
    # Avoid leaking info via timing.
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _load_users():
    return read_json(USERS_FILE) or {}


def _save_users(users):
    write_json(USERS_FILE, users)


def _load_tokens():
    return read_json(TOKENS_FILE) or {}


def _save_tokens(tokens):
    write_json(TOKENS_FILE, tokens)


def ensure_user_dir(username: str):
    # Ensure repos/<username>/ exists
    os.makedirs(os.path.join(BASE_DIR, username), exist_ok=True)


def repo_path(username: str, repo: str):
    # repos/<username>/<repo>/
    ensure_user_dir(username)
    return os.path.join(BASE_DIR, username, repo)


def ensure_repo_dirs(path):
    os.makedirs(os.path.join(path, "objects"), exist_ok=True)
    os.makedirs(os.path.join(path, "commits"), exist_ok=True)
    os.makedirs(os.path.join(path, "twigs"), exist_ok=True)
    os.makedirs(os.path.join(path, "snapshots"), exist_ok=True)
    head = os.path.join(path, "HEAD")
    if not os.path.exists(head):
        with open(head, "w") as f:
            f.write("main")


def snapshot_path(repo_dir, commit_id):
    return os.path.join(repo_dir, "snapshots", f"{commit_id}.json")


def _get_bearer_token():
    auth = request.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip(), parts[1].strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_bearer_token()
        if not token:
            return "missing bearer token", 401
        tokens = _load_tokens()
        info = tokens.get(token)
        if not info or "username" not in info:
            return "invalid token", 401
        # stash username for handler use
        request.svcs_user = info["username"]
        return fn(*args, **kwargs)

    return wrapper


@app.get("/health")
def health():
    return jsonify(
        ok=True,
        routes=[
            "POST /login",
            "POST /create/<user>/<repo>",
            "POST /push/<user>/<repo>",
            "GET  /pull/<user>/<repo>",
            "GET  /snapshot/<user>/<repo>/<commit>",
            "GET  /repos/<user>",
            "GET  /health",
        ],
    )


@app.post("/login")
def login():
    """
    Basic login that issues a token per user.

    Request JSON:
      { "username": "...", "password": "..." }

    If username doesn't exist yet, we auto-create it (toy behavior).
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")

    if not username or not password:
        return "missing username/password", 400

    users = _load_users()
    pw_hash = _sha256_hex(password)

    if username not in users:
        # Auto-register (simple/dev-friendly)
        users[username] = {"password_sha256": pw_hash}
        _save_users(users)
    else:
        stored = users[username].get("password_sha256") or ""
        if not stored or not _timing_safe_equal(stored, pw_hash):
            return "invalid username/password", 401

    token = secrets.token_urlsafe(32)
    tokens = _load_tokens()
    tokens[token] = {"username": username}
    _save_tokens(tokens)

    return jsonify({"token": token, "username": username})


@app.post("/create/<user>/<repo>")
@require_auth
def create_repo(user, repo):
    # Enforce per-user scope: token user must match path user
    if getattr(request, "svcs_user", None) != user:
        return "forbidden", 403

    path = repo_path(user, repo)
    if os.path.exists(path):
        return "repo already exists", 400
    os.makedirs(path, exist_ok=True)
    ensure_repo_dirs(path)
    return f"repo {user}/{repo} created", 201


@app.post("/push/<user>/<repo>")
@require_auth
def push(user, repo):
    if getattr(request, "svcs_user", None) != user:
        return "forbidden", 403

    path = repo_path(user, repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    data = request.get_json(silent=True) or {}
    objects = data.get("objects", {})
    commits = data.get("commits", {})
    twigs = data.get("twigs", {})

    working_tree = data.get("working_tree", {})
    snapshot_commit = data.get("snapshot_commit")

    # store objects
    for h, b64 in objects.items():
        obj_file = os.path.join(path, "objects", h)
        if not os.path.exists(obj_file):
            try:
                raw = base64.b64decode(b64)
            except Exception:
                return f"invalid base64 object for {h}", 400
            with open(obj_file, "wb") as f:
                f.write(raw)

    # store commits
    for cid, cdata in commits.items():
        commit_file = os.path.join(path, "commits", f"{cid}.json")
        if not os.path.exists(commit_file):
            write_json(commit_file, cdata)

    # update twig HEADs
    for twig, head in twigs.items():
        with open(os.path.join(path, "twigs", twig), "w") as f:
            f.write(head)

    # store snapshot if provided
    if working_tree and snapshot_commit:
        write_json(snapshot_path(path, snapshot_commit), working_tree)

    return "push successful", 200


@app.get("/pull/<user>/<repo>")
@require_auth
def pull(user, repo):
    if getattr(request, "svcs_user", None) != user:
        return "forbidden", 403

    path = repo_path(user, repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    objects = {}
    commits = {}
    twigs = {}

    # encode objects
    obj_dir = os.path.join(path, "objects")
    for fname in os.listdir(obj_dir):
        full = os.path.join(obj_dir, fname)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            objects[fname] = base64.b64encode(f.read()).decode()

    # load commits
    commits_dir = os.path.join(path, "commits")
    for fname in os.listdir(commits_dir):
        if fname.endswith(".json"):
            cid = fname[:-5]
            commits[cid] = read_json(os.path.join(commits_dir, fname))

    # load twigs
    twigs_dir = os.path.join(path, "twigs")
    for fname in os.listdir(twigs_dir):
        full = os.path.join(twigs_dir, fname)
        if not os.path.isfile(full):
            continue
        with open(full) as f:
            twigs[fname] = f.read().strip()

    return jsonify({"objects": objects, "commits": commits, "twigs": twigs})


@app.get("/snapshot/<user>/<repo>/<commit>")
@require_auth
def snapshot(user, repo, commit):
    if getattr(request, "svcs_user", None) != user:
        return "forbidden", 403

    path = repo_path(user, repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    sp = snapshot_path(path, commit)
    if not os.path.exists(sp):
        return "snapshot not found for commit", 404

    return jsonify(read_json(sp))


@app.get("/repos/<user>")
@require_auth
def list_user_repos(user):
    if getattr(request, "svcs_user", None) != user:
        return "forbidden", 403

    user_dir = os.path.join(BASE_DIR, user)
    ensure_user_dir(user)
    return jsonify([name for name in os.listdir(user_dir) if os.path.isdir(os.path.join(user_dir, name))])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)