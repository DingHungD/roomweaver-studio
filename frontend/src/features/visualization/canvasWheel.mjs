/** A native non-passive listener is required: React delegates wheel passively. */
export function bindCanvasWheel(element, changeZoom) {
  const wheel = event => {
    event.preventDefault();
    event.stopPropagation();
    if (event.deltaY) changeZoom(event.deltaY < 0 ? 1.1 : 1 / 1.1);
  };
  element.addEventListener('wheel', wheel, {passive:false});
  return () => element.removeEventListener('wheel', wheel);
}
