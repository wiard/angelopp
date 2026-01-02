# Angelopp v1-ready (Pilot-proof)

## Definition of Done
✅ USSD root menu always responds, no 500s on core paths  
✅ Customer flows:
- Find a rider
- Local businesses (village -> list -> details)
- Change my place
- Travel menu (basic)
✅ Channels:
- My channel (create/post/rename/view)
- Listen (categories)
✅ Sacco Line:
- Latest updates
- Principles & safety
- Verified riders (masked)
- Report issue (stored)
- Community role explanation
✅ Privacy:
- Public rider numbers masked
✅ Ops:
- Server restart procedure documented
- Logs available
- DB schema stable (ensure_schema / migrations)

## Recommended hardening (next step)
- systemd service for app.py (reliable restart)
- logrotate for ussd_server.log
- basic monitoring: liveness + error grep
