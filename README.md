# codebase-auditor

Self-improving codebase auditor: weekly snapshots of `~/CodingProjects/*/` -> LLM diff analysis -> auto-file improvement issues to the task board.

## How it works

1. **snapshot.sh** walks all git repos under `~/CodingProjects/`, capturing per-repo state (HEAD, branch, file count, uncommitted changes, deps, open issues, gitleaks findings) as JSON.
2. **diff.py** compares two snapshots, producing a structured diff.
3. **analyze.py** sends the diff to `vps-gateway/coding-fast` and asks for 3-5 concrete improvement issue proposals.
4. **emit_issues.py** creates issues on `ons96/task-board`, deduplicating against existing open issues and rejecting vague proposals.

Runs weekly via GitHub Actions (manual dispatch also available).

## Quickstart

```bash
# 1. Snapshot
./scripts/snapshot.sh --out /tmp/snap-new.json

# 2. Diff against last snapshot
python3 scripts/diff.py /tmp/snap-old.json /tmp/snap-new.json --out /tmp/diff.json

# 3. Analyze (needs gateway env vars)
export GATEWAY_URL=http://localhost:8000/v1
export VPS_GATEWAY_API_KEY=...
python3 scripts/analyze.py /tmp/diff.json --out /tmp/proposals.json --max 5

# 4. Emit issues (dry-run first)
python3 scripts/emit_issues.py /tmp/proposals.json --dry-run
python3 scripts/emit_issues.py /tmp/proposals.json --max 3
```

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `CODEBASE_ROOT` | `$HOME/CodingProjects` | Root dir to scan for repos |
| `GATEWAY_URL` | `http://localhost:8000/v1` | VPS gateway endpoint |
| `VPS_GATEWAY_API_KEY` | (required) | Gateway auth key |
| `AUDITOR_MODEL` | `coding-fast` | Gateway virtual model for analysis |

## Drip-not-flood guards

- Max 5 issues per run (`--max`, default 5, GH Action uses 3)
- Priority capped at P3 (never P0/P1/P2 from auto-audit)
- Vague title patterns rejected ("add more tests", "improve code quality", etc.)
- Dedup by title fuzzy match (>80% word overlap = skip)
- Labels: `status:new`, `priority:P3`, `tag:auto-audit`, `project:<repo>`

## Dependencies

- `bash`, `git`, `python3` (stdlib only, no pip packages)
- `gh` CLI (authenticated) for issue creation
- `gitleaks` (optional, best-effort - snapshot continues if absent)
- VPS gateway access (localhost:8000 tunnel or direct)

## Files

```
scripts/
  snapshot.sh    - capture repo states as JSON
  diff.py        - compare two snapshots
  analyze.py     - LLM proposes improvement issues
  emit_issues.py - create issues on task board (dedup + cap)
.github/workflows/
  audit.yml      - weekly cron + manual dispatch
```

## License

MIT
