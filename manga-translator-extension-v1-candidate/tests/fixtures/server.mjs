import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
const assets = join(here, 'assets');
const MAIN_PORT = Number(process.env.MTE_FIXTURE_PORT ?? 4173);
const CDN_PORT = Number(process.env.MTE_FIXTURE_CDN_PORT ?? 4174);

const main = http.createServer(async (req, res) => {
  setBaseHeaders(res);
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${MAIN_PORT}`);
  if (url.pathname.startsWith('/assets/')) return await serveAsset(url.pathname.slice('/assets/'.length), res);
  if (url.pathname === '/') return html(res, indexPage());
  if (url.pathname === '/same-origin') return html(res, readerShell('Same-origin images', sameOriginBody()));
  if (url.pathname === '/picture-srcset') return html(res, readerShell('Picture/srcset', pictureBody()));
  if (url.pathname === '/lazy') return html(res, readerShell('Lazy loading', lazyBody()));
  if (url.pathname === '/canvas') return html(res, readerShell('Canvas', canvasBody()));
  if (url.pathname === '/spa') return html(res, readerShell('SPA source changes', spaBody()));
  if (url.pathname === '/virtualized') return html(res, readerShell('Virtualized source changes', virtualizedBody()));
  if (url.pathname === '/replacement') return html(res, readerShell('DOM replacement', replacementBody()));
  if (url.pathname === '/revoked-blob') return html(res, readerShell('Revoked Blob URL', revokedBlobBody()));
  if (url.pathname === '/tainted-canvas') return html(res, readerShell('Tainted canvas', taintedCanvasBody()));
  if (url.pathname === '/cross-origin') return html(res, readerShell('Cross-origin CORS/no-CORS', crossOriginBody()));
  if (url.pathname === '/iframe') return html(res, readerShell('Cross-origin iframe', iframeBody()));
  notFound(res);
});

const cdn = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${CDN_PORT}`);
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (url.pathname === '/cors/page-4.png') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    return await serveAsset('page-4.png', res);
  }
  if (url.pathname === '/nocors/page-5.png') return await serveAsset('page-5.png', res);
  if (url.pathname === '/redirect-same') {
    res.statusCode = 302;
    res.setHeader('Location', `/nocors/page-5.png`);
    return res.end();
  }
  if (url.pathname === '/frame-reader') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end(`<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#bbb}img{display:block;width:900px;max-width:100%;height:auto;margin:auto}</style><img src="/nocors/page-5.png">`);
  }
  if (url.pathname === '/not-image') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end('<!doctype html><title>not image</title>');
  }
  notFound(res);
});

main.listen(MAIN_PORT, '127.0.0.1', () => {
  console.log(`Phase 1 fixture reader: http://127.0.0.1:${MAIN_PORT}/`);
});
cdn.listen(CDN_PORT, '127.0.0.1', () => {
  console.log(`Phase 1 fixture CDN:    http://127.0.0.1:${CDN_PORT}/`);
});

function setBaseHeaders(res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Content-Security-Policy', "default-src 'self' http://127.0.0.1:*; img-src 'self' http://127.0.0.1:* blob: data:; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'");
}

async function serveAsset(name, res) {
  const safe = normalize(name).replace(/^(\.\.[/\\])+/, '');
  const path = join(assets, safe);
  if (!path.startsWith(assets)) return notFound(res);
  try {
    const bytes = await readFile(path);
    res.statusCode = 200;
    res.setHeader('Content-Type', mime(path));
    res.setHeader('Content-Length', bytes.length);
    res.end(bytes);
  } catch {
    notFound(res);
  }
}

function html(res, body) {
  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(body);
}

function notFound(res) {
  res.statusCode = 404;
  res.setHeader('Content-Type', 'text/plain; charset=utf-8');
  res.end('not found');
}

function mime(path) {
  switch (extname(path).toLowerCase()) {
    case '.png': return 'image/png';
    case '.jpg':
    case '.jpeg': return 'image/jpeg';
    case '.webp': return 'image/webp';
    default: return 'application/octet-stream';
  }
}

