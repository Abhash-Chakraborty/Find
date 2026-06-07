# Small-Team Authentication (Instance Sharing)

**Status:** Not started  
**Last reviewed:** 2026-05-29
**Current implementation status:** No user model, authentication middleware, invite flow, instance-management UI, or upload ownership/deletion-request workflow is implemented in the current codebase.

## Summary

Find should support a lightweight single-admin + multi-user model for trusted small-team or household deployments while preserving the local-first philosophy. The machine hosting Find acts as the "admin" and controls storage, database, and shared access. The feature is an opt-in, self-hosted instance-sharing model rather than a cloud multi-tenant identity system.

## Goals

- Keep storage and indexing local to the admin-hosted instance.
- Enable trusted users to authenticate and use the same Find instance.
- Keep authentication and user-management intentionally lightweight and self-hosted.
- Track which authenticated user uploaded each media item.
- Require admin approval for destructive actions (e.g., deletions).

## UX: "Instance" Tab

Place a new **Instance** tab in the UI with two sections: **Create an Instance** and **Join an Instance**.

Create an Instance (admin flows)
- Admin creates a shared instance from the hosting machine. Creating an instance:
  - Marks the backend as running in shared mode.
  - Sets an admin user (local single admin account).
  - Optionally configures a friendly instance name.
- Admin can manually add trusted users (username + password) directly from UI.
- Admin can generate:
  - A short-lived, single-use high-entropy invite token (minimum 128-bit URL-safe random value) that users can paste into "Join an Instance"; or
- A shareable URL containing the one-time token and pointing to the admin's reachable instance address.
- If a human-readable short code is provided for UX purposes, it should only function as an optional alias and still require admin approval alongside strict rate limiting.
- Admin sees a pending join requests list (approve/reject), and a list of active users and their roles.

Join an Instance (user flows)
- A user clicks "Join an Instance" and enters either an invite code or a shareable link.
- They submit a username + password and an optional display name.
- The backend creates a join request which the admin reviews and approves or denies (or if invite is pre-approved, account is created automatically).
- Once approved, the user can sign in and interact with the shared instance.

## Instance Tab UI State Checklist

Use this checklist when implementing or reviewing the future Instance tab. It documents expected UI
states only; no frontend implementation exists yet.

### General states

- [ ] Single-user default: local installs continue to work without creating or joining a shared
  instance.
- [ ] Empty state: no shared instance is configured, with clear create/join entry points.
- [ ] Loading state: authentication, instance details, invite status, and pending request data can
  load without flashing incorrect admin or user controls.
- [ ] Success state: connected instance details, current user role, and active users are visible.
- [ ] Unauthorized state: invalid permissions, missing sessions, and expired sessions are handled
  without exposing admin actions.
- [ ] Error state: failed requests, unavailable backend services, and invalid response shapes are
  shown with recoverable retry paths.

### Admin setup flow

- [ ] Admin can explicitly enable shared-instance mode and create the first admin account.
- [ ] Admin can generate short-lived invite tokens or links.
- [ ] Admin can review pending join requests in loading, empty, error, and populated states.
- [ ] Admin can approve or reject requests with visible success and failure feedback.
- [ ] Active users list is visible to admins and handles empty, loading, and error states.

### Joining-user flow

- [ ] User can enter an invite token or link and submit username/password details.
- [ ] Pending approval state is clearly displayed after a join request is submitted.
- [ ] Approved or successful join state provides a clear sign-in or continue path.
- [ ] Rejected, expired, reused, malformed, or unauthorized invite states are handled gracefully.

> Single-user local installs must not require shared-instance setup. Sharing remains opt-in and local-first by default.

## Authentication & Accounts

Minimal user model (example fields):
- `id` (int)
- `username` (string, unique)
- `display_name` (string)
- `password_hash` (string)
- `is_admin` (bool)
- `created_at`, `last_login`

Notes:
- Passwords stored as bcrypt (or passlib) hashes.
- Sessions can be short-lived tokens/cookies served by the local backend.
- Keep default instance mode as single-user if no admin action taken.

