# Personal AI Skills

A version-controlled home for reusable AI skills: focused instructions and supporting resources for tasks you repeat.

## Structure

```text
skills/
  <skill-name>/
    SKILL.md              # Required: metadata and instructions
    references/           # Optional: documentation loaded as needed
    scripts/              # Optional: executable helpers
    assets/               # Optional: templates and output resources
    agents/               # Optional: agent-specific metadata
templates/
  SKILL.md.template       # Starter for a new skill
AGENTS.md                 # Guidance for agents working in this repository
```

Keep each skill in its own folder. Add optional folders only when they have a purpose. Use lowercase, hyphenated names such as `meeting-notes` or `review-sql`; match the folder name to the frontmatter `name`.

## Available skills

- [feature-planner](skills/feature-planner/SKILL.md): Interview through design decisions, confirm shared understanding, and produce an implementation plan for review.
- [ticket-writer](skills/ticket-writer/SKILL.md): Interview through the intended change, check affected projects and potential conflicts, and produce confirmed ticket bullets for a coworker.

Both skills require Plan mode. `ticket-writer` reuses the `feature-planner` interview and ends with ticket content in chat.

## Add a skill

Run one of the following examples from this repository's root. Both create a new skill folder and copy the template; if the folder already exists, they stop without overwriting its contents.

**Windows PowerShell 5.1 or later**

```powershell
& {
    $skillName = 'meeting-notes'
    $skillPath = Join-Path 'skills' "$skillName"
    New-Item -ItemType Directory -Path "$skillPath" -ErrorAction Stop
    Copy-Item -LiteralPath 'templates/SKILL.md.template' -Destination (Join-Path "$skillPath" 'SKILL.md') -ErrorAction Stop
}
```

**Linux Bash**

```bash
skill_name='meeting-notes'
skill_path="skills/$skill_name"
mkdir -- "$skill_path" &&
    cp -- 'templates/SKILL.md.template' "$skill_path/SKILL.md"
```

Edit the new `SKILL.md`:

1. Replace the name and description. Explain what the skill does and when to use it.
2. Replace the starter instructions with your actual workflow and preferences.
3. Add supporting files only as needed, linking to them with relative paths.
4. Try the skill on a representative request and adjust it based on the result.
5. Review the diff and commit the finished skill.

The template uses a `.template` suffix so it is distinct from finished skills.

## Writing useful skills

Keep instructions focused on decisions, context, and preferences the agent would not otherwise know. Describe the expected outcome and meaningful checks. Avoid repeating general AI advice or turning a single example into a universal rule.

Keep the main instructions in `SKILL.md`. Move lengthy, conditional material into `references/` and explain when to read it. Keep resources portable: prefer relative paths and document any required tools or environment variables without storing their secret values.

Whenever documentation includes shell commands, provide labeled Windows PowerShell 5.1 and Linux Bash equivalents. Identical commands may share a block labeled **PowerShell and Bash**. Quote paths, state the working directory and prerequisites, and identify platform-specific limitations with an alternative where available.

## Use your skills

This repository stores the source files. To make a skill available in an AI tool, follow that tool's discovery or installation rules and point it to, link, or copy the **whole skill folder**, including supporting files. Discovery paths and supported metadata vary by tool; storing files here alone does not install them globally.

Make ongoing edits here so this repository stays the source of truth. If you use copies, refresh them after changes.

The [ticket-writer](skills/ticket-writer/SKILL.md) skill depends on [feature-planner](skills/feature-planner/SKILL.md). When installing `ticket-writer`, copy both skill folders into the same skills directory so the relative dependency link resolves.

### Copy a skill into your user-wide directory

For Codex, the user-wide directory is `~/.agents/skills`, and a project's directory is `<project>/.agents/skills`. These locations follow the [official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills). Other AI tools may use different locations.

