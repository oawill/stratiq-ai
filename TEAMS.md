# Teams (Phase 5)

Workspaces were already shared containers; Phase 5 adds the people side: invitations, roles, comments, an activity feed and seat limits.

## Roles

| Role | Can do |
|---|---|
| Owner | Everything: invite anyone (including admins), change any role, remove anyone, transfer ownership, billing |
| Admin | Invite members and viewers, change member/viewer roles, remove members and viewers, moderate comments |
| Member | Read and save work, comment |
| Viewer | Read only (sees the team, saved work and comments, cannot save or comment) |

Every rule is enforced in the Python API (`stratiq/team_api.py`, `stratiq/comments_api.py`), against the database, on every request; the interface only hides what the server would refuse. The owner cannot be removed or leave (transfer ownership first). Nobody can change their own role.

## Invitations

- An owner or admin enters an email and a role. The API stores only the SHA-256 of a random 256-bit token and returns the token once; the web app turns it into a link `https://<site>/invite/<token>`.
- The link works **once**, for **7 days**, and only for the **invited email address**: the invitee signs in or creates an account with that address (sign-up and log-in return to the invitation), then clicks Accept. A different signed-in address sees "Wrong account".
- If email is configured (`RESEND_API_KEY` and `EMAIL_FROM`, see `LAUNCH.md`) the link is also emailed. Otherwise the inviter copies it and shares it themselves; the Team page says which applies.
- Re-inviting the same address replaces the earlier link. Pending invitations can be cancelled. Expired, cancelled and used links show "Invitation not available".
- Accepting joins the workspace and makes it the person's active workspace. They keep their own personal workspace and can switch between workspaces on My Workspace.

## Comments

Threaded comments (one reply level) on saved forecasts, scenarios and simulation runs, from the Library on My Workspace. Everyone in the workspace sees them. Members and above can post; authors can delete their own, admins and owners can delete any. Deleting a comment hides its replies. Comments are length-limited (2,000 characters) and rendered as plain text.

## Activity feed

The Team page lists recent activity for the workspace: saved work, comments, invitations, joins, role changes, removals and ownership transfers (from the existing activity log). Team actions are also written to the audit log.

## Seat limits

Members plus pending invitations count toward a per-plan cap, enforced by the server with HTTP 402 `seat_limit`:

| Plan | Seats |
|---|---|
| Explorer | 2 |
| Sports Pro | 2 |
| Strategy Pro | 5 |
| Enterprise | custom (contact us) |

Like the other plan limits, **seat limits only apply once `BILLING_ENFORCED=1`**. While billing is off (early access) a workspace can invite without a cap. The numbers are a proposal: change them in `stratiq/plans.py`.

## Known limits

- Seats are checked when an invitation is created (pending invitations count), not again when it is accepted, so a plan downgrade between the two could leave a workspace over its cap. It blocks further invitations but does not remove anyone.
- There are no per-item permissions, mentions or notifications; comments do not trigger emails.
- Removing a member does not delete what they saved: saved work belongs to the workspace.
- Enterprise features beyond this (SSO, custom permissions, API access) are not built.

## Database

Migration `0007_teams.sql` adds `workspace_invites` and `comments`. It is additive. It is applied to the development database; **it must be applied to production before the Team and comments pages are used there** (`node scripts/migrate.mjs` with production credentials).
