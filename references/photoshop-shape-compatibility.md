# Photoshop shape editing compatibility

Read before creating or changing any native-shape exporter. This is a delivery gate, not optional visual QA.

## Known failure and diagnosis boundary

A generated shape PSD opened and composited in psd-tools, but Photoshop reported "Cannot transform because of a program error" (`e348c8.1140`) on dragging a shape. The exporter had constructed minimal vector-mask, fill, stroke and live-origination descriptors by attaching tags to a PixelLayer. This is a demonstrated unsafe export route, not a confirmed mapping from that error code to a specific missing field. Do not blame the user's preferences, GPU, fonts, or Photoshop installation without isolating the failure against a Photoshop-created control document.

A parser recognizing `kind == shape`, preserved radii values, a valid preview, and a successful binary round trip do not validate Photoshop's edit engine. They cannot authorize delivery of an editable-shape PSD.

## Supported construction

Prefer creating shapes through Photoshop's native scripting/Action Manager interface and saving through Photoshop. Alternatively use a Photoshop-authored shape template or a maintained serializer with demonstrated edit tests for the exact fields and versions being emitted. Preserve its complete required descriptors and their native types. Never infer Adobe class IDs or required descriptor keys from what psd-tools happens to read.

Do not build an ad hoc writer during a page export by attaching a few `vmsk`, `SoCo`, `vstk`, or `vogk` tags to PixelLayer and setting `pixel_data_irrelevant=True`. A raster cache plus a shape label is not a validated native shape. A custom serializer may be developed in an isolated fixture workflow, but cannot be used for delivery until the tests below pass in Photoshop.

Audit, against native Photoshop output:

- Unique positive document-wide layer IDs and consistent group records; no copied duplicate IDs.
- Actual pixel bounds, vector-mask coordinates, fill/stroke alignment, and live shape bounds in their correct coordinate spaces. Scaling or moving requires all dependent representations to stay consistent.
- Complete native origination descriptors, correct class IDs, versions, unit types, transform data where required by the native schema, corner fields and descriptor-list relationships. Absence of an optional field in one Adobe version is not proof it is optional in another.
- Finite positive rectangle dimensions, normalized nonnegative radii, nonsingular transforms, valid closed paths and fill rules. Emit a normal four-corner rectangle when radii are zero. Do not encode zero-radius corners as duplicate tangency knots with degenerate segments. For independent nonzero corners, use valid segment/handle and closure semantics.
- Accurate channels/caches and pixel-data flags for the layer type, independent Fill and Stroke properties, and alpha applied once. Preserve complete group behavior and Unicode names.

These checks supplement the edit tests. They are not proof that an untested handcrafted descriptor is safe.

## Photoshop edit smoke tests

Work on a disposable copy; never modify the user's source or only finished copy. Record the Photoshop version/build, exporter identity, file hashes, actual command results and UI observations. Use real application execution, not fabricated JSON or psd-tools transforms.

1. Open the newly exported PSD in Photoshop without a repair/recovery warning.
2. Enumerate every native shape by its unique layer ID. Select and translate each by a small nonzero X/Y distance, commit, verify the new position, undo, and verify restoration. Test with actual Photoshop commands; a click without checking the result is not success.
3. On representatives of every emitted shape family (plain rectangle, equal/unequal/partly-zero radii, fill-only, stroke-only, fill+stroke, thin divider, alpha and clipping when emitted), commit translation, nonuniform scale and rotation, undo each, and verify editable Fill, Stroke and four corner controls where applicable. Use the problematic zero-radius and mixed-radius fixture families in regression tests.
4. Move a module group containing shapes and text; verify membership and relative placement, then undo.
5. Save a copy through Photoshop, close it, reopen it, repeat move/undo for every native shape, and verify no error/repair dialog. Record the tested final PSD SHA-256 after this save. Do not modify or rebuild that file afterward without repeating the gate.
6. Compare the reopened layout against the intended capture, preserving groups, editable type and shape data. Keep a compact test log and UI evidence next to the job artifacts.

Write `photoshop_edit_validation.json` using the schema accepted by `scripts/check_photoshop_edit_gate.py`. It is an evidence index, not a replacement for application execution. Every boolean must be based on the observed operation. Do not generate a passing report from a structural validator.

## Failure policy

Any Photoshop error dialog, failed commit/undo, unexpected property loss, missing test evidence or inability to run Photoshop leaves `photoshopEditTest` as `failed` or `not-run`. No editable-shape deliverable may be marked complete in either state. Keep the candidate internal, preserve captures/assets, and report the exact blocker. Do not deliver the candidate with only an "untested in Photoshop" disclaimer. Do not silently rasterize shapes or drop live-corner metadata to bypass the problem. A raster-only alternative requires the user's explicit acceptance of that changed requirement.

Repair by rebuilding the failing shape through a validated native route, then regenerate and retest the exact final file. Reusing the same failed descriptor writer under a new layer name is not a repair. Never promise universal freedom from Photoshop program errors; enforce that unverified/known-failing exports do not pass delivery.
