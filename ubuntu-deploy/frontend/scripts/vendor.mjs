import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('static/vendor', { recursive: true });
await copyFile('node_modules/plotly.js-dist-min/plotly.min.js', 'static/vendor/plotly.min.js');
await copyFile('node_modules/plotly.js-dist-min/LICENSE', 'static/vendor/PLOTLY-LICENSE');
