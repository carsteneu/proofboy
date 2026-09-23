"""Stack detection: what a repository looks like, as a suggestion.

A repository announces its stack through marker files at its root
(``composer.json``, ``package.json``, ``go.mod``, ...). :func:`detect` reads
their *names* (a regular file; a symlink on an existing file counts under
its name, but neither contents nor the link target are read, and git is
never consulted) --
and derives which runners and lint commands a report for this project
plausibly names, so a user can see what the verifier would accept before
writing the claim.

This is a suggestion layer, not a gate: it changes no verdict, runs nothing,
writes nothing. ``python3 -m bemyself check --detect --repo <path>`` prints
the result; combined with a report the same result rides along in the output
while the claims and the exit code stay exactly what they were (the
differential test pins that). A detection is a hint about what to allow with
``--allow``/``--project-config`` -- the allowlist still decides what runs.
"""

from __future__ import annotations

import os

# A marker file and what its presence suggests. The suggestions are command
# prefixes, in the spelling of the allowlist.
_MARKERS = (
    ("composer.json", "php", ("vendor/bin/phpunit", "composer test")),
    ("phpunit.xml", "php", ("vendor/bin/phpunit",)),
    ("phpunit.xml.dist", "php", ("vendor/bin/phpunit",)),
    ("package.json", "node", ("npm test",)),
    ("go.mod", "go", ("go test",)),
    ("Cargo.toml", "rust", ("cargo test",)),
    ("pyproject.toml", "python", ("python3 -m pytest",)),
    ("setup.py", "python", ("python3 -m pytest",)),
    ("pytest.ini", "python", ("python3 -m pytest",)),
    ("tox.ini", "python", ("python3 -m pytest",)),
    ("Makefile", "make", ("make test", "make check")),
)

# Lint suggestions per stack: only commands the [LINT] type knows.
_LINT_SUGGESTIONS = {
    "php": (
        "php -l",
        "bin/console lint:twig",
        "bin/console lint:yaml",
        "bin/console lint:container",
        "composer validate",
    ),
}


class Detection:
    """The detected stacks and the command suggestions for them."""

    __slots__ = ("stacks", "files", "commands", "lint_commands")

    def __init__(self, stacks, files, commands, lint_commands):
        self.stacks = stacks
        self.files = files
        self.commands = commands
        self.lint_commands = lint_commands


def detect(repo_path):
    """Detect the stacks of ``repo_path`` from its root marker files.

    Only the presence of regular files with those names is checked
    (``os.path.isfile``, a metadata lookup): the contents are never read, so
    a hostile manifest can at most be counted as present -- it cannot
    influence anything else. The result is sorted and deduplicated.
    """
    seen_stacks = []
    seen_files = []
    commands = []
    lint_commands = []
    for name, stack, suggestions in _MARKERS:
        if not os.path.isfile(os.path.join(repo_path, name)):
            continue
        seen_files.append(name)
        if stack not in seen_stacks:
            seen_stacks.append(stack)
        for command in suggestions:
            if command not in commands:
                commands.append(command)
    for stack in seen_stacks:
        for command in _LINT_SUGGESTIONS.get(stack, ()):
            if command not in lint_commands:
                lint_commands.append(command)
    return Detection(
        tuple(seen_stacks), tuple(seen_files), tuple(commands), tuple(lint_commands)
    )


def render(detection):
    """A human-readable suggestion block; empty when nothing was detected."""
    if not detection.stacks:
        return "detected stacks: none (no known marker file at the repository root)"
    lines = [
        "detected stacks: " + ", ".join(detection.stacks)
        + " (" + ", ".join(detection.files) + ")"
    ]
    if detection.commands:
        lines.append("suggested test commands: " + ", ".join(detection.commands))
    if detection.lint_commands:
        lines.append("suggested [LINT] commands: " + ", ".join(detection.lint_commands))
    lines.append(
        "these are suggestions, not a verdict: allowlist them with --allow "
        "or the project config; the check itself stays untouched"
    )
    return "\n".join(lines)
