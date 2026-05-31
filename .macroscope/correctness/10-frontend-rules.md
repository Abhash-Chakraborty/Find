Apply these rules when reviewing changes under `frontend/**`.

Frontend review priorities:
- Check light mode and dark mode readability for any visible UI change.
- Watch for stale state after upload, delete, retry, like, process completion, modal close, or tab/filter changes.
- Verify gallery, search, clusters, people, and vault views still use the right image URL variant for each surface.
- Flag regressions where preview modals, tabs, query params, bulk actions, or empty states drift out of sync.
- Be strict about API contract assumptions in `frontend/src/lib/api.ts` and related consumers.
- Avoid approving UI changes that look visually inconsistent with the current Find design system.