function indexPage() {
  const links = [
    ['/same-origin', 'A — same-origin sequential images'],
    ['/picture-srcset', 'B — picture/srcset/currentSrc'],
    ['/lazy', 'C — lazy attributes and delayed source'],
    ['/canvas', 'D — origin-clean canvas'],
    ['/spa', 'E — SPA chapter URL change'],
    ['/virtualized', 'F — same element changes source'],
    ['/replacement', 'G — DOM node replacement'],
    ['/revoked-blob', 'H — revoked Blob URL'],
    ['/tainted-canvas', 'I — tainted canvas → screenshot'],
    ['/cross-origin', 'J — cross-origin CORS and no-CORS'],
    ['/iframe', 'K — cross-origin iframe visual region']
  ];
  return `<!doctype html><meta charset="utf-8"><title>Phase 1 fixtures</title>
  <style>${baseCss()}</style><main><h1>Manga Translator — Phase 1 Fixtures</h1><p>Use these pages to validate discovery/acquisition without OCR or Engine.</p>
  <ol>${links.map(([href,label]) => `<li><a href="${href}">${label}</a></li>`).join('')}</ol></main>`;
}

function readerShell(title, content) {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>${baseCss()}</style></head><body>
  <header><a href="/">Fixtures</a><span>${title}</span><img src="/assets/icon.png" width="32" height="32" alt="UI icon"></header>
  <main id="reader">${content}</main></body></html>`;
}

function baseCss() {
  return `html{background:#ddd;font:16px system-ui,sans-serif}body{margin:0}header{position:sticky;top:0;z-index:2;display:flex;gap:1rem;align-items:center;padding:.7rem 1rem;background:#fff;border-bottom:1px solid #aaa}main{max-width:960px;margin:0 auto;padding:24px}#reader img.page,#reader canvas{display:block;width:min(900px,100%);height:auto;margin:18px auto;background:white;box-shadow:0 1px 5px #777}button{font:inherit;padding:.5rem .8rem}.spacer{height:1400px}.note{padding:1rem;background:#fff6c9}`;
}

function sameOriginBody() {
  return [1,2,3,4].map((n) => `<img class="page" data-page="${n}" src="/assets/page-${n}.png" alt="fixture page ${n}">`).join('');
}

function pictureBody() {
  return `<picture><source media="(min-width: 700px)" srcset="/assets/page-3.webp 1x"><source srcset="/assets/page-2.jpg 1x"><img class="page" data-page="picture" src="/assets/page-1.png" srcset="/assets/page-2.jpg 700w, /assets/page-3.webp 900w" sizes="(max-width: 700px) 100vw, 900px" alt="responsive fixture"></picture>`;
}

function lazyBody() {
  const images = Array.from({ length: 120 }, (_, index) => {
    const n = (index % 6) + 1;
    const attribute = index % 2 === 0 ? 'data-lazy-src' : 'data-original';
    return `<img class="page lazy-page" data-page="${index + 1}" ${attribute}="/assets/page-${n}.png" alt="lazy fixture ${index + 1}">`;
  }).join('');
  return `<p class="note">120 candidates start without src. The fixture itself loads only images near its viewport; extension detection must not mass-fetch image bytes.</p>${images}
  <script>
    const io = new IntersectionObserver((entries)=>{for(const e of entries){if(e.isIntersecting){const el=e.target; const src=el.dataset.lazySrc||el.dataset.original; if(src&&!el.getAttribute('src')) setTimeout(()=>el.src=src,80);}}},{rootMargin:'800px'});
    document.querySelectorAll('.lazy-page').forEach((image)=>io.observe(image));
  </script>`;
}

function canvasBody() {
  return `<canvas id="comic" width="900" height="1300" data-page="canvas"></canvas><script>
  const c=document.querySelector('#comic'); const x=c.getContext('2d');
  x.fillStyle='#fafafa';x.fillRect(0,0,c.width,c.height);x.strokeStyle='#111';x.lineWidth=8;x.strokeRect(40,40,820,1220);
  x.font='48px sans-serif';x.fillStyle='#111';x.fillText('PHASE 1 CANVAS FIXTURE',100,150);
  for(let i=0;i<4;i++){x.strokeRect(90,220+i*245,720,200);x.fillText('Panel '+(i+1),130,330+i*245)}
  </script>`;
}

function spaBody() {
  return `<p><button id="next">Change chapter source</button> <span id="route">chapter 1</span></p>
  <img id="spa-page" class="page" data-page-index="1" src="/assets/page-1.png" alt="SPA fixture"><script>
  let chapter=1; document.querySelector('#next').onclick=()=>{chapter=chapter===1?2:1; history.pushState({},'', '/spa?chapter='+chapter); const img=document.querySelector('#spa-page'); img.dataset.pageIndex=String(chapter); img.src='/assets/page-'+chapter+'.png'; document.querySelector('#route').textContent='chapter '+chapter;};
  </script>`;
}

function virtualizedBody() {
  return `<p><button id="advance">Change source on the same image element</button> <span id="vstate">page 3</span></p>
  <img id="virtual" class="page" data-page="virtual" src="/assets/page-3.png" alt="virtualized source fixture"><script>
  let n=3; document.querySelector('#advance').onclick=()=>{n=n===3?4:3; const img=document.querySelector('#virtual'); img.src='/assets/page-'+n+'.png'; document.querySelector('#vstate').textContent='page '+n;};
  </script>`;
}

function replacementBody() {
  return `<p><button id="replace">Replace image node, keep same source</button></p><div id="slot"><img class="page" data-page="replacement" src="/assets/page-6.png" alt="replacement fixture"></div><script>
  document.querySelector('#replace').onclick=()=>{const old=document.querySelector('#slot img'); const next=document.createElement('img'); next.className='page'; next.dataset.page='replacement'; next.src='/assets/page-6.png'; next.alt='replacement fixture'; old.replaceWith(next);};
  </script>`;
}

function revokedBlobBody() {
  return `<p class="note">The Blob URL is revoked after decode. Acquisition should fall back to the already-loaded image canvas snapshot.</p><img id="blob-page" class="page" data-page="blob" alt="revoked blob fixture"><script>
  (async()=>{const response=await fetch('/assets/page-2.png'); const blob=await response.blob(); const url=URL.createObjectURL(blob); const img=document.querySelector('#blob-page'); img.src=url; await img.decode(); URL.revokeObjectURL(url);})();
  </script>`;
}

function taintedCanvasBody() {
  return `<p class="note">A no-CORS cross-origin image is drawn into this canvas. toBlob should be blocked and the visible screenshot path should remain available.</p><canvas id="tainted" width="900" height="1300" data-page="tainted"></canvas><script>
  const img=new Image(); img.src='http://127.0.0.1:${CDN_PORT}/nocors/page-5.png'; img.onload=()=>{const c=document.querySelector('#tainted'); c.getContext('2d').drawImage(img,0,0,c.width,c.height);};
  </script>`;
}

function crossOriginBody() {
  return `<p class="note">CORS image should be acquirable in page context. no-CORS image should require the later fallback path. The local HTTP CDN intentionally cannot exercise the production exact-HTTPS permission grant.</p>
  <img class="page" data-page="cors" crossorigin="anonymous" src="http://127.0.0.1:${CDN_PORT}/cors/page-4.png" alt="CORS CDN fixture">
  <img class="page" data-page="nocors" src="http://127.0.0.1:${CDN_PORT}/nocors/page-5.png" alt="no CORS CDN fixture">`;
}

function iframeBody() {
  return `<p class="note">The reader lives in a different origin. The top-level content script cannot inspect its DOM, so Phase 1 exposes the iframe itself as a viewport-region candidate for screenshot acquisition.</p>
  <iframe data-page="iframe-reader" src="http://127.0.0.1:${CDN_PORT}/frame-reader" title="cross-origin reader" style="display:block;width:min(900px,100%);height:1300px;border:0;margin:18px auto;background:white"></iframe>`;
}
