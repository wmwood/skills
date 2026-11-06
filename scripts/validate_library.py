"""Structural validation for this repository's deliberately small skill dialect."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REQUIRED = {
    'ticket-writer', 'feature-planner', 'feature-orchestrator',
    'feature-implementer', 'independent-code-reviewer', 'feature-validator',
    'pre-pr-quality-gate', 'repository-initializer', 'library-update',
    'feature-workflow',
}
VERSION = '1.1.0'
SCHEMA = 2


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors = []
    skills = root / 'skills'
    actual = {p.parent.name for p in skills.glob('*/SKILL.md')}
    if REQUIRED - actual:
        errors.append('Missing skills: ' + ', '.join(sorted(REQUIRED - actual)))
    for skill in sorted(skills.glob('*/SKILL.md')):
        data = skill.read_text(encoding='utf-8-sig')
        match = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', data, re.S)
        if not match:
            errors.append(f'{skill.relative_to(root)}: missing frontmatter')
            continue
        fields = {}
        for line in match[1].splitlines():
            if ':' in line and not line.startswith(' '):
                key, value = line.split(':', 1)
                fields[key] = value.strip().strip('"\'')
        name = fields.get('name', '')
        if name != skill.parent.name or not re.fullmatch('[a-z0-9-]{1,63}', name):
            errors.append(f'{skill}: invalid or mismatched name')
        if not fields.get('description'):
            errors.append(f'{skill}: missing description')
        body = data[match.end():].lower()
        for required in ('activation', 'inputs', 'authority', 'procedure', 'outputs', 'completion', 'failure', 'recovery'):
            if required not in body:
                errors.append(f'{skill}: missing interface concept {required}')
        if 'references/contracts.md' not in data:
            errors.append(f'{skill}: missing shared contract link')
    for path in sorted(root.rglob('*.md')):
        relative = path.relative_to(root)
        if any(part.startswith('.') for part in relative.parts) or relative.parts[0] in ('tmp', 'outputs', 'scratch'):
            continue
        data = path.read_text(encoding='utf-8-sig')
        if path.name != 'SKILL.md.template' and re.search(r'REPLACE:|replace-with-skill-name|\bTODO\b|\bTBD\b', data):
            errors.append(f'{path.relative_to(root)}: unfinished placeholder')
        # This is structural coverage, not a shell parser. Execution evidence
        # and equivalent failure handling remain part of release review.
        fences = re.findall(r'^```([a-zA-Z0-9+-]*)\s*\n(.*?)^```', data, re.M | re.S)
        shell_fences = {language.lower() for language, _ in fences
                        if language.lower() in ('powershell', 'bash', 'sh', 'shell', 'console')}
        paired = 'powershell' in shell_fences and 'bash' in shell_fences
        shared = '**PowerShell and Bash**' in data
        commands = any(re.search(r'^\s*(?:python|git|gh|rtk|mkdir|cp)\s', content, re.M)
                       for language, content in fences if language.lower() != 'json')
        if (shell_fences or commands) and not (paired or shared):
            errors.append(f'{path.relative_to(root)}: shell examples need paired powershell/bash blocks or shared PowerShell and Bash label')
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', data):
            target = target.split('#', 1)[0].strip('<>')
            if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                continue
            if not (path.parent / target).exists():
                errors.append(f'{path.relative_to(root)}: broken link {target}')
    policy = skills / 'library-update' / 'agents' / 'openai.yaml'
    if not policy.exists() or 'allow_implicit_invocation: false' not in policy.read_text(encoding='utf-8'):
        errors.append('library-update must be explicit-only')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root)
    for error in errors:
        print(error)
    print(f'Library validation: {len(errors)} error(s)')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
