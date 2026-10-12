# Local static project input

Use for an existing local project directory, a user-supplied directory attachment available on disk, or an uploaded archive containing HTML and static assets. Local serving and rendering are part of the authorized conversion; do not upload the project to a hosting service.

## Resolve the input

- Locate the supplied directory or archive using its actual attachment path. Preserve the HTML, CSS, JavaScript, images and fonts together with their relative paths.
- For archives, extract into a writable job subdirectory using the available archive tool. Reject extraction paths outside that directory, and inspect the extracted layout. Do not flatten folders or overwrite source files.
- Prefer `index.html` at the supplied project root. Ignore `__MACOSX` metadata and dependency directories during discovery. A single wrapper directory can be unwrapped. If several independent projects contain an entry and the intended one is unclear, ask which to capture; otherwise use the supplied root.
- For an explicit HTML path, use its containing directory as the initial server root. If root-relative URLs refer to assets in a parent project root, inspect the supplied project structure and serve that root with a relative `--entry`.
- This mode serves already-built static files. If the entry requires a backend, uncompiled framework source, or a build step, identify the missing requirement rather than silently installing dependencies, editing source, or claiming a complete capture.

## Start the project server

Use the bundled Python runtime and [../scripts/serve_static_project.py](../scripts/serve_static_project.py):

```sh
python3 <skill-dir>/scripts/serve_static_project.py \
  --project-dir '<project-directory>' \
  --entry 'index.html' \
  --job-dir '<job-directory>'
```

`--port 0` is the default and chooses an unused port. The first stdout line is compact JSON with the exact `url`, root and port; use that URL rather than guessing. `local_source.json` records the same source metadata. The server binds only to `127.0.0.1`, leaves source files unchanged, preserves nested resource paths, and blocks directory listings and symlinks escaping the project root. Do not start another server on an occupied fixed port or terminate a user-owned process. Retain the execution session identifier for cleanup.

## Render and capture

1. Read the available Browser skill and open the reported URL. Add the user-requested hash/query state when applicable.
2. Wait for fonts and visible images. Check browser errors and resource loading for the actual rendered page. Missing visible local resources must be resolved by correcting the serving root or locating supplied assets; avoid changes to project code without a task-related reason.
3. Follow [browser-capture.md](browser-capture.md), then the standard prepare, atlas rendering, build and token-efficient visual QA workflow. Local page capture has the same 72 PPI, 1x pixel rendering by default, native type, layering and quality requirements as online input.
   - Keep `local_source.json` in the job directory. Preparation maps the resolved `currentSrc` and single CSS background-image URLs back to the supplied project root, percent-decodes URL paths, ignores query/fragment components for filesystem lookup, and copies the original bytes into the job assets. It checks path confinement and existence; it does not recover missing originals from page screenshots.
   - Ordinary image layers are rendered directly from these copied source files using Pillow, not from a screenshot of the webpage or atlas. Supported modes include object-fit fill/contain/cover/none/scale-down, common two-value object/background positioning, transparency, uniform rounded clipping, rectangular ancestor clipping, single-image background size and repeat. Preserve source provenance in `image_provenance.json`.
   - Browser reference screenshots are for layout comparison only. Atlas screenshots remain necessary for native-text caches and CSS/vector paint; supported source image atoms are excluded from those atlases. Missing images are fatal. Unsupported formats or effects require a direct renderer or a specifically recorded exception through `--allow-image-raster-fallback`; default preparation stops with an explanatory error.
4. Keep the project server running through asset bundling and PSD generation. The generated atlases use a separate job-directory loopback server; do not replace the project's document root or expose the job folder inside the user's project.
5. Report external-resource dependencies, missing fonts or backend limitations honestly. Bundled fonts may render in the browser but still require a separately installed matching font for Photoshop editing.
6. After PSD validation, stop only the temporary servers started for this conversion. Restore temporary viewport overrides. Do not leave a required capture/build process running at turn end.

Deliver the normal PSD, preview and notes. Notes should identify the local project and entry instead of presenting its temporary localhost address as a permanent source, and list any image-effect fallbacks. No actual project is needed merely to update this skill; validate helpers with isolated fixtures.
