---
name: external tools and cache directory
description: All external tools, npm cache, pip cache, and global installs go to D:\11_Agent\Setting, never C drive
type: project
---

All external tools, package caches, and global installations for this project MUST be stored in `D:\11_Agent\Setting`, not on the C drive.

**npm config:**
- cache: `D:\11_Agent\Setting\npm-cache`
- global prefix: `D:\11_Agent\Setting\npm-global`

**pip config:**
- cache-dir: `D:\11_Agent\Setting\pip-cache`

**Why:** User's instruction — avoid consuming C drive space.
**How to apply:** Before any `npm install -g`, `pip install`, or tool installation, ensure the path points to D:\11_Agent\Setting.
