#!/usr/bin/env python3
"""codebase-auditor: analyze.py

Takes a diff JSON (from diff.py) and asks vps-gateway/coding-fast to propose
3-5 improvement issues. Outputs JSON array of issue proposals.

Usage: analyze.py <diff.json> [--out file] [--max 5]

ponytail: stdlib urllib + json only, no openai SDK dependency.
"""
import json, sys, os, argparse, urllib.request, urllib.error

GATEWAY_URL = os.environ.get('GATEWAY_URL', 'http://localhost:8000/v1')
GATEWAY_KEY = os.environ.get('VPS_GATEWAY_API_KEY', os.environ.get('GATEWAY_API_KEY', ''))
MODEL = os.environ.get('AUDITOR_MODEL', 'coding-fast')

SYSTEM = """You are a codebase auditor. Given a diff of repository states (HEAD moves, file count changes, dependency additions, open issue counts, gitleaks findings), propose 3-5 concrete improvement issues for the task board.

Rules:
- Be SPECIFIC: reference the repo name, the changed metric, and a concrete action.
- NEVER propose vague issues like "add more tests" or "improve code quality" without a specific failure or gap.
- If gitleaks_findings > 0, ALWAYS propose a security fix issue.
- If a repo has many uncommitted changes, propose a "commit and clean working tree" issue.
- If file_count dropped significantly, propose a "verify no needed files were deleted" issue.
- If a new dep was added, propose a "scan new dependency <name> for security/license" issue.
- If open_issues grew, propose a "triage open issues in <repo>" issue.

Output STRICT JSON (no markdown, no prose): an array of objects, each with:
  {"title": "...", "body": "...", "repo": "<repo-name>", "priority": "P3", "rationale": "..."}
Title <= 80 chars. Priority must be P3 or P4 (never P0/P1/P2 from auto-audit)."""

def analyze(diff_path, max_proposals=5):
    with open(diff_path) as f:
        diff = json.load(f)

    # Trim to changed repos only to save tokens
    changed = [c for c in diff.get('changes', []) if c['action'] in ('changed', 'added')]
    if not changed:
        return []

    # Cap context: only send summary + diffs, not full repo objects
    payload_changes = []
    for c in changed[:20]:  # cap at 20 repos
        entry = {'name': c['name'], 'action': c['action']}
        if 'diff' in c:
            entry['diff'] = c['diff']
        if 'new' in c:
            entry['new'] = {k: v for k, v in c['new'].items()
                            if k in ('head', 'file_count', 'uncommitted', 'deps', 'open_issues', 'gitleaks_findings')}
        payload_changes.append(entry)

    user_msg = json.dumps({
        'old_timestamp': diff.get('old_timestamp'),
        'new_timestamp': diff.get('new_timestamp'),
        'summary': diff.get('summary'),
        'changes': payload_changes,
    }, indent=2)

    body = json.dumps({
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': f'Analyze this codebase diff and propose up to {max_proposals} issues:\n\n{user_msg}'},
        ],
        'max_tokens': 2000,
        'temperature': 0.3,
    }).encode()

    req = urllib.request.Request(
        f'{GATEWAY_URL}/chat/completions',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {GATEWAY_KEY}',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode() if e.fp else str(e)
        print(f'analyze: gateway HTTP {e.code}: {err[:200]}', file=sys.stderr)
        return []
    except Exception as e:
        print(f'analyze: gateway error: {e}', file=sys.stderr)
        return []

    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    # Extract JSON array from response (handle markdown fences)
    content = content.strip()
    if content.startswith('```'):
        lines = content.split('\n')
        content = '\n'.join(lines[1:-1] if lines[-1].startswith('```') else lines[1:])

    try:
        proposals = json.loads(content)
    except json.JSONDecodeError:
        # Try to find array bounds
        start = content.find('[')
        end = content.rfind(']')
        if start >= 0 and end > start:
            try:
                proposals = json.loads(content[start:end+1])
            except json.JSONDecodeError:
                print(f'analyze: could not parse LLM response as JSON', file=sys.stderr)
                return []
        else:
            print(f'analyze: no JSON array in LLM response', file=sys.stderr)
            return []

    # Validate + sanitize proposals
    valid = []
    for p in proposals[:max_proposals]:
        title = str(p.get('title', '')).strip()[:80]
        if not title:
            continue
        priority = str(p.get('priority', 'P3')).upper()
        if priority not in ('P3', 'P4'):
            priority = 'P3'  # never allow P0/P1/P2 from auto-audit
        valid.append({
            'title': title,
            'body': str(p.get('body', ''))[:2000],
            'repo': str(p.get('repo', ''))[:100],
            'priority': priority,
            'rationale': str(p.get('rationale', ''))[:500],
        })
    return valid

def main():
    ap = argparse.ArgumentParser(description='Analyze codebase diff via LLM')
    ap.add_argument('diff', help='diff JSON path (from diff.py)')
    ap.add_argument('--out', help='write proposals to file (default: stdout)')
    ap.add_argument('--max', type=int, default=5, help='max proposals (default 5)')
    args = ap.parse_args()

    proposals = analyze(args.diff, args.max)
    text = json.dumps(proposals, indent=2)
    if args.out:
        with open(args.out, 'w') as f:
            f.write(text + '\n')
        print(f'analyze: {len(proposals)} proposals -> {args.out}', file=sys.stderr)
    else:
        print(text)

if __name__ == '__main__':
    main()
