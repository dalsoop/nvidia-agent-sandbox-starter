---
name: workspace-report
description: Write a short Markdown inventory of the files in the workspace to report.md. Use when asked to report on, inventory, or summarize what is in the workspace.
---
# Workspace report

1. Call `list_files` with path `.`.
2. Read at most five small text files with `read_file`. Skip anything larger than 16 KB or not UTF-8 text.
3. Call `write_file` for `report.md` with these sections:
   - `## Files`: one bullet per file with its size.
   - `## Notes`: one line per file you read, describing only what the file actually contains.
4. Reply with the path of the report and one sentence summarizing it.

Rules:
- Never describe a file you did not read. Write "not read" instead.
- Do not overwrite any file other than `report.md`.
