---
name: site-health-kit
description: Build the Site Health screen ("בריאות האתר") for a website (uptime, speed, broken products, certificate, alerts to the phone) from a fixed screen template and a tested reference backend. Use when asked to build, port, deploy or change a site health / בריאות האתר screen.
---

# Site Health kit

Everything is in this folder, and nothing in it is edited. Read `START-HERE.md` completely, to its
last line (`<!-- EOF START-HERE.md -->`), before doing anything else, and follow it. It lists the
other files to read (each ends with its own `<!-- EOF <path> -->` line) and the rules of the work.

Never retype `site_health.html`; copy it. The backend is a copy of `reference/` that you adapt
outside this folder. Run the scripts and tests of the kit instead of rewriting them. You never
hold a production secret: `OWNER-STEPS.md` says what the owner does and how you confirm it.

<!-- EOF SKILL.md -->
