# Research Project 1

A version-controlled research workspace. Everything lives inside this folder: documents, notes, code, and an automatic record of commits and commands.

## Proposal

See [`docs/proposal.md`](docs/proposal.md) for the project scope: *Look Decomposer*, an After Effects re-compositing tool.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/` | Research notes, papers, write-ups |
| `logs/commits.log` | Auto-generated log of every commit (via git hook) |
| `logs/commands.log` | Log of commands you record with the helper script |
| `scripts/log-command.sh` | Record a command you ran |
| `scripts/hooks/post-commit` | Git hook that logs each commit |
| `scripts/setup.sh` | Installs the git hooks into `.git/hooks` |

## Daily use

Commit changes as usual:

```sh
git add -A
git commit -m "describe what changed"
```

Every commit is automatically appended to `logs/commits.log` and included in that commit, so `git status` stays clean.

To record a command you ran:

```sh
./scripts/log-command.sh "python experiment.py --seed 42"
```

Then commit as usual to store it.

## GitHub

Remote: https://github.com/ikao1/Research-Project-1 (public).

Push changes with:

```sh
git push
```
