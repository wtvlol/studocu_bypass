/* Paste into the browser console on a document page you can read.
 *
 * It scrolls through the preview so each page loads the way it would for a
 * reader, then saves the readable pages to preview-export.json.
 *
 * It never removes access gates. A page that is blurred, hidden or not loaded
 * is NOT exported. It is listed under `skippedPages`, and extract_preview.py
 * refuses to build an incomplete PDF unless you pass --allow-partial.
 */
(async () => {
  const PAGE_TIMEOUT_MS = 8000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const frames = [...document.querySelectorAll('#page-container .pf')];
  if (!frames.length) throw new Error('No document preview pages (#page-container .pf) found.');

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

  // Scroll each page into view and give it time to load, as a reader would.
  for (const [i, frame] of frames.entries()) {
    frame.scrollIntoView({block: 'center'});
    const started = Date.now();
    while (!frame.querySelector('.pc') && Date.now() - started < PAGE_TIMEOUT_MS) await sleep(150);
    console.log(`Page ${i + 1}/${frames.length}: ${unreadableReason(frame) || 'ok'}`);
  }
  window.scrollTo(0, 0);

  const stylesheets = [...document.querySelectorAll('link[rel="stylesheet"]')]
    .map((e) => e.href)
    .filter((u) => u.includes('doc-assets.') && u.includes('/html/'));
  if (!stylesheets.length) throw new Error('Document stylesheet was not found.');

  const pages = [];
  const skippedPages = [];
  frames.forEach((frame, i) => {
    const reason = unreadableReason(frame);
    if (reason) skippedPages.push({number: i + 1, reason});
    else pages.push({number: i + 1, className: frame.className, html: frame.querySelector('.pc').outerHTML});
  });

  const data = {
    format: 2,
    title: document.title,
    pageUrl: location.href,
    capturedAt: new Date().toISOString(),
    totalPages: frames.length,
    stylesheets,
    skippedPages,
    pages,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement('a'), {href: url, download: 'preview-export.json'});
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);

  console.log(`Exported ${pages.length} of ${frames.length} pages.`);
  if (skippedPages.length) {
    console.warn('Not exported (not readable):', skippedPages.map((p) => `${p.number} (${p.reason})`).join(', '));
  }
})();
