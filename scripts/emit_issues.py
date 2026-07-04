#!/usr/bin/env python3
"""codebase-auditor: emit_issues.py

Creates task-board issues from analyzer proposals (JSON array).
Deduplicates by title regex against existing open issues.
Caps per-run to avoid flooding (default 5, --max).

Usage: emit_issues.py <proposals.json> [--dry-run] [--max 5] [--board ons96/task-board]

ponytail: stdlib + subprocess(gh) only.
"""
import json, sys, os, argparse, subprocess, re

DEFAULT_BOARD = 'ons96/task-board'
# Vague patterns to reject (per #226 constraints)
VAGUE_RE = re.compile(
    r'\b(add more tests|improve code quality|refactor for readability|'
    r'clean up the code|general improvements|tech debt)\b',
    re.IGNORECASE,
)

def get_existing_titles(board):
    """Fetch existing open issue titles for dedup."""
    try:
        r = subprocess.run(
            ['gh', 'issue', 'list', '--repo', board, '--state', 'open',
             '--limit', '200', '--json', 'number', 'title'],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return set()
        issues = json.loads(r.stdout)
        return {i['title'].lower().strip() for i in issues}
    except Exception:
        return set()

def title_matches_existing(title, existing):
    """Check if a proposal title is too similar to an existing one."""
    t = title.lower().strip()
    # Exact match
    if t in existing:
        return True
    # Fuzzy: >80% word overlap
    tw = set(re.findall(r'\w+', t))
    for ex in existing:
        ew = set(re.findall(r'\w+', ex))
        if tw and ew:
            overlap = len(tw & ew) / len(tw | ew)
            if overlap > 0.80:
                return True
    return False

def create_issue(board, proposal, dry_run=False):
    """Create a single issue via gh CLI. Returns (success, url_or_error)."""
    title = proposal['title']
    priority = proposal.get('priority', 'P3')
    repo = proposal.get('repo', '')
    body = proposal.get('body', '')
    rationale = proposal.get('rationale', '')

    # Build issue body
    sections = []
    sections.append('## Goal')
    sections.append(body)
    sections.append('')
    sections.append('## Context')
    sections.append(f'Auto-filed by codebase-auditor. Rationale: {rationale}')
    if repo:
        sections.append(f'Related repo: `{repo}`')
    sections.append('')
    sections.append('## Acceptance Criteria')
    sections.append('- [ ] Issue resolved with a concrete code/config change')
    sections.append('')
    sections.append('## Constraints')
    sections.append('- Free-tier only')
    sections.append('- Auto-audit issue (priority capped at P3)')
    full_body = '\n'.join(sections)

    labels = [f'priority:{priority}', 'status:new', 'tag:auto-audit']
    if repo:
        labels.append(f'project:{repo}')

    if dry_run:
        return True, f'[DRY-RUN] would create: {title} (labels: {",".join(labels)})'

    label_args = []
    for l in labels:
        label_args.extend(['--label', l])

    try:
        r = subprocess.run(
            ['gh', 'issue', 'create', '--repo', board,
             '--title', title, '--body', full_body] + label_args,
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, f'gh exit {r.returncode}: {r.stderr.strip()[:200]}'
    except Exception as e:
        return False, str(e)

def main():
    ap = argparse.ArgumentParser(description='Emit task-board issues from proposals')
    ap.add_argument('proposals', help='proposals JSON path (from analyze.py)')
    ap.add_argument('--dry-run', action='store_true', help='print what would be created, create nothing')
    ap.add_argument('--max', type=int, default=5, help='max issues to create (default 5)')
    ap.add_argument('--board', default=DEFAULT_BOARD, help='task-board repo (default ons96/task-board)')
    args = ap.parse_args()

    with open(args.proposals) as f:
        proposals = json.load(f)

    if not proposals:
        print('emit_issues: no proposals to create', file=sys.stderr)
        return

    existing = get_existing_titles(args.board) if not args.dry_run else set()
    print(f'emit_issues: {len(existing)} existing open titles loaded for dedup', file=sys.stderr)

    created = 0
    skipped_vague = 0
    skipped_dup = 0
    skipped_cap = 0

    for p in proposals:
        if created >= args.max:
            skipped_cap += 1
            continue

        title = p['title']

        # Reject vague proposals
        if VAGUE_RE.search(title):
            print(f'  SKIP (vague): {title}', file=sys.stderr)
            skipped_vague += 1
            continue

        # Dedup check
        if title_matches_existing(title, existing):
            print(f'  SKIP (dup): {title}', file=sys.stderr)
            skipped_dup += 1
            continue

        ok, result = create_issue(args.board, p, dry_run=args.dry_run)
        if ok:
            created += 1
            existing.add(title.lower().strip())  # prevent intra-run dups
            print(f'  CREATED: {result}', file=sys.stderr)
        else:
            print(f'  FAILED: {result}', file=sys.stderr)

    print(f'emit_issues: {created} created, {skipped_dup} dup, {skipped_vague} vague, {skipped_cap} capped', file=sys.stderr)

if __name__ == '__main__':
    main()
