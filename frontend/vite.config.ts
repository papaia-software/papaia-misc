/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({ resolve:{alias:{'@':new URL('./src',import.meta.url).pathname}},plugins:[react(),tailwindcss()],server:{proxy:{'/api':'http://127.0.0.1:8000'}},test:{environment:'jsdom',setupFiles:'./src/test-setup.ts',css:false} });
