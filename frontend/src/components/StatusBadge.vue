<template>
  <Badge :theme="statusTheme(status)" :label="__(status)" variant="subtle" data-testid="status" />
</template>

<script setup>
import { Badge } from 'frappe-ui'
import { statusTheme } from '../lib/format'

defineProps({ status: String })
</script>
