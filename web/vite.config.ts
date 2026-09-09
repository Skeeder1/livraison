import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';

/*
 * Two builds live here.
 *
 * `npm run dev` and `npm run build:demo` serve and bundle `demo/`, the
 * standalone page that replaces the old folium-generated `vrp_visualization.html`.
 *
 * `npm run build` produces the library: one ES module, one UMD bundle, one
 * stylesheet and the declaration files, with React kept external so the host
 * application owns it.
 *
 * Paths are relative on purpose: both builds are run from this directory.
 */
export default defineConfig(({ mode }) => {
  const isDemo = mode === 'demo' || mode === 'development';

  if (isDemo) {
    return {
      root: 'demo',
      plugins: [react()],
      build: { outDir: '../dist-demo', emptyOutDir: true },
    };
  }

  return {
    plugins: [react(), dts({ include: ['src'] })],
    build: {
      lib: {
        entry: 'src/index.ts',
        name: 'DeliveryReplay',
        fileName: (format) => (format === 'es' ? 'delivery-replay.js' : 'delivery-replay.umd.cjs'),
        formats: ['es', 'umd'],
      },
      cssFileName: 'delivery-replay',
      rollupOptions: {
        external: ['react', 'react-dom', 'react/jsx-runtime'],
        output: {
          globals: {
            react: 'React',
            'react-dom': 'ReactDOM',
            'react/jsx-runtime': 'jsxRuntime',
          },
        },
      },
    },
  };
});
