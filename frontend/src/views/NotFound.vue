<template>
  <div class="min-h-[60vh] flex items-center justify-center">
    <div class="text-center">
      <div class="text-8xl font-bold text-primary/20 mb-4">404</div>
      <h1 class="font-display text-2xl font-bold mb-2">页面不存在</h1>
      <p class="text-gray-500 mb-6">你访问的页面可能已被移除或地址有误</p>
      <router-link to="/" class="btn-primary">
        <span class="icon mr-2">home</span>返回首页
      </router-link>
    </div>
  </div>
</template>