Run the examples from **this repository's root**. Change `feature-planner` to the name of the skill you want to copy. Each example copies the entire folder, including supporting resources and hidden files, and stops if the destination skill folder already exists. No administrator privileges or extra packages are required: use Windows PowerShell 5.1+ or Linux Bash with standard `mkdir` and `cp` utilities.

**Windows PowerShell 5.1 or later**

```powershell
& {
    $skillName = 'feature-planner'
    $source = Join-Path 'skills' "$skillName"
    $skillsRoot = Join-Path "$HOME" '.agents/skills'
    $destination = Join-Path "$skillsRoot" "$skillName"
    if (-not (Test-Path -LiteralPath (Join-Path "$source" 'SKILL.md') -PathType Leaf)) {
        throw "Skill not found: $source"
    }
    New-Item -ItemType Directory -Path "$skillsRoot" -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path "$destination" -ErrorAction Stop | Out-Null
    Get-ChildItem -LiteralPath "$source" -Force -ErrorAction Stop |
        Copy-Item -Destination "$destination" -Recurse -Force -ErrorAction Stop
}
```

**Linux Bash**

```bash
(
    skill_name='feature-planner'
    source="skills/$skill_name"
    skills_root="$HOME/.agents/skills"
    destination="$skills_root/$skill_name"
    if [ ! -f "$source/SKILL.md" ]; then
        printf 'Skill not found: %s\n' "$source" >&2
        exit 1
    fi
    mkdir -p -- "$skills_root" &&
        mkdir -- "$destination" &&
        cp -R -- "$source/." "$destination/"
)
```

### Copy a skill into a specific project

Stay in **this repository's root** and replace the example project path with an existing project's root directory. These examples put the skill in that project's `.agents/skills` directory instead of your user-wide directory.

**Windows PowerShell 5.1 or later**

```powershell
& {
    $skillName = 'feature-planner'
    $projectRoot = 'C:\Projects\My Project'
    $source = Join-Path 'skills' "$skillName"
    if (-not (Test-Path -LiteralPath "$projectRoot" -PathType Container)) {
        throw "Project directory not found: $projectRoot"
    }
    if (-not (Test-Path -LiteralPath (Join-Path "$source" 'SKILL.md') -PathType Leaf)) {
        throw "Skill not found: $source"
    }
    $skillsRoot = Join-Path "$projectRoot" '.agents/skills'
    $destination = Join-Path "$skillsRoot" "$skillName"
    New-Item -ItemType Directory -Path "$skillsRoot" -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path "$destination" -ErrorAction Stop | Out-Null
    Get-ChildItem -LiteralPath "$source" -Force -ErrorAction Stop |
        Copy-Item -Destination "$destination" -Recurse -Force -ErrorAction Stop
}
```

**Linux Bash**

```bash
(
    skill_name='feature-planner'
    project_root='/path/to/My Project'
    source="skills/$skill_name"
    if [ ! -d "$project_root" ]; then
        printf 'Project directory not found: %s\n' "$project_root" >&2
        exit 1
    fi
    if [ ! -f "$source/SKILL.md" ]; then
        printf 'Skill not found: %s\n' "$source" >&2
        exit 1
    fi
    skills_root="$project_root/.agents/skills"
    destination="$skills_root/$skill_name"
    mkdir -p -- "$skills_root" &&
        mkdir -- "$destination" &&
        cp -R -- "$source/." "$destination/"
)
```

Repeat with another skill name to install more skills. Copies are snapshots, so later edits here do not automatically update them. To replace an installed copy, first review or back up any local edits and move the existing destination skill folder aside, then rerun the appropriate example. A failed copy may leave a partial destination folder; inspect and move it aside before retrying as well.

Codex detects installed skills automatically; restart Codex if a skill does not appear. For project skills, open or run Codex inside the target project. See the [official discovery guidance](https://learn.chatgpt.com/docs/build-skills).

## Repository hygiene

Commit reusable instructions and intentional assets. Keep credentials, private task inputs, generated outputs, and local environments out of version control. `.gitignore` covers common local files but cannot identify every sensitive file; review staged changes before committing.
