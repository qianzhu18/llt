import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomePage.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/requests',
      name: 'lobby',
      component: () => import('../views/requests/LobbyPage.vue'),
    },
    {
      path: '/requests/new',
      name: 'request-new',
      component: () => import('../views/requests/NewPage.vue'),
      meta: { auth: true },
    },
    {
      path: '/requests/:id',
      name: 'request-detail',
      component: () => import('../views/requests/DetailPage.vue'),
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('../views/library/LibraryPage.vue'),
    },
    {
      path: '/me',
      name: 'dashboard',
      component: () => import('../views/me/DashboardPage.vue'),
      meta: { auth: true },
    },
    {
      path: '/me/profile',
      name: 'profile',
      component: () => import('../views/me/ProfilePage.vue'),
      meta: { auth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/admin/OverviewPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/admin/settings',
      name: 'admin-settings',
      component: () => import('../views/admin/SettingsPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/admin/UsersPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/admin/requests',
      name: 'admin-requests',
      component: () => import('../views/admin/RequestsPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/admin/reports',
      name: 'admin-reports',
      component: () => import('../views/admin/ReportsPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/admin/gift',
      name: 'admin-gift',
      component: () => import('../views/admin/GiftPage.vue'),
      meta: { auth: true, admin: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFound.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.initialized) {
    await auth.fetchMe()
  }

  if (to.meta.auth && !auth.isLoggedIn) {
    return { name: 'login', query: { next: to.fullPath } }
  }

  if (to.meta.admin && !auth.isAdmin) {
    return { name: 'home' }
  }

  if (to.meta.guest && auth.isLoggedIn) {
    return { name: 'home' }
  }
})

export default router
