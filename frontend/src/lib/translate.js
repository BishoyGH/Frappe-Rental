// Translation helper. Uses messages from the boot data when the server sends them, else the source string.
const messages = (window.rental_boot && window.rental_boot.messages) || {}

export function __(text, args = []) {
  let out = messages[text] || text
  args.forEach((a, i) => {
    out = out.replaceAll(`{${i}}`, a)
  })
  return out
}

export const translatePlugin = {
  install(app) {
    app.config.globalProperties.__ = __
  },
}
