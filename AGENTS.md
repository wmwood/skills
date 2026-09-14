# Working in this repository

This repository is the source of truth for the owner's personal AI skills.

## Shell commands

Prefer `rtk` when running external commands to reduce output. Prefix each external command separately in a chain. In both PowerShell and Bash, use `rtk proxy <cmd>` when raw output is needed but usage should still be tracked. Run shell built-ins and PowerShell cmdlets directly; they are not standalone executables that `rtk` can invoke.

All READMEs, skill instructions, references, and templates containing shell commands must support Windows PowerShell 5.1 and Linux Bash:

- Provide clearly labeled `powershell` and `bash` blocks for shell-specific syntax. Identical commands may share one block labeled **PowerShell and Bash**.
- Quote paths and document the working directory and required tools. Do not use PowerShell 7-only syntax in PowerShell examples.
- Preserve equivalent behavior, including failure handling. Creation examples must stop when the destination already exists without overwriting its contents.
- State limitations for platform-specific operations and provide an alternative where available; do not invent unsupported equivalents.

## Skill conventions

- Store each skill in `skills/<skill-name>/SKILL.md`.
- Use lowercase letters, digits, and hyphens for skill names, under 64 characters. Match the folder name and frontmatter `name`.
- Include YAML frontmatter with `name` and a concise `description` describing the capability and when it applies.
- Start new skills from `templates/SKILL.md.template` and replace all starter content before treating them as finished.
- Keep instructions focused on the owner's workflow. Preserve the requested scope and existing authorization boundaries.
- Add `references/`, `scripts/`, `assets/`, or agent-specific metadata only when needed. Link supporting resources from the instructions using relative paths.
- Keep application-specific installation details separate from otherwise portable instructions.
- Do not install or synchronize skills outside this repository unless requested.

## Verification

For skill edits, check frontmatter, relative links, unfinished placeholders, and command coverage for both shells. Verify changed command examples in available shells with safe temporary inputs, including paths with spaces and existing destinations where relevant. Report any platform receiving only static review. Try representative requests when behavioral validation would help. Run any new or modified helper scripts with safe sample inputs before delivering them. Do not add a test framework for prose-only changes.

Do not commit secrets, private task data, or generated output. Preserve unrelated work already in the repository.
