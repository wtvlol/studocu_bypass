/* Run in the browser console on the document after scrolling through its pages.
   Exports already-present preview content. It does not fetch missing pages,
   remove access gates, or change blur/visibility styles. */
(() => {
  const frames=[...document.querySelectorAll('#page-container .pf')];
  if (!frames.length) throw new Error('No document preview pages found.');
  const unloadedPages=frames.map((e,i)=>e.querySelector('.pc')?null:i+1).filter(Boolean);
  if (unloadedPages.length) throw new Error('Scroll through these unloaded pages first: '+unloadedPages.join(', '));
  const stylesheets=[...document.querySelectorAll('link[rel="stylesheet"]')]
    .map(e=>e.href).filter(u=>u.includes('doc-assets.studocu.com')&&u.includes('/html/'));
  if (!stylesheets.length) throw new Error('Document stylesheet was not found.');
  const data={title:document.title,pageUrl:location.href,stylesheets,unloadedPages,
    pages:frames.map(e=>e.querySelector('.pc').outerHTML)};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='preview-export.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
  console.log('Exported '+data.pages.length+' already-loaded preview pages.');
})();
