# Repository workflow

- After completing any file changes in this project, commit all relevant non-ignored changes and push the resulting commit to `origin/main` (`https://github.com/TraderKei/UST_Auction.git`).
- Do not commit secrets, local environment files, dependency directories, build outputs, caches, or other files excluded by `.gitignore`.
- Preserve unrelated user changes and include them only when the user explicitly asks to commit all current project changes.
- Before reporting completion, verify that the local branch is clean and that its commit matches `origin/main`.

## Default Work Style
- Natural-language requests should be translated into executable tasks without requiring a separate detailed prompt.
- Before editing, inspect relevant code, tests, docs, and existing implementation; do not redo completed work.
- Prefer minimal, targeted changes; avoid unrelated refactors or interface/schema changes unless required.
- Resolve minor ambiguity from existing project conventions instead of blocking on clarification.
- For non-trivial work, form a brief internal plan before editing.
- Validate changes with relevant tests and, when practical, a build/typecheck/lint.
- Fix root causes rather than applying fragile workarounds.
- Update project/progress docs only when the change materially affects them.
- Completion means implementation + validation, not code changes alone.
- Final report should summarize: changes, key files, important decisions, validation results, and remaining issues.
