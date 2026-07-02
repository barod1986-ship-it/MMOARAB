# MMOARAB

Private workspace for the Arabic Ragnarok Online translation based on rAthena.

## Current state

- Last completed stage: 267
- Last completed file: `rathena-master/npc/other/monster_race.txt`
- Next file: `rathena-master/npc/other/msg_boards.txt`
- Reviewed NPC files: 268 / 555
- Completed quest files: 88 / 88
- Cumulative changes: 64,155
- Excluded files: 28

## Repository workflow

- `main` contains the approved working state.
- `translation-project-setup` is used to prepare the Git-based workflow.
- Arabic files are reviewed against `rathena-master/npc_EN/` and the current official rAthena source.
- Internal names, commands, identifiers, maps, coordinates, file encoding, and line endings must be preserved.
- Full ZIP packages and generated Excel workbooks are stored as delivery backups rather than committed to normal Git history.

See `docs/WORKFLOW.md` and `tracking/PROJECT_STATE.json` for the working procedure and current checkpoint.
