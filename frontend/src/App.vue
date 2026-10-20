<template>
  <router-view v-slot="{ Component }">
    <component :is="Component" :key="$route.fullPath" />
  </router-view>
</template>

<style>
:root {
  --sb-primary: #4f6ef7;
  --sb-primary-deep: #3b53d6;
  --sb-bg: #f2f4fb;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f6f7fb;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

.page { max-width: 1280px; margin: 0 auto; padding: 20px; }
.card-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; }
.mb16 { margin-bottom: 16px; }

/* 统计卡片：带主色顶边与悬浮效果 */
.el-card { border-radius: 14px !important; border: none !important;
  box-shadow: 0 2px 12px rgba(31, 45, 122, .08) !important; }
.stat-card { flex: 1; min-width: 170px; overflow: hidden; position: relative;
  transition: transform .15s ease, box-shadow .15s ease; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(31, 45, 122, .14) !important; }
.stat-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--sb-primary), #7c9bff); }
.stat-card .num { font-size: 26px; font-weight: 700; color: #2c3150; letter-spacing: .5px; }
.stat-card .label { font-size: 13px; color: #8a91a8; margin-top: 4px; }
.stat-card .el-card__header { font-weight: 600; color: #2c3150; }

.el-table { --el-table-header-bg-color: #f7f8fd; }

/* 移动端适配 */
@media (max-width: 768px) {
  .page { padding: 10px; }
  .card-row { gap: 10px; margin-bottom: 10px; }
  .stat-card { min-width: calc(50% - 5px); flex: 1 1 calc(50% - 5px); }
  .stat-card .num { font-size: 20px; }
  .el-dialog { width: 94% !important; }
  .el-message-box { width: 92% !important; }
}
</style>
