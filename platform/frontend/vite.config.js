import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
        },
    },
    build: {
        rollupOptions: {
            output: {
                // 供应商按包族分块：应用迭代只失效 index 业务块，第三方各自长缓存。
                // 按依赖图引用，不改变加载时机（element-plus 仍随入口首屏拉取）。
                manualChunks: function (id) {
                    if (!id.includes('node_modules'))
                        return;
                    if (id.includes('element-plus') || id.includes('@element-plus'))
                        return 'element-plus';
                    if (id.includes('@vue-flow'))
                        return 'vue-flow'; // 仅 DAG 视图引用，随路由懒加载
                    if (/[\\/]node_modules[\\/](vue|vue-router|pinia|axios)[\\/]/.test(id))
                        return 'vue-core';
                    return 'vendor'; // dayjs/lodash-es 等 EP 传递依赖
                },
            },
        },
    },
    server: {
        port: 5173,
        proxy: {
            // 用 /api/（带尾斜杠）避免误匹配前端路由 /apis、/api-manage 等
            '/api/': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
        },
    },
});
