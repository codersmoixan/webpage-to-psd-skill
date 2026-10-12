() => {
  const all = [...document.querySelectorAll('body *')];
  const index = new Map(all.map((element, i) => [element, i]));
  const cssKeys = [
    'color', 'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'lineHeight',
    'letterSpacing', 'textTransform', 'textAlign', 'backgroundColor',
    'backgroundImage', 'backgroundSize', 'backgroundPosition', 'backgroundRepeat',
    'backgroundOrigin', 'backgroundClip', 'backgroundAttachment', 'borderTopWidth',
    'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth', 'borderTopColor',
    'borderRightColor', 'borderBottomColor', 'borderLeftColor', 'borderTopStyle',
    'borderRightStyle', 'borderBottomStyle', 'borderLeftStyle', 'borderRadius',
    'boxShadow', 'textShadow', 'opacity', 'position', 'zIndex', 'overflow',
    'objectFit', 'objectPosition', 'paddingTop', 'paddingLeft', 'paddingRight', 'paddingBottom', 'transform',
    'filter', 'clipPath', 'mixBlendMode', 'fill', 'stroke', 'strokeWidth', 'display',
    'visibility'
  ];
  const documentRect = rect => ({
    x: rect.x + scrollX, y: rect.y + scrollY, w: rect.width, h: rect.height
  });
  const elements = [];
  for (const element of all) {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || style.display === 'none' ||
        style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    let visible = true;
    for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
      const ancestorStyle = getComputedStyle(ancestor);
      if (ancestorStyle.display === 'none' || ancestorStyle.visibility === 'hidden' ||
          Number(ancestorStyle.opacity) === 0) visible = false;
    }
    if (!visible || (element.closest('svg') && element.tagName.toLowerCase() !== 'svg')) continue;
    const text = [];
    for (const node of element.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
      const chars = [];
      for (let i = 0; i < node.textContent.length; i++) {
        const range = document.createRange();
        range.setStart(node, i); range.setEnd(node, i + 1);
        const charRect = range.getBoundingClientRect();
        if (charRect.width && charRect.height) {
          chars.push({ char: node.textContent[i], ...documentRect(charRect) });
        }
      }
      text.push({ value: node.textContent, chars });
    }
    const pseudo = ['::before', '::after'].map(selector => {
      const pseudoStyle = getComputedStyle(element, selector);
      return {
        selector,
        css: Object.fromEntries([...pseudoStyle].map(key => [key, pseudoStyle.getPropertyValue(key)]))
      };
    }).filter(item => !['none', 'normal'].includes(item.css.content));
    elements.push({
      index: index.get(element), parent: index.get(element.parentElement) ?? -1,
      tag: element.tagName.toLowerCase(), id: element.id,
      cls: element.className?.baseVal ?? element.className,
      rect: documentRect(rect),
      css: Object.fromEntries(cssKeys.map(key => [key, style[key]])),
      text, pseudo, src: element.currentSrc || null, alt: element.alt || null,
      naturalSize: element.tagName.toLowerCase() === 'img' ?
        { w: element.naturalWidth, h: element.naturalHeight } : null,
      placeholder: element.placeholder || null,
      svg: element.tagName.toLowerCase() === 'svg' ? element.outerHTML : null
    });
  }
  return {
    url: location.href, title: document.title, width: innerWidth,
    height: document.documentElement.scrollHeight, ratio: devicePixelRatio,
    viewportHeight: innerHeight, scrollX, scrollY,
    clientWidth: document.documentElement.clientWidth,
    scrollbarWidth: innerWidth - document.documentElement.clientWidth,
    fontStatus: document.fonts.status,
    pendingVisibleImages: elements.filter(e => e.tag === 'img').filter(e => {
      const img = all[e.index];
      return !img.complete || img.naturalWidth === 0;
    }).map(e => ({ index: e.index, src: e.src })),
    elements
  };
}
