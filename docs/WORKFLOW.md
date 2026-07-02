# Translation Review Workflow

## Source of truth

The approved Git branch is the source of truth for reviewed text files. Full ZIP packages remain delivery and recovery backups.

## Stage procedure

1. Read `tracking/PROJECT_STATE.json`.
2. Confirm the next Arabic file and its internal English reference.
3. Compare both files structurally with the current official rAthena source.
4. Review dialogue contextually. Do not use blind replacement.
5. Preserve commands, labels, internal names after `::`, identifiers, maps, coordinates, variables, conditions, encoding, and line endings.
6. Synchronize related item, monster, skill, quest, or navigation files only when required.
7. Run static and structural validation.
8. Commit the reviewed file and update `tracking/PROJECT_STATE.json`.
9. Create a full ZIP delivery periodically or at major checkpoints.

## Commit naming

Use one commit per stage:

`stage-268: review rathena-master/npc/other/msg_boards.txt`

## Files excluded from normal Git history

- Full stage ZIP packages
- Generated Excel trackers
- Historical stage report directories
- Temporary verification output

These files are retained as external delivery backups or release assets.

## Encoding policy

The repository `.gitattributes` file disables automatic text conversion for Ragnarok source files. Do not normalize or rewrite a file solely to change its encoding or line endings.
