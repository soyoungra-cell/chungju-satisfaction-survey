const { chromium } = require('playwright-core');
const { spawn } = require('child_process');
const fs = require('fs');
const FF = process.argv[2], SRC = process.argv[3], OUT = process.argv[4];
const path = require('path');
const FPS = 30, DUR = 63;
(async () => {
  const fonts = ['nanum-gothic/korean-400.css','nanum-gothic/korean-700.css','nanum-gothic/korean-800.css','gowun-dodum/korean-400.css',
                 'nanum-gothic/latin-800.css','nanum-gothic/latin-400.css','gowun-dodum/latin-400.css']
    .map(f => `<link rel="stylesheet" href="file://${path.resolve('node_modules/@fontsource/' + f)}">`).join('');
  const html = fs.readFileSync(SRC, 'utf8').replace(/<link[^>]+fonts\.g[^>]+>/g, '');
  const WRAP = path.join(path.dirname(path.resolve(SRC)), '.rec.html');
  fs.writeFileSync(WRAP, `<!doctype html><html><head><meta charset="utf-8">${fonts}</head><body>${html}</body></html>`);
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await p.goto('file://' + WRAP);
  await p.evaluate(async () => {
    window.__reels.exportMode();
    await Promise.all(['800 60px "Nanum Gothic"','700 60px "Nanum Gothic"','400 60px "Nanum Gothic"','400 60px "Gowun Dodum"'].map(f => document.fonts.load(f, '가나다 아이의 1957')));
    await document.fonts.ready;
    const urls = [...document.querySelectorAll('.photo .img')].map(n => (n.style.backgroundImage.match(/url\("?(.*?)"?\)/) || [])[1]).filter(Boolean);
    await Promise.all([...urls, ...[...document.images].map(i => i.src)].map(u => new Promise(r => { const im = new Image(); im.onload = im.onerror = r; im.src = u; })));
  });
  console.log('fonts', await p.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded').length), 'total', await p.evaluate(() => window.__reels.total()));
  const ff = spawn(FF, ['-y','-loglevel','error','-f','image2pipe','-framerate',String(FPS),'-c:v','mjpeg','-i','-',
    '-i','bgm.mp3','-map','0:v','-map','1:a','-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p',
    '-profile:v','high','-r',String(FPS),'-c:a','aac','-b:a','160k','-t',String(DUR),'-movflags','+faststart',OUT], { stdio: ['pipe','inherit','inherit'] });
  const n = FPS * DUR, t0 = Date.now();
  for (let i = 0; i < n; i++) {
    await p.evaluate(t => window.__reels.at(t), i / FPS);
    const buf = await p.screenshot({ type: 'jpeg', quality: 93 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 300 === 0) console.log(i, '/', n, ((Date.now() - t0) / 1000).toFixed(0) + 's');
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await b.close();
  fs.unlinkSync(WRAP);
  console.log('done');
})();
