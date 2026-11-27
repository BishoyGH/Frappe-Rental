// Setup screens: list columns and form fields per doctype. Option lists come from setup.form_options.
export const screens = {
  ItemTypes: {
    doctype: 'Rental Type',
    title: 'Item types',
    single: 'Item type',
    columns: [
      { key: 'name', label: 'Name' },
      { key: 'mode', label: 'Kind' },
      { key: 'time_unit', label: 'Billing unit' },
      { key: 'identification_mode', label: 'Identification' },
    ],
    sections: [
      {
        title: 'Booking rules',
        fields: [
          { key: 'type_name', label: 'Name', type: 'text', createOnly: true, reqd: true },
          { key: 'mode', label: 'Kind', type: 'select', options: 'modes' },
          { key: 'time_unit', label: 'Billing unit', type: 'select', options: 'time_units' },
          { key: 'identification_mode', label: 'Identification', type: 'select', options: 'identification_modes' },
          { key: 'min_duration', label: 'Min duration (billing units)', type: 'number' },
          { key: 'max_duration', label: 'Max duration (billing units)', type: 'number' },
          { key: 'buffer_before', label: 'Buffer before (min)', type: 'number' },
          { key: 'buffer_after', label: 'Buffer after (min)', type: 'number' },
          { key: 'deposit_rule', label: 'Deposit rule', type: 'select', options: 'deposit_rules', blank: true },
          { key: 'cancellation_policy', label: 'Cancellation policy', type: 'select', options: 'cancellation_policies', blank: true },
        ],
      },
      {
        title: 'Needs',
        fields: [
          { key: 'requires_hold', label: 'Hold before confirm', type: 'check' },
          { key: 'requires_deposit', label: 'Deposit', type: 'check' },
          { key: 'requires_contract', label: 'Contract', type: 'check' },
          { key: 'requires_checkin', label: 'Handover', type: 'check' },
          { key: 'requires_return_inspection', label: 'Return inspection', type: 'check' },
          { key: 'allow_quantity', label: 'Book a quantity', type: 'check' },
        ],
      },
    ],
    customFieldsEditor: true,
    defaults: { mode: 'Resource', time_unit: 'Day', identification_mode: 'None', requires_hold: 1 },
  },
  Items: {
    doctype: 'Rental Item',
    title: 'Items',
    single: 'Item',
    columns: [
      { key: 'item_name', label: 'Name' },
      { key: 'rental_type', label: 'Type' },
      { key: 'location', label: 'Location' },
      { key: 'rate_card', label: 'Rate card' },
      { key: 'is_published', label: 'Published', check: true },
    ],
    filters: [{ key: 'rental_type', options: 'rental_types', label: 'Type: any' }],
    sections: [
      {
        title: 'Item',
        fields: [
          { key: 'item_name', label: 'Name', type: 'text', reqd: true },
          { key: 'rental_type', label: 'Item type', type: 'select', options: 'rental_types', reqd: true },
          { key: 'location', label: 'Location', type: 'select', options: 'locations', blank: true },
          { key: 'rate_card', label: 'Rate card', type: 'select', options: 'rate_cards', blank: true },
          { key: 'capacity_people', label: 'Capacity (people)', type: 'number' },
          { key: 'is_published', label: 'Show on website', type: 'check' },
        ],
      },
    ],
    customFrom: 'rental_type',
  },
  Units: {
    doctype: 'Rental Unit',
    title: 'Units',
    single: 'Unit',
    columns: [
      { key: 'unit_name', label: 'Name' },
      { key: 'rental_item', label: 'Item' },
      { key: 'status', label: 'Status' },
      { key: 'location', label: 'Location' },
      { key: 'barcode', label: 'Barcode' },
    ],
    filters: [{ key: 'status', options: 'unit_statuses', label: 'Status: any' }],
    sections: [
      {
        title: 'Unit',
        fields: [
          { key: 'unit_name', label: 'Name', type: 'text', reqd: true },
          { key: 'rental_item', label: 'Item', type: 'link', doctype: 'Rental Item', reqd: true },
          { key: 'status', label: 'Status', type: 'select', options: 'unit_statuses' },
          { key: 'location', label: 'Location', type: 'select', options: 'locations', blank: true },
          { key: 'barcode', label: 'Barcode', type: 'text' },
          { key: 'serial_no', label: 'Serial No', type: 'text' },
          { key: 'quantity_available', label: 'Quantity (pooled)', type: 'number' },
        ],
      },
    ],
    customFrom: 'rental_item',
  },
  Customers: {
    doctype: 'Customer',
    title: 'Customers',
    single: 'Customer',
    columns: [
      { key: 'customer_name', label: 'Name' },
      { key: 'customer_type', label: 'Type' },
      { key: 'customer_group', label: 'Group' },
      { key: 'territory', label: 'Territory' },
    ],
    sections: [
      {
        title: 'Customer',
        fields: [
          { key: 'customer_name', label: 'Name', type: 'text', reqd: true },
          { key: 'customer_type', label: 'Type', type: 'select', options: 'customer_types' },
          { key: 'customer_group', label: 'Group', type: 'select', options: 'customer_groups' },
          { key: 'territory', label: 'Territory', type: 'select', options: 'territories' },
        ],
      },
    ],
    showBookings: true,
  },
}
