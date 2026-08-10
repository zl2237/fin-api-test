<template>
  <RequestProgressBar />
  <router-view />
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores'
import RequestProgressBar from '@/components/RequestProgressBar.vue'

const store = useAppStore()
store.initTheme()
</script>
