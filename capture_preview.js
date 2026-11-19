/* Paste into the browser console on a Studocu document preview.
 *
 * It scrolls through the preview so each page loads the way it would for a
 * reader, reveals client-side blurred content, then saves preview-export.json.
 *
 * This only works on content the site supplies to the browser. Missing pages
 * are listed under `skippedPages`; the PDF build still rejects partial exports
 * unless you pass --allow-partial. Set REVEAL_PREVIEW to false for readable-only
 * capture without changing the page's presentation.
 */
(function () {
async function capturePreview(options = {}) {
  const REVEAL_PREVIEW = options.reveal ?? true;
  const PAGE_TIMEOUT_MS = options.pageTimeoutMs ?? 8000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = options.quiet ? () => {} : console.log.bind(console);

  const frames = [...document.querySelectorAll('#page-container .pf')];
  if (!frames.length) throw new Error('No document preview pages (#page-container .pf) found.');

  if (REVEAL_PREVIEW) {
    // Keep this rule in the document so lazy-loaded content is also unblurred.
    let style = document.getElementById('preview-unblur-style');
    if (!style) {
      style = document.createElement('style');
      style.id = 'preview-unblur-style';
      document.head.append(style);
    }
    style.textContent = `
      #page-container .pf, #page-container .pf * {
        filter: none !important;
        -webkit-filter: none !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
      }
      #page-container .pc { display: block !important; }
    `;
  }

  const reveal = (frame) => {
    if (!REVEAL_PREVIEW) return;
    const content = frame.querySelector('.pc');
    // Reveal wrappers too: a filter on an ancestor blurs the whole preview.
    for (let el = content || frame; el; el = el.parentElement) {
      const s = getComputedStyle(el);
      if (s.filter.includes('blur')) el.style.setProperty('filter', 'none', 'important');
      if (s.display === 'none') el.style.setProperty('display', 'block', 'important');
      if (s.visibility !== 'visible') el.style.setProperty('visibility', 'visible', 'important');
      if (Number(s.opacity) === 0) el.style.setProperty('opacity', '1', 'important');
    }
    if (!content) return;
    // Suppress sibling covers, preserving any sibling document containers.
    for (const sibling of content.parentElement.children) {
      if (sibling !== content && !sibling.matches('.pc') && !sibling.querySelector('.pc')
          && !['STYLE', 'LINK'].includes(sibling.tagName)) {
        sibling.style.setProperty('display', 'none', 'important');
      }
    }
    // Persist overrides inside the saved HTML as well as the live page. Avoid
    // touching transforms, text colours or positioning used by PDF text layers.
    for (const el of [content, ...content.querySelectorAll('*')]) {
      el.style.setProperty('filter', 'none', 'important');
      el.style.setProperty('backdrop-filter', 'none', 'important');
    }
    content.style.setProperty('display', 'block', 'important');
  };

  // Report the reason a page is not readable, or null if it is readable.
  const unreadableReason = (frame) => {
    const content = frame.querySelector('.pc');
    if (!content) return 'not loaded';
    for (let el = content; el && el !== document.body; el = el.parentElement) {
      const s = getComputedStyle(el);
      if (s.filter.includes('blur')) return 'blurred';
      if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return 'hidden';
    }
    return null;
  };

  const pages = [];
  const skippedPages = [];
  // Save each page before scrolling on: virtualised viewers can unload it later.
  for (const [i, frame] of frames.entries()) {
    reveal(frame);
    frame.scrollIntoView({block: 'center'});
    const started = Date.now();
    while (!frame.querySelector('.pc') && Date.now() - started < PAGE_TIMEOUT_MS) await sleep(150);
    reveal(frame);
    const reason = unreadableReason(frame);
    log(`Page ${i + 1}/${frames.length}: ${reason || 'ok'}`);
    if (reason) skippedPages.push({number: i + 1, reason});
    else {
      const content = frame.querySelector('.pc');
      const lines = [...content.querySelectorAll('.t')].map((el) => el.textContent);
      pages.push({
        number: i + 1, className: frame.className, html: content.outerHTML,
        text: lines.length ? lines.join('\n') : content.textContent,
      });
    }
  }
  window.scrollTo(0, 0);

  const stylesheets = [...document.querySelectorAll('link[rel="stylesheet"]')]
    .map((e) => e.href)
    .filter((u) => u.includes('doc-assets.') && u.includes('/html/'));
  if (!stylesheets.length) throw new Error('Document stylesheet was not found.');

  const pageUrl = new URL(location.href);
  for (const key of [...pageUrl.searchParams.keys()]) {
    if (key.toLowerCase() === 'sid') pageUrl.searchParams.delete(key);
  }
  const data = {
    format: 2,
    title: document.title,
    pageUrl: pageUrl.href,
    capturedAt: new Date().toISOString(),
    totalPages: frames.length,
    revealedPreview: REVEAL_PREVIEW,
    stylesheets,
    skippedPages,
    pages,
  };
  if (options.download !== false) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement('a'), {href: url, download: 'preview-export.json'});
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  log(`Exported ${pages.length} of ${frames.length} pages.`);
  if (skippedPages.length && !options.quiet) {
    console.warn('Not exported (not readable):', skippedPages.map((p) => `${p.number} (${p.reason})`).join(', '));
  }
  return data;
}

// One implementation for browser-console users, the CLI and the MCP server.
// The function is self-contained so Playwright can serialize it into a frame.
if (typeof module === 'object' && module.exports) module.exports = {capturePreview};
else return capturePreview();
})();
