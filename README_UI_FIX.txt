QŪNAR v0.8.1 - targeted UI correction

Changed: app.py ONLY.

1. Removed three duplicate User Guide download controls accidentally inserted in the previous patch.
2. Displays one localized guide download below the QŪNAR branding and BEFORE the My report expander.
3. No Before you start expander is created by this version of app.py.
4. Keeps report workspace, calculations and previously implemented session-state fixes unchanged.

Installation:
- Replace the root app.py with this file.
- Keep the existing docs/QUNAR_User_Guide_EN_v0.8.1.pdf, ..._RU_..., ..._KK_... from the previous update.
- Streamlit Cloud: confirm GitHub commit is deployed, then reboot/refresh application.
- Check there is exactly one User Guide link above My report, with no Before you start.

This patch was syntax-checked but not browser-tested on deployed Streamlit.
