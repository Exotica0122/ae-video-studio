# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/Exotica0122/ae-video-studio/security/advisories/new),
not in a public issue. Include what you ran, what happened, and the output of
`python3 -m aestudio doctor` if it's relevant.

This is a one-person project. I aim to reply within a week and will credit you in the
advisory unless you'd rather not be named.

Only the latest release and `main` get fixes.

## What the plugin can do on your machine

ae-video-studio drives After Effects by writing ExtendScript (`.jsx`) and asking the
MCP bridge to run it. Those scripts run inside After Effects with your user's permissions,
so they can read and write any file you can.

- **Edit plans and designs are code.** The engine compiles `edit.json` and design files into
  scripts. Treat plans, designs and footage folders from someone else the way you would
  treat a script from them.
- **The bridge only runs scripts from one folder.** The `runJsx` patch accepts only `.jsx`
  files directly inside `~/.ae-mcp-bridge/jsx` (or `$AESTUDIO_BRIDGE_DIR/jsx`). Anything
  that can write to that folder as you can run code in After Effects.
- **The bridge is built from upstream at a pinned commit.** `bridge/install.sh` clones
  [after-effects-mcp](https://github.com/Dakkshin/after-effects-mcp) at the commit in
  `bridge/base-commit.txt` and applies `bridge/runJsx.patch`. Review the patch before
  building it.
- **The design preview is local only.** `aestudio design-preview` serves mockups on
  `127.0.0.1`.

## In scope

- A plan, design or media file that makes the engine write a script doing something other
  than what the plan describes (for example, injection through captions, names or file paths).
- The bridge running a script from outside its `jsx` folder.
- The preview server being reachable from other machines, or serving files outside the
  preview folder.
- Secrets or personal data committed to this repository.

## Out of scope

- Running an edit plan or design you were given and didn't read: it is code, as described above.
- Other processes running as your user writing into the bridge's `jsx` folder.
- Vulnerabilities in After Effects, the upstream MCP server or ffmpeg themselves. Report
  those to their maintainers.
