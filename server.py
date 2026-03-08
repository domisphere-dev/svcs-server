from flask import Flask, request, jsonify
import os
import json
import base64

app = Flask(__name__)
BASE_DIR = "repos"
os.makedirs(BASE_DIR, exist_ok=True)

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)

def repo_path(name):
    return os.path.join(BASE_DIR, name)

def ensure_repo_dirs(path):
    os.makedirs(os.path.join(path, "objects"), exist_ok=True)
    os.makedirs(os.path.join(path, "commits"), exist_ok=True)
    os.makedirs(os.path.join(path, "branches"), exist_ok=True)
    os.makedirs(os.path.join(path, "snapshots"), exist_ok=True)  # NEW: commit snapshots
    head = os.path.join(path, "HEAD")
    if not os.path.exists(head):
        with open(head, "w") as f:
            f.write("main")

def snapshot_path(repo_dir, commit_id):
    return os.path.join(repo_dir, "snapshots", f"{commit_id}.json")

@app.get("/health")
def health():
    return jsonify(
        ok=True,
        routes=[
            "POST /create/<repo>",
            "POST /push/<repo>",
            "GET  /pull/<repo>",
            "GET  /snapshot/<repo>/<commit>",
            "GET  /repos",
            "GET  /health",
        ],
    )

@app.route("/create/<repo>", methods=["POST"])
def create_repo(repo):
    path = repo_path(repo)
    if os.path.exists(path):
        return "repo already exists", 400
    os.makedirs(path, exist_ok=True)
    ensure_repo_dirs(path)
    return f"repo {repo} created", 201

@app.route("/push/<repo>", methods=["POST"])
def push(repo):
    path = repo_path(repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    data = request.get_json(silent=True) or {}
    objects = data.get("objects", {})
    commits = data.get("commits", {})
    branches = data.get("branches", {})

    # NEW: working tree snapshot (path -> base64 file content)
    working_tree = data.get("working_tree", {})
    # commit id to associate snapshot with (client sends it explicitly)
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

    # update branch HEADs
    for branch, head in branches.items():
        with open(os.path.join(path, "branches", branch), "w") as f:
            f.write(head)

    # store snapshot if provided
    if working_tree and snapshot_commit:
        # keep only JSON-safe values; already base64 strings
        write_json(snapshot_path(path, snapshot_commit), working_tree)

    return "push successful", 200

@app.route("/pull/<repo>", methods=["GET"])
def pull(repo):
    # Pull returns ONLY .svcs DB portion (objects/commits/branches)
    path = repo_path(repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    objects = {}
    commits = {}
    branches = {}

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

    # load branches
    branches_dir = os.path.join(path, "branches")
    for fname in os.listdir(branches_dir):
        full = os.path.join(branches_dir, fname)
        if not os.path.isfile(full):
            continue
        with open(full) as f:
            branches[fname] = f.read().strip()

    return jsonify({"objects": objects, "commits": commits, "branches": branches})

@app.route("/snapshot/<repo>/<commit>", methods=["GET"])
def snapshot(repo, commit):
    # For clone: download full working tree for a commit.
    path = repo_path(repo)
    if not os.path.exists(path):
        return "repo not found", 404

    ensure_repo_dirs(path)

    sp = snapshot_path(path, commit)
    if not os.path.exists(sp):
        return "snapshot not found for commit", 404

    return jsonify(read_json(sp))

@app.route("/repos", methods=["GET"])
def list_repos():
    return jsonify([name for name in os.listdir(BASE_DIR) if os.path.isdir(repo_path(name))])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)