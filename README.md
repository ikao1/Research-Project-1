# Research Project 1

A version-controlled research workspace. Everything lives inside this folder: documents, notes, code, and an automatic record of commits and commands.

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

Every commit is automatically appended to `logs/commits.log`.

To record a command you ran:

```sh
./scripts/log-command.sh "python experiment.py --seed 42"
```

## Connect to GitHub

This folder is already a local git repo on branch `main`, and `gh` is authenticated as **ikao1**.

When you are ready to create the remote repo:

```sh
gh repo create "Research Project 1" --private --source=. --remote=origin --push
```

Use `--public` instead of `--private` if you want it public. After that, normal `git push` works.
