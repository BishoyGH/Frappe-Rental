# Decisions (override `PLAN.md` where they differ)

## D1. Rent anything
No fixed list of verticals. Every rentable thing is defined by a user-created **Rental Type** (called "Item type" in the UI) with its own booking rules (resource or service, billing units, min/max duration, buffers, deposit, cancellation policy, required steps) and **custom fields** added in the UI (Frappe Custom Field / child table, no code). The types named in `PLAN.md` (apartment, hotel room, device, storage, photographer, maintenance contract) ship only as **presets** to copy from, plus examples such as vehicle, boat and event gear. The first release is the generic engine, not a set of verticals. Phase 1 is validated with two presets (Device and Apartment) only as acceptance tests.

## D2. Frappe UI look
The staff app and customer website follow the **Frappe UI** design language (as in Frappe CRM and Helpdesk): gray sidebar with workspace switcher, compact list views, badges, tabbed detail pages with a side panel.
Implementation: a Vue 3 + `frappe-ui` single-page app served at `/rental` (staff, role-gated) and a public Vue/website app at `/rentals` for customers, both talking to the whitelisted REST API in `PLAN.md` section 8. Desk (standard Frappe forms) stays available for setup DocTypes such as Rate Card and Settings. This adds a `frontend/` folder (Vite + frappe-ui) to the layout in section 9 and about 4 weeks to phases 1 and 3.

Mockups: https://claude.ai/artifact/GWrCpQ4YQmxYKq34oEZmjY
