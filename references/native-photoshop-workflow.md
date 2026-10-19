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

The only packaged native drop-shadow profile exercised so far is `rgba(21, 57, 90, 0.04) 0px 2px 8px 0px` at 1x. Other shadows, transformed/clipped solid surfaces, mixed unsplit gradient+solid paint, elliptical radii or unsupported geometry must stop with an explanatory error. Extend the native effect route in a fixture workflow and test it in Photoshop before accepting those features; do not apply the sample shadow to arbitrary input or silently rasterize eligible solids.

ExtendScript compatibility: keep the tested ES3-compatible syntax, use `if/else` for shape-family decisions, include the JSON compatibility shim, write UTF-8 with BOM, and flush logs by closing/reopening files (there is no assumed `File.flush()`). The generated root/staging/output paths must be JSON-escaped absolute file paths; never shell-escape them as JavaScript.

The historical workflow needed user help because Photoshop COM was unavailable and modal file-dialog automation was unreliable. That is environment-specific, not a requirement for every export: use a working native interface when available, and request only the missing user action when necessary. **File → Open** opens the resulting PSD; **Scripts → Browse** filters for scripts and will hide PSD files.
