# Reusable Photoshop-native export route

Use this route for native editable rectangles. It is packaged from the native creation/move/undo/save/reopen route exercised successfully in Adobe Photoshop 27.10.0 on 2026-10-19. That historical result validates the construction route; it does not certify new pages, new parameters or another Photoshop build.

1. Finish the ordinary capture, assets, dimension contract, prepare and atlases. `build_psd.py` currently paints solid surfaces as pixels. Its result is an **internal staging artifact only**, not a native-shape deliverable. Name it `internal-paint-staging.psd`. Do not deliver this staging file or declare the task complete at this point.
2. Run:

   `python scripts/prepare_native_photoshop_job.py --job-dir <job> --staging-psd <job>/internal-paint-staging.psd --output <job>/page.psd`

   This writes `photoshop-rebuild-data.json`, `native-job-config.json` and `rebuild-in-photoshop.jsx`. It derives dimensions, semantic module IDs/names, shape geometry, fill/stroke and four corners from the job, without page-specific widths, heights or source paths. Use a different job directory for another page.
3. Run the generated JSX in Photoshop through a working documented native automation connection. If unavailable, ask the user to run it once using **File → Scripts → Browse**. Do not assume a command-line launch executed it; check the runtime log and output. Preserve existing user documents. The script creates native shapes, saves through Photoshop, runs a native fixture and tests every generated shape before and after reopening. It deliberately leaves results `pending-independent-validation`.
4. Run:

   `python scripts/validate_native_photoshop_output.py --job-dir <job> --psd <job>/page.psd`

   This checks the exact Photoshop-saved file's native paths/origination, bounds, normalized corners, fill/stroke, opacity, layer IDs, text, module groups and real edit-test results. It accepts Photoshop-native `vscg` fill descriptors as well as `SoCo`; never invent a `SoCo` tag merely to satisfy an old parser. It does not mark UI/visual tests as passed automatically.
5. Independently composite the final PSD and compare it against the Photoshop-saved `photoshop-preview.png` and browser reference. Use the normal overview/native-pixel crop workflow. Inspect Photoshop Shape Properties, including Fill, Stroke and four independent corners on a representative nonuniform rectangle, and save actual UI evidence.
6. Only after observing both UI properties and visual QA, rerun the structural validator with `--ui-evidence <actual-screenshot> --confirm-ui-properties --confirm-visual`. These flags record completed observations, not instructions to fabricate them. It seals `photoshop_edit_validation.json` and invokes the existing delivery gate. Keep raw `photoshop-native-results.json` and the runtime log intact. Do not change final PSD bytes after certification.

## Supported surface scope and safe stopping

The generator supports axis-aligned CSS solid-color rectangles, four nonelliptical radii, uniform inside strokes, and separately editable straight side borders. It scales bounds, radii and stroke widths with the recorded render scale. No fixed page size, layer count, font or image count may be assumed.

The native bridge uses `scripts/native_shadows.py` to resolve explicit supported shadow profiles:

- A zero-offset, zero-blur, positive-spread outer shadow on an opaque fill becomes a separate native rectangle below the original surface, with expanded bounds and independently expanded nonzero corner radii. Its readable layer name ends with `/ 外描边`. Fill and border of the casting surface remain separate and unchanged. This preserves a 1px button outline without flattening the button.
- A trailing CSS `inset` shadow with zero x/y offset, zero blur and positive spread becomes a separate native inside-stroke shape above the original surface. It retains the source bounds and four independent radii, uses a transparent fill, and carries the inset color and spread as editable Stroke properties. Its readable layer name ends with `/ 内描边`. Offset or blurred inset shadows remain unsupported.
- At 1x, `rgba(21, 57, 90, 0.04) 0px 2px 8px 0px` and `rgba(21, 57, 85, 0.047) 0px 6px 28px 0px` become native editable Drop Shadow layer effects with their own color, opacity, distance and size. Photoshop rounds effect opacity to integer percentages (4.7% becomes 5%); record this small difference in delivery notes. CSS and Photoshop blur kernels can differ; inspect the shadow regions against the browser reference.

The bridge creates disposable shadow fixtures from the actual job specifications before opening production staging. It tests move/scale/rotate/undo, saves/reopens, repeats editing, and keeps `shadowFixtureTests` plus fixture PSD/PNG files. This is runtime evidence, not a blanket certification of every size/color/build. The independent validator checks native effect color, geometry and opacity, allowing at most 0.51 percentage points for native opacity rounding. Continue to require whole-page visual QA and the exact-final-file edit gate.

See [native-shadow-validation.json](native-shadow-validation.json) for the historical Photoshop build, tested profiles, fixture hashes and observed properties. It does not replace a new job's evidence.

Offset or blurred inset shadows, multiple shadows, unlisted soft-shadow profiles, scaled soft shadows, nonopaque hard outer-shadow casting fills, transformed/clipped solid surfaces, mixed unsplit gradient+solid paint, elliptical radii or unsupported geometry must stop with an explanatory error. Extend and test a new profile before accepting it; never replace it with the sample shadow or silently rasterize eligible solids.

Original-file image rendering also supports independent nonelliptical corner radii, including `0px 38px 0px 0px`, with CSS radius normalization. This clips original image bytes and does not use browser image screenshots. Regression-test both direct images and shadows with `test_image_sources.py`, `test_export_support.py` and `test_native_shadows.py`; the latter covers hard inner and outer shapes, supported soft profiles and explicit rejection paths. On Windows run Python with `-X utf8` so existing UTF-8 JSON tests do not depend on the system ANSI code page.

ExtendScript compatibility: keep the tested ES3-compatible syntax, use `if/else` for shape-family decisions, include the JSON compatibility shim, write UTF-8 with BOM, and flush logs by closing/reopening files (there is no assumed `File.flush()`). The generated root/staging/output paths must be JSON-escaped absolute file paths; never shell-escape them as JavaScript.

The historical workflow needed user help because Photoshop COM was unavailable and modal file-dialog automation was unreliable. That is environment-specific, not a requirement for every export: use a working native interface when available, and request only the missing user action when necessary. **File → Open** opens the resulting PSD; **Scripts → Browse** filters for scripts and will hide PSD files.
