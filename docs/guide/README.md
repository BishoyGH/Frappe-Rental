# Frappe Rental guide

Frappe Rental adds a generic rental engine to ERPNext: anything with a time range can be rented, from a camera
to an apartment, a photographer's hour or a yearly maintenance plan.

| Read this | If you are |
| --- | --- |
| [Admin setup](admin-setup.md) | installing the app and setting up a company |
| [Roles](roles.md) | anyone using the app day to day (manager, front desk, accountant, provider, customer) |
| [Accounting](accounting.md) | an accountant or the person who signs off the chart of accounts |
| [API](api.md) | integrating a website, kiosk or device |
| [Supported versions](supported-versions.md) | choosing Frappe and ERPNext versions |
| [Upgrade notes](upgrade.md) | upgrading the app or moving from v15 to v16 |

Words used throughout:

- **Rental Type**: how something is rented (time unit, identification, buffers, deposit, billing plan). Presets
  ship for Device, Apartment, Hotel Room, Storage Unit, Vehicle, Event Gear, Photographer, Maintenance, Boat
  Charter, Bicycle, Meeting Room, Tool and Tour Guide.
- **Rental Item**: what customers see and book. **Rental Unit**: the concrete thing (a serial number, an
  asset, a pool of 200 chairs, a person).
- **Rental Booking**: a reservation of units for a time range. **Rental Contract**: an agreement that can
  cover many bookings, allocations, billing and visits.
