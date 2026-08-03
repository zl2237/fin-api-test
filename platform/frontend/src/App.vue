<template>
  <router-view />
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores'

const store = useAppStore()
store.initTheme()
</script>
