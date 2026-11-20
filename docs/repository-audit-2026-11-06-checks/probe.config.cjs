const { defineConfig } = require('../../frontend/node_modules/@playwright/test');
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: 'quality-probe.spec.cjs',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5186', viewport: { width: 1440, height: 1000 } },
});
