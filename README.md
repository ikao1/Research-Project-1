# Research Project 1

A version-controlled research workspace. Everything lives inside this folder: documents, notes, code, and an automatic record of commits and commands.

## Proposal

See [`docs/proposal.md`](docs/proposal.md) for the project scope: *Look Decomposer*, an After Effects re-compositing tool.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/` | Research notes, papers, write-ups |
| `ae_mcp/` | MCP bridge that drives a live After Effects session (see [`ae_mcp/README.md`](ae_mcp/README.md)) |
| `logs/commits.log` | Auto-generated log of every commit (via git hook) |
| `logs/commands.log` | Log of commands you record with the helper script |
| `scripts/log-command.sh` | Record a command you ran |
| `scripts/hooks/post-commit` | Git hook that logs each commit |
| `scripts/setup.sh` | Installs the git hooks into `.git/hooks` |

## After Effects bridge

`ae_mcp/` connects a live After Effects session to opencode over MCP. Install the
AE-side startup script, then restart After Effects and opencode:

```sh
python3 ae_mcp/install.py
```

Tools: `aftereffects_status`, `aftereffects_run`, `aftereffects_project_info`,
`aftereffects_list_comps`, `aftereffects_create_comp`, `aftereffects_save_project`,
`aftereffects_import_footage`, `aftereffects_export_frame`. See
[`ae_mcp/README.md`](ae_mcp/README.md) for the protocol, examples, and
troubleshooting.

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
