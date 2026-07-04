#!/usr/bin/env python3
"""codebase-auditor: diff.py

Compares two snapshot JSON files, emits a structured diff of changes.
Usage: diff.py <old.json> <new.json> [--out file]
Output: JSON with per-repo {added, removed, changed} + summary.

ponytail: stdlib only, no external deps.
"""
import json, sys, argparse, datetime

def load(path):
    with open(path) as f:
        return json.load(f)

def diff_snapshots(old, new):
    old_repos = {r['name']: r for r in old.get('repos', [])}
    new_repos = {r['name']: r for r in new.get('repos', [])}

    changes = []
    for name in sorted(set(old_repos) | set(new_repos)):
        o = old_repos.get(name)
        n = new_repos.get(name)

        if o and not n:
            changes.append({'name': name, 'action': 'removed', 'old': o})
            continue
        if n and not o:
            changes.append({'name': name, 'action': 'added', 'new': n})
            continue

        # both exist - compare fields
        diffs = {}
        for key in ['head', 'branch', 'file_count', 'uncommitted', 'last_commit',
                     'deps', 'open_issues', 'gitleaks_findings']:
            ov = o.get(key)
            nv = n.get(key)
            if ov != nv:
                diffs[key] = {'old': ov, 'new': nv}
        if diffs:
            changes.append({'name': name, 'action': 'changed', 'diff': diffs})

    return {
        'old_timestamp': old.get('timestamp'),
        'new_timestamp': new.get('timestamp'),
        'summary': {
            'added': sum(1 for c in changes if c['action'] == 'added'),
            'removed': sum(1 for c in changes if c['action'] == 'removed'),
            'changed': sum(1 for c in changes if c['action'] == 'changed'),
        },
        'changes': changes,
    }

def main():
    ap = argparse.ArgumentParser(description='Diff two codebase snapshots')
    ap.add_argument('old', help='old snapshot JSON path')
    ap.add_argument('new', help='new snapshot JSON path')
    ap.add_argument('--out', help='write diff to file (default: stdout)')
    args = ap.parse_args()

    old = load(args.old)
    new = load(args.new)
    result = diff_snapshots(old, new)
    text = json.dumps(result, indent=2)

    if args.out:
        with open(args.out, 'w') as f:
            f.write(text + '\n')
        print(f"diff: {result['summary']} -> {args.out}", file=sys.stderr)
    else:
        print(text)

if __name__ == '__main__':
    main()
