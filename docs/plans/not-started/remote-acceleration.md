# Remote Acceleration UX Copy Checklist

## Consent Dialog
- [ ] Title: "Enable Remote Acceleration?"
- [ ] Body: "Remote acceleration allows your local development server to be accessed from the internet. This can be useful for testing with external services, sharing progress with collaborators, or previewing changes on mobile devices.

**Important:** By enabling this feature, your local project will be exposed to the public internet. Anyone with the generated URL can access your development server. No project-hosted endpoint is configured — only the remote acceleration tunnel is created.

Do not enable this feature if you are working with sensitive data or on a private network where exposure is not permitted."
- [ ] Primary button: "Enable Remote Acceleration"
- [ ] Secondary button: "Cancel"

## Active Indicator
- [ ] Text: "**Remote acceleration active** — Your local server is accessible via the internet. Anyone with the URL can access it."

## HTTP Warning
- [ ] Title: "Warning:"
- [ ] Body: "This connection is not encrypted (HTTP). Data transmitted through this tunnel is sent in plain text and can be intercepted by third parties. Use only for testing purposes. Do not transmit sensitive information."

## Cloudflare Tunnel Warning
- [ ] Title: "Cloudflare Tunnel detected."
- [ ] Body: "Your traffic is routed through Cloudflare's network. While the tunnel itself is encrypted, Cloudflare may inspect or log traffic in accordance with their privacy policy. Review Cloudflare's terms of service before use."

## Implementation Checklist
- [ ] First-enable consent dialog implemented with exact title, body, and button text
- [ ] Active remote indicator shown whenever remote acceleration is enabled
- [ ] HTTP endpoint warning displayed when tunnel protocol is HTTP
- [ ] Cloudflare Tunnel warning displayed when hostname matches `*.trycloudflare.com`
- [ ] All copy matches this document verbatim
- [ ] No project-hosted endpoint configuration is implied or referenced in any copy

## Implementer Notes
- The consent dialog must be shown only once per session. Do not re-prompt on page reload.
- The active indicator must update in real time when remote acceleration is toggled.
- Warnings are additive — if both HTTP and Cloudflare conditions are met, display both warnings.
- All copy must be localizable. Use the exact English text above as the source string.