## Authentication Architecture Alternatives

The authentication architecture for Find should prioritize local-first deployments, lightweight operational requirements, and minimal external dependencies. The following approaches were evaluated for small-team shared-instance deployments.

| Approach | Local-First Fit | Operational Complexity | Offline Compatibility | Dependency Footprint | Migration / Maintenance Risk |
|---|---|---|---|---|---|
| Better Auth | Good | Moderate | Good | Moderate | Moderate |
| Auth.js | Moderate | Moderate-to-High | Limited in some flows | Higher | Moderate |
| Backend-Owned Authentication | Excellent | Low | Excellent | Minimal | Low |

### Better Auth

Better Auth provides a modern self-hosted authentication approach with session handling and extensibility. It aligns reasonably well with self-hosted deployments, but may still introduce unnecessary abstraction and operational overhead for small trusted deployments.
Because Find's authoritative API is FastAPI/Python, using Better Auth would also require a clear boundary between the Next.js UI session layer and backend authorization checks.

### Auth.js

Auth.js provides a mature authentication ecosystem and strong OAuth support, but it is more heavily oriented toward web-platform and SaaS-oriented authentication flows. Many of its strengths are less relevant for Find’s local-first deployment model.
It would be most useful if Find later adds optional OAuth providers, but it is not the smallest fit for an offline-capable household instance.

### Backend-Owned Authentication

A lightweight backend-owned authentication system aligns most closely with Find’s local-first philosophy. It minimizes dependency overhead, avoids mandatory cloud identity integrations, preserves offline compatibility, and keeps operational complexity intentionally small for trusted small-team deployments.

### Recommended Direction

For trusted household and small-team deployments, a lightweight backend-owned authentication model is the preferred direction. This approach preserves Find’s self-hosted architecture while avoiding unnecessary SaaS-oriented authentication complexity.

## Data & Metadata Changes

- Add `users` table as above.
- Update `media` table to include `uploader_user_id` (nullable) to record which authenticated user uploaded the media.
- Add `deletion_requests` table to track deletion petitions from non-admins:
  - `id`, `media_id`, `requester_user_id`, `reason`, `created_at`, `approved_by`, `approved_at`, `status`.
- Optional `audit_log` table for admin actions (uploads, approvals, deletions).

## Possible API Endpoints (proposal)

- POST `/api/instance/create` — create instance + initial admin account (local only).
- POST `/api/instance/invite` — (admin) create invite code / link with TTL and optional auto-approve flag.
- POST `/api/instance/join` — (user) submit invite code or token + username/password (creates join request or account if auto-approved).
- GET `/api/instance/requests` — (admin) list pending join requests.
- POST `/api/instance/requests/{id}/approve` — (admin) approve request.
- POST `/api/instance/requests/{id}/reject` — (admin) reject request.
- POST `/api/auth/login` — username/password -> session token / cookie.
- POST `/api/auth/logout` — end session.
- GET `/api/users/me` — current user info.
- POST `/api/image/{media_id}/delete-request` — user requests deletion (creates deletion request).
- GET `/api/admin/deletion-requests` — admin lists pending deletion requests.
- POST `/api/admin/deletion-requests/{id}/approve` — admin approves deletion (permanently delete file and record).

## Behavioral notes

- Uploads from authenticated users attach `uploader_user_id` to `Media` records.
- Public access remains off by default: `MINIO_PUBLIC_READ` remains a separate config option; enabling public MinIO remains explicit and admin-controlled.
- Admin-only actions include: adding/removing users, approving join requests, approving deletions, and toggling instance shared mode.

## Security & Privacy considerations

