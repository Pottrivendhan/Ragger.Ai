import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'dev-api-proxy',
      configureServer(server) {
        // Dedicated endpoint to read session token
        server.middlewares.use('/api/dev/session', (_req, res) => {
          try {
            const sessionPath = path.resolve(__dirname, '../storage/dev_session.json');
            if (fs.existsSync(sessionPath)) {
              const data = fs.readFileSync(sessionPath, 'utf8');
              res.setHeader('Content-Type', 'application/json');
              res.end(data);
              return;
            }
          } catch {}
          res.statusCode = 404;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'No active dev session found in storage/dev_session.json' }));
        });

        // Dynamic reverse proxy for all /api requests to the supervised engine
        server.middlewares.use('/api', (req, res, next) => {
          if (req.url === '/dev/session') return next();

          let engineHost = '127.0.0.1';
          let enginePort = 8000;

          try {
            const sessionPath = path.resolve(__dirname, '../storage/dev_session.json');
            if (fs.existsSync(sessionPath)) {
              const session = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
              if (session.port) {
                enginePort = session.port;
                engineHost = session.host || '127.0.0.1';
              }
            }
          } catch {}

          import('http').then(({ default: http }) => {
            const proxyHeaders = { ...req.headers };
            proxyHeaders.host = `${engineHost}:${enginePort}`;

            const proxyReq = http.request(
              {
                host: engineHost,
                port: enginePort,
                path: `/api${req.url}`,
                method: req.method,
                headers: proxyHeaders,
              },
              (proxyRes) => {
                res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
                proxyRes.pipe(res);
              }
            );

            proxyReq.on('error', (err) => {
              res.statusCode = 502;
              res.setHeader('Content-Type', 'application/json');
              res.end(
                JSON.stringify({
                  detail: `Engine unreachable on ${engineHost}:${enginePort}: ${err.message}`,
                })
              );
            });

            req.pipe(proxyReq);
          });
        });
      },
    },
  ],
  base: './', // Ensures assets load correctly from file:// protocol in packaged Electron
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
});
