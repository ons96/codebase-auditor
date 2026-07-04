#!/usr/bin/env bash
# codebase-auditor: snapshot.sh
# Walks ~/CodingProjects/*/ capturing per-repo state to a JSON snapshot.
# Output: snapshot JSON to stdout (or --out <file>).
# ponytail: stdlib bash + git/python only, no deps.
set -euo pipefail

ROOT="${CODEBASE_ROOT:-$HOME/CodingProjects}"
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --root) ROOT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: snapshot.sh [--out FILE] [--root DIR]"
      echo "  Captures per-repo state (HEAD, file count, deps, open issues) as JSON."
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

python3 - "$ROOT" "$OUT" << 'PYEOF'
import json, os, subprocess, sys, glob, datetime

root = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None

def run(cmd, cwd=None, timeout=10):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

repos = []
for entry in sorted(os.listdir(root)):
    rdir = os.path.join(root, entry)
    if not os.path.isdir(rdir) or entry.startswith('.'):
        continue
    gdir = os.path.join(rdir, '.git')
    if not os.path.isdir(gdir):
        continue

    head = run(['git', 'rev-parse', 'HEAD'], cwd=rdir)
    branch = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=rdir)
    # file count (tracked, excluding .git)
    fcount = run(['git', 'ls-files'], cwd=rdir)
    file_count = len(fcount.splitlines()) if fcount else 0
    # uncommitted changes
    status = run(['git', 'status', '--porcelain'], cwd=rdir)
    dirty = len(status.splitlines()) if status else 0
    # last commit date
    last_date = run(['git', 'log', '-1', '--format=%ci'], cwd=rdir)

    # detect dep files
    deps = []
    for df in ['package.json', 'requirements.txt', 'pyproject.toml', 'Cargo.toml',
               'go.mod', 'uv.lock', 'package-lock.json', 'Cargo.lock']:
        if os.path.exists(os.path.join(rdir, df)):
            deps.append(df)

    # open issues count via gh (best-effort, skip if no gh/repo)
    owner_repo = None
    remote = run(['git', 'remote', 'get-url', 'origin'], cwd=rdir)
    if remote and 'github.com' in remote:
        parts = remote.replace('.git', '').split('/')
        if len(parts) >= 2:
            owner_repo = f"{parts[-2]}/{parts[-1]}"
    open_issues = None
    if owner_repo:
        n = run(['gh', 'issue', 'list', '--repo', owner_repo, '--state', 'open',
                 '--limit', '1', '--json', 'number'], timeout=15)
        if n and n.strip().startswith('['):
            try:
                open_issues = len(json.loads(n))
            except Exception:
                open_issues = None

    # gitleaks status (best-effort)
    gitleaks = None
    gl = run(['gitleaks', 'detect', '--no-banner', '--config', '/dev/null',
              '--source', rdir, '--report-format', 'json', '--report-path', '/dev/stdout'],
             timeout=30)
    if gl is not None:
        try:
            gitleaks = len(json.loads(gl)) if gl.strip() else 0
        except Exception:
            gitleaks = None

    repos.append({
        'name': entry,
        'path': rdir,
        'head': head,
        'branch': branch,
        'file_count': file_count,
        'uncommitted': dirty,
        'last_commit': last_date,
        'deps': deps,
        'owner_repo': owner_repo,
        'open_issues': open_issues,
        'gitleaks_findings': gitleaks,
    })

snap = {
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'root': root,
    'repo_count': len(repos),
    'repos': repos,
}

text = json.dumps(snap, indent=2)
if out:
    with open(out, 'w') as f:
        f.write(text + '\n')
    print(f"snapshot: {len(repos)} repos -> {out}", file=sys.stderr)
else:
    print(text)
PYEOF
