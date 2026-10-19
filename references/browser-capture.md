# Browser capture contract

Use this procedure after reading the installed Browser control skill.

## Files in the job directory

- `web_reference.png`: full-page screenshot at the exact extraction viewport.
- `web_dom.json`: output from `scripts/capture_page.js`.
- `web_dom_after.json`: repeat extraction immediately after the screenshot.
- `capture_validation.json`: result of `scripts/check_capture_pair.py --job-dir <job-dir>`.
- `capture_dimensions.json`: required viewport, screenshot and scale contract described below.
- `web_assets.json`: result of the page-assets bundle operation.

## Viewport-width default

Before DOM extraction, resolve the capture width in this order:

1. Use an explicit user-requested viewport or canvas width when present.
2. Otherwise use a 1920 CSS-pixel viewport width.

The second rule is only a fallback. An explicit positive width always wins, for either a URL or a local project; do not replace, normalize or clamp it to 1920 merely because 1920 is the default. If width is omitted, use 1920 without asking the user to repeat the request.

Use the documented browser viewport capability to apply this width before any extraction. Height may retain the existing desktop viewport height unless a verified full-height capture is needed. After setting the viewport, read `window.innerWidth`, `window.innerHeight`, `document.documentElement.clientWidth`, `window.devicePixelRatio` and image/font readiness. Assert `innerWidth` equals the requested CSS viewport width; if the backend cannot honor it, resolve the limitation before capture. Do not change browser zoom as a substitute.

Before preparation, write `capture_dimensions.json` with these exact fields:

```json
{
  "widthSource": "default-1920",
  "requestedViewportWidth": 1920,
  "measuredInnerWidth": 1920,
  "measuredInnerHeight": 1200,
  "clientWidth": 1920,
  "scrollbarWidth": 0,
  "devicePixelRatio": 1,
  "screenshotWidth": 1920,
  "screenshotHeight": 6816,
  "scaleSource": "default-1",
  "requestedRenderScale": 1
}
```

Use `widthSource: "explicit"` for a user-specified width and `scaleSource: "explicit"` for a user-specified output scale. `requestedViewportWidth`, measured widths/heights and screenshot dimensions are positive integer CSS pixels; `scrollbarWidth` is a non-negative integer. Read screenshot dimensions from the saved image rather than assuming them. Preparation validates this record against `web_dom.json`, `web_dom_after.json`, `web_reference.png` and its CLI render scale, then adds `effectiveRenderScale`, `finalPSDWidth` and `finalPSDHeight`.

A screenshot backend may omit scrollbar pixels: a 1920 viewport with a 15-pixel scrollbar can yield a 1905-pixel screenshot. This capture is rejected because the builder does not invent or stretch missing page pixels. Use a supported capture whose saved screenshot width exactly matches the resolved viewport width. Apply the same rule to any explicit viewport. Any change affecting layout requires fresh DOM extraction and a new reference screenshot.

Output scale and PPI remain independently configurable. A 1920-pixel capture at `--render-scale 1` stays 1920 pixels wide regardless of whether its metadata is 72 or 300 PPI; 4x rendering makes it 7680 pixels wide. Apply explicit user scale/PPI choices before preparation. Reset agent-applied viewport overrides after all capture and atlas work.

## Capture sequence

1. Open the target URL and wait for `networkidle` when supported.
2. Verify `document.fonts.status` is loaded and every visible image has finished with nonzero natural width. Load lazy images by scrolling through the document, return to the requested initial position, and then repeat the complete capture. Hidden unloaded images do not block the capture. No arbitrary sleep is proof of readiness.
3. Apply and verify the width resolved by the viewport-width rule above before extraction. A tall viewport avoids fixed-element duplication, but verify that changing height does not alter responsive CSS.
4. Read `scripts/capture_page.js` as UTF-8. It contains a function expression. Invoke that expression (`'(' + source + ')()'`) when the browser evaluates a string as source code; for APIs accepting a callable, pass the function directly. Verify a nonempty object is returned before saving.
5. Save the returned object as `web_dom.json`.
6. Take the full-page screenshot without navigating, reloading, resizing, hovering, clicking, or scrolling between extraction and screenshot.
7. Repeat the same extraction immediately, save as `web_dom_after.json`, and run `scripts/check_capture_pair.py --job-dir <job-dir>`. Both captures are mandatory; preparation rejects a missing or changed pair. If animation or automatic carousel movement causes drift, use an available browser animation-pause facility or a page-provided pause control without choosing a different slide; otherwise retry the capture up to three times. If no stable state can be captured, report the limitation rather than delivering mismatched geometry and pixels.
8. Call the page-assets inventory and bundle image, stylesheet, and font assets. Save the bundle result as `web_assets.json`.

The pair check covers parent-document geometry, text, styles and image URLs; it cannot see changing cross-origin iframe contents or prove that a full-page screenshot painted fixed elements at the extracted coordinates. Visually check fixed/sticky controls and iframe regions against the reference before rendering atlases. If the screenshot backend relocates them, capture fixed controls once at the original viewport and use those observed coordinates, or use a tall viewport and repeat both extraction and screenshot after verifying responsive layout. Never repair them with site-specific IDs or guessed offsets. Cross-origin frames must be independently cropped from the verified reference location and identified as raster content.

The capture script records visible elements, parent relationships, document-space rectangles, direct text-node character boxes, relevant computed CSS, image URLs, placeholders, and inline SVG markup. Character boxes are required because element boxes do not preserve line wrapping accurately.

## Atlas rendering

After `build_psd.py prepare`, serve the job directory on a loopback-only HTTP server. For every `atlas_N_white.html` and `atlas_N_black.html`:

1. Open the file through localhost in the same browser engine.
2. Apply a viewport override matching BOTH the width and height recorded for that atlas page in `web_layers.json`. The HTML scales original vector text, SVGs and CSS paint before rasterization; use the recorded render scale, which may have been reduced by size preflight. Do not resize old atlas PNGs to obtain the high-resolution cache. If the browser enforces a minimum viewport height larger than a short atlas, crop only the surplus blank rows; never rescale or crop contributing pixels.
3. Save it as the matching `.png` file.
4. Verify each PNG's width and height exactly match the corresponding manifest page. Dimensions alone do not prove full painting; build rejects any nonempty text atom with an empty recovered cache. If an atlas exceeds the browser's viewport limit, use supported tiled capture without rescaling or repack into smaller atlases; do not accept a silently clamped viewport. Reset temporary viewport overrides after rendering. Reference screenshots remain at the original capture dimensions.

White/black pairs allow the builder to recover color plus alpha without flattening objects against a permanent background.

Ordinary image pixels are taken directly from original files. Atoms marked `imageSource: original-file` have no atlas placement and must not be added to atlas HTML or extracted from atlas screenshots. An image-only job can have zero atlas pages. Record any explicitly enabled image-effect exceptions in `image_provenance.json` and the delivery notes.

## Capture failures

- For cross-origin iframes, canvas, WebGL, maps, or video frames, crop the region from the reference screenshot and document that it is a raster layer.
- If web fonts are unavailable to the browser export, preserve the rendered raster preview and name the expected font in the notes. The PSD type layer should use the closest installed font and remain editable.
- If an image is lazy-loaded, scroll it into view and then repeat the complete capture so coordinates, assets, and screenshot describe the same state.
