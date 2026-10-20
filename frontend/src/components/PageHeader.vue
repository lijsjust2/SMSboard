<template>
  <div class="page-header">
    <div>
      <h2 class="ph-title">{{ title }}</h2>
      <div class="ph-sub">{{ subtitle }}</div>
    </div>
    <div class="ph-actions"><slot /></div>
  </div>
</template>

<script setup>
defineProps({ title: String, subtitle: String })
</script>

<style scoped>
.page-header { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 18px; gap: 12px; flex-wrap: wrap; }
.ph-title { margin: 0; font-size: 24px; font-weight: 700; color: #23283f; }
.ph-sub { margin-top: 4px; font-size: 13px; color: #8a91a8; }
.ph-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
</style>
