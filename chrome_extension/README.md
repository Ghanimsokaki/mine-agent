# ForgePilot Browser Bridge

This is an unpacked Chromium (Chrome/Edge/Brave) extension—not a store package.

1. Go to `chrome://extensions` (or Edge's extensions page), enable **Developer mode**, then choose **Load unpacked** and select this folder.
2. In ForgePilot, create a browser pairing bundle and paste it into the extension popup.
3. Keep an authorized website open in the focused tab. Click **Check for a task now**, or wait for the 30-second bridge check.
4. The page asks for confirmation for **each** requested DOM action. Decline anything unexpected.

It needs `<all_urls>` because the user asked to work across sites. This is powerful permission. The extension does not execute a queued request unless the person at the page confirms it, and it blocks obvious sensitive inputs. Disable or unpair it when you are done.

No browser extension can reliably automate Chrome internal pages, extension store pages, native apps, or sites that prohibit content scripts. It is not a tool to bypass access controls, CAPTCHAs, or website rules.
