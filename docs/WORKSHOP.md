# Skill workshop and co-work

Open Settings → Skill workshop. Create or paste an instruction skill as JSON, then choose Install locally or Publish to workshop. An instruction skill contains an id, name, description, engine and instructions. It is not executable code. Installed skills are included in the shared provider startup/refresh instructions, and can be removed from the same panel. The catalogue is also available through `ms_list_skills` and `ms_get_skill`.

The built-in library is local to your bridge. For a shared community, run the included `runtime/workshop_server.py` on a host you control and put it behind an HTTPS reverse proxy. It exposes only `/workshop` for list, publish and review. It does not expose your game-engine bridge or local workspaces.

1. Generate a distinct unpredictable token for each user, for example with Python's `secrets.token_urlsafe(32)`.
2. Set `MS_WORKSHOP_USERS` to a JSON object mapping those tokens to stable user IDs. User IDs use letters, digits, colons, underscores or hyphens, 3–120 characters. Store tokens outside source control.
3. Set `MS_STUDIO_DATA_DIR` to a persistent writable directory for the service. Optionally set `MS_WORKSHOP_HOST` and `MS_WORKSHOP_PORT`; defaults are `127.0.0.1:8766`.
4. Run `python runtime/workshop_server.py`, configure your reverse proxy for HTTPS, and give each participant their own token.
5. In the extension's workshop connection panel, enter the HTTPS server URL and your individual token. The local bridge stores the connection in `runtime/.workshop-connection.json`. The release builder excludes it, and the extension does not put it in model prompts or settings backups.

For development on the same machine, HTTP on localhost is supported. Hosted access requires HTTPS. The remote server derives author/voter identity from the authenticated token and ignores a client-supplied identity. Revoke access by removing or rotating that participant's token in the service configuration and restarting it.

Limits: 16 concurrent requests, 60 requests per minute per account, 20 publishes per day per account, 30 review updates per hour, 32 KB per skill, 16,000 instruction characters, 1,000 published skills, 20 entries per page and 12 locally installed skills. A user has one star/rating/feedback record per skill; repeated ratings update that record. Text is displayed with escaping, and importing never runs scripts. Operators still need to moderate content and issue tokens responsibly; these controls prevent routine overload, not every possible abuse.

Co-work uses the local bridge's persistent task board. Add tasks with concrete acceptance criteria and disjoint file/asset ownership. A provider tab claims one atomically; another worker cannot claim an unexpired task. Workers renew their 30-minute lease with `ms_cowork` update and report their evidence. Complete or release tasks from the board. This shares work across your provider sessions; it does not log in to, message or operate another person's account. There is no automatic file-level merge or engine-scene isolation, so avoid parallel edits to the same resource.

Concurrent execution follows Agent → Keep running in the background. When enabled, the loop may continue in hidden/covered tabs; when disabled it parks there. Shared provider pacing coordinates sends across tabs. Co-work coordinates ownership and evidence; it does not change that preference or automatically merge shared files.

For the 6.40 Skills library, project-aware workflows, queued follow-ups and migrated task board, see `WORKSPACE_REVAMP_6.40.md`. Queue receipts confirm delivery only; board resource checks coordinate claims and are not filesystem locks.