- Default to local-only deployment: instance sharing via invite links only if the admin exposes the instance (e.g., through NAT, reverse proxy, or by running on a reachable host).
- Require HTTPS/TLS for all non-localhost authentication-related endpoints, including login, join, invite, and session APIs.
- Plaintext HTTP is acceptable only for local development and trusted loopback access. It should be rejected or clearly blocked for LAN/internet-exposed authentication flows to prevent credential or token leakage.
- TLS termination should occur at the deployment edge using a reverse proxy, local certificates, or trusted load balancer configuration.
- Exposed authentication endpoints should fail closed if TLS is not configured rather than relying solely on HTTP-to-HTTPS redirects.
- Deployment documentation should include minimal TLS setup guidance for common reverse proxy solutions such as nginx or Caddy.
- Invite tokens must be single-use or short-lived and stored hashed on disk.
- Rate-limit join attempts and signups.
- Store password hashes with a strong algorithm (bcrypt/argon2) and a proper work factor.
- Do not send any secrets in clear text over logs or email.

## Threat Model

The shared-instance deployment model introduces a small but important trust boundary between the admin-hosted infrastructure and authenticated users accessing the instance.

### Protected Assets

The following assets should be protected:

- locally stored media files,
- metadata and embeddings,
- authentication credentials,
- invite tokens,
- user session tokens,
- audit and deletion records.

### Trust Boundaries

The architecture assumes:

- the admin controls the hosting infrastructure,
- authenticated users are trusted but not fully unrestricted,
- instance sharing is opt-in,
- public exposure remains disabled unless explicitly configured by the admin.

### Potential Threat Actors

Potential threat actors may include:

- unauthorized local-network users,
- internet attackers targeting exposed instances,
- compromised or leaked invite links,
- malicious authenticated users,
- compromised admin devices,
- weak-password attacks against exposed deployments.

### Mitigations

The proposed architecture mitigates these risks through:

- invite-based onboarding,
- admin approval workflows,
- strong password hashing,
- short-lived invite tokens,
- rate limiting,
- optional HTTPS/TLS deployment guidance,
- uploader metadata tracking,
- deletion approval workflows,
- and minimal public exposure by default.

## Admin UX & Operational notes

- Keep the admin UI simple: approve/deny list, generate invites, list active sessions, list users, and viewing deletion requests.
- Provide a lightweight CLI or UI to export the user list and audit logs.
- Provide config flags for `MAX_INVITE_TTL`, `AUTO_APPROVE_INVITES`, and `ALLOW_PUBLIC_ACCESS`.

## Edge cases & optional features

- Guest accounts: create ephemeral accounts with limited rights (view-only) for casual access.
- Role expansion: `editor` vs `viewer` roles for finer-grained control.
- Device-pairing flow for mobile: a QR code with invite token that mobile device can scan.
- LDAP/SSO: intentionally omitted; this proposal focuses on self-hosted, local-first simplicity.

## Implementation Complexity & Migration Considerations

This proposal is intended to remain low-to-moderate in implementation complexity.

Possible implementation areas may include:

1. Lightweight users model and migrations.
2. Session/token authentication middleware.
3. Invite generation and join-request workflows.
4. Instance management UI pages.
5. Metadata additions for uploader tracking and deletion requests.

Backward compatibility should remain straightforward by allowing pre-existing media entries to continue functioning without uploader metadata.

## Out of Scope

This proposal intentionally avoids introducing enterprise or SaaS-oriented authentication complexity.

The following items remain out of scope:

- Public multi-tenant SaaS deployments
- Enterprise SSO systems
- Billing and subscription systems
- Cloud-first identity providers
- Large-scale enterprise RBAC
- Centralized cloud-hosted user management
- Mandatory third-party authentication systems

The goal is to preserve Find’s lightweight, self-hosted, and local-first architecture while enabling trusted small-team collaboration.

## Why This Aligns with Find’s Design

This proposal aligns with Find’s local-first philosophy by:

- keeping user data and images on admin-controlled infrastructure,
- avoiding centralized cloud identity systems,
- enabling practical collaboration for trusted small teams,
- preserving privacy and local ownership,
- and avoiding unnecessary SaaS-oriented operational complexity.

## Future Implementation Considerations

This document focuses on architectural direction and deployment expectations rather than immediate implementation details.
Authentication middleware, database migrations, UI integration, invite workflows, and session handling can be explored in future implementation-focused issues and pull requests.
