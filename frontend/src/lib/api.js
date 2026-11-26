import { call } from 'frappe-ui'

// The SPA only talks to frappe_rental.api.*
export const api = (method, params = {}) => call(`frappe_rental.api.${method}`, params)
