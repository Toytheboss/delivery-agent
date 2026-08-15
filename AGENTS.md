# Agent notes

## README feature sync

When adding, changing, or removing a user-visible Delivery Agent capability, update `README.md` **Features** (and Config / Env / Ops tables if needed) in the same change set.

Details: `.cursor/rules/readme-feature-sync.mdc`.

## Local changes → GitHub

Local edits must be **committed and pushed** to GitHub (`origin`), not only deployed to the production server. Prefer: edit → commit → push → deploy. If a hotfix landed on the server first, sync the same files back into this repo and push in the same session.

Details: `.cursor/rules/git-commit-push.mdc`.
