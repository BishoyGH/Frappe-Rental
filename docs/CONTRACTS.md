# D7. Contracts: terms and resource allocation (extends `DECISIONS.md`, overrides `PLAN.md` 4.6)

A **Rental Contract** is the agreement with a customer. It can cover many bookings and many resources over a period (a master agreement), or wrap a single booking. Bookings, billing and visits hang off it.

## Contract terms

### Term library
- **Rental Terms Template** (new): named, versioned, per Item type or general. Holds a rich-text body with Jinja merge fields (`{{ customer.customer_name }}`, `{{ contract.start_date }}`, `{{ units }}`, `{{ billing_plan }}`, `{{ deposit }}`), plus child **clauses**.
- **Rental Clause** (reusable library): title, body, category (Payment, Liability, Use, Maintenance, Insurance, Termination, Privacy, Custom), `mandatory`, `editable_per_contract`, language. Templates are ordered lists of clauses, so a clause fixed once updates future contracts without touching signed ones.
- Per-contract **overrides**: add, remove or edit clauses (if allowed). A contract stores a rendered **snapshot** (HTML and PDF) at signing, so later template changes never alter a signed contract.
- Versioning: amendments create a **Rental Contract Amendment** (new snapshot, effective date, reason), keeping the original.
- Languages and RTL: template per language; the customer's language picks the default.

### Structured terms (machine-readable, drive the system)
Besides legal text, the contract holds fields that the engine enforces:
- Term: `start_date`, `end_date`, `open_ended`, `auto_renew`, `renewal_term`, `notice_period_days`, `minimum_term`, `early_termination_fee`.
- Money: link to the **billing plan** (D6), `deposit` rule, `price_lock` period, `indexation_percent` on anniversary, late-fee rule, currency, payment terms.
- Usage: allowed use, included allowance (hours, km, visits), overage rate, permitted locations, max users, subletting allowed.
- Responsibility: insurance required, damage liability cap, waiver option, maintenance responsibility (customer or us), SLA (response and resolution hours, visit frequency).
- Policies: cancellation policy link, return conditions, grace period.
Bookings under the contract inherit these as defaults and the pricing, billing, late-fee and cancellation logic read them.

### Lifecycle and signatures
`Draft -> In Review -> Awaiting Signature -> Active -> (Suspended) -> Ending -> Ended | Terminated | Renewed`.
- Approval workflow for non-standard terms (discount or clause changes beyond a limit).
- E-signature on the portal (typed or drawn), optional OTP, IP and timestamp stored; counter-signature by an internal signer. Uses ERPNext `Contract` signee fields and a signed PDF attached.
- Reminders before renewal (`notice_period_days`), at expiry, and for unsigned contracts. Auto-renew creates the next term and a new schedule; non-renewal triggers the closure checklist (returns, final invoice, deposit settlement).
- Termination records reason and date, applies the early-termination fee as a Billable Event, releases allocations (below).

## Allocation of resources to a contract

### Rental Contract Allocation (child table, or standalone doctype when history is needed)
Each row assigns a resource to the contract for a period:

| Field | Meaning |
|---|---|
| `allocation_type` | **Specific unit** (serial/asset), **Category** (any unit of an item or type), **Quantity** (pooled), **Capacity** (seats, sqm, hours per month), **Provider time** (retainer hours, visits) |
| `rental_item` / `rental_unit` | What is allocated (unit is optional for category allocations) |
| `from` / `to` | Allocation period (defaults to the contract term) |
| `qty` or `capacity` | How much |
| `exclusive` | Reserved only for this customer (blocks others) vs. entitlement (guaranteed access) |
| `rate_override` | Contract rate per unit or period (otherwise rate card) |
| `billing_plan` | Optional per-row plan override |
| `site` / `location` | Where the resource is used (address, building, room) |
| `status` | Reserved, Active, Swapped, Returned, Released |
| `substitution_allowed` | Whether a similar unit may replace it |

### Behaviour
1. **Availability integration**: exclusive allocations write `Rental Availability Cache` rows with `source_type = Contract`, so the calendar and search never offer them. Category and entitlement allocations reserve **capacity** (count or hours) and are consumed by bookings.
2. **Call-off bookings**: for category, quantity and provider-time allocations, the customer (or staff) creates bookings *against the contract*; the booking decrements the allocation, validates it fits (dates, allowance), and inherits rates and terms. Specific-unit exclusive allocations can auto-generate the booking or run as one long open booking.
3. **Swap and replace**: swapping a unit (broken device, upgraded room) closes the old row, opens a new row, writes Asset Movement or stock entries, and logs the reason. Billing adjusts from the swap date.
4. **Add and remove mid-term**: allocations can be added or released with an effective date; the billing schedule regenerates future rows only (D6); a contract amendment records the change if the customer must agree.
5. **Over-allocation guard**: cannot allocate a unit that is allocated, booked or blocked in the same period; pooled allocations cannot exceed free stock. Warnings for utilisation below an allowance (unused entitlement) and above it (overage billing).
6. **Handover and return per allocation**: each row can have its own handover, serial and condition record; returning all units ends the contract's physical obligations.
7. **Visit allocations** (services and maintenance): a retainer row (e.g. 4 visits per year, 10 hours per month) generates a visit schedule or a pool of hours; each visit or timesheet entry consumes it, shows remaining balance, and bills overage.
8. **Reporting**: allocations by customer, by unit (who holds it now and until when), contract utilisation (allocated vs used), upcoming expiries, idle allocated resources.

## Data model summary
- `Rental Contract` (extend): terms fields above, `terms_template`, `rendered_terms` (snapshot), `status`, `signed_by`, `signed_on`, `countersigned_by`, `billing_plan` (child, D6), `allocations` (child), `amendments` (child), `renewal_of` (link).
- `Rental Terms Template`, `Rental Terms Template Clause` (child), `Rental Clause`.
- `Rental Contract Allocation` (child) and optional `Rental Allocation Log` (swaps, releases).
- `Rental Contract Amendment`.
- Booking gets `contract` and `contract_allocation` links.

## UI (matches the Frappe UI mockups)
Contract page tabs: **Overview** (parties, term, status, signatures), **Terms** (clause list with live preview, edit and add from library, version history), **Allocations** (table with unit, serial, period, rate, status, and a "Find available" picker that uses the availability search; swap and release actions), **Billing** (D6 schedule), **Bookings and visits**, **Documents**.

## Roadmap impact
Terms templates, clauses, signatures and allocations move into Phase 4 (contracts) with allocation-to-availability integration in Phase 2 so the calendar is correct early. About 2 extra weeks overall.
