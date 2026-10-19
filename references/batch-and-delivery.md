# Batch Photoshop execution and delivery verification

Use these helpers when one request contains multiple pages or when editable type needs an explicit Photoshop test. Keep paths and page names in a job manifest outside the skill. The scripts resolve relative paths against that manifest, so manifests remain movable and the skill never needs project-specific constants.

## Manifest

One manifest can feed rebuild, type-edit and delivery stages. Include only the fields needed by the stage being run:

```json
{
  "waitSeconds": 1200,
  "log": "photoshop-batch.log",
  "jobs": [
    {
      "name": "page-a",
      "rebuildScript": "page-a/rebuild-in-photoshop.jsx",
      "result": "page-a/photoshop-native-results.json",
      "psd": "page-a/page-a.psd",
      "typeLog": "page-a/photoshop-type-edit-test.txt",
      "evidence": "page-a/photoshop_edit_validation.json",
      "visualReview": "page-a/visual-reviewed.json",
      "qaReport": "page-a/final-qa-metrics.json",
      "deliver": [
        "page-a/page-a-preview.png",
        "page-a/notes.txt"
      ]
    }
  ]
}
```

Job names must be unique. A rebuild job requires `rebuildScript` and `result`; a type-edit job requires an existing `psd`; delivery verification requires `psd`, `evidence`, and `visualReview`. `qaReport` is optional and defaults to checking `structure.finalPsdSha256`; set `qaShaField` when another dotted field stores the exact final hash. `deliver` is optional. Use an object with `path` and `archiveName` only when the default `<job-name>/<filename>` ZIP path is unsuitable.

## Rebuild and type-edit runners

Generate ExtendScript instead of editing a copied batch file:

```text
python scripts/generate_photoshop_batch_runner.py --manifest jobs.json --mode rebuild --output run-rebuilds.jsx
python scripts/generate_photoshop_batch_runner.py --manifest jobs.json --mode type-edit --output test-type-editing.jsx
```

Run the generated JSX through a working Photoshop automation connection. Rebuild mode waits only for missing generated scripts, executes each one, and checks the declared raw result status. Type-edit mode opens every declared PSD, edits the first native type layer, verifies commit and undo, doubles the point size, verifies commit and undo, and closes the document without saving. It writes one log per PSD plus a batch log, preserves documents that were already open, and throws after recording any failure.

These tests are runtime evidence. Generating JSX does not prove that Photoshop ran it. Read the logs and keep the exact-final-file shape gate separate.

## Final verification and packaging

After shape editing, UI-property inspection and visual review have been recorded, run:

```text
python scripts/verify_delivery_bundle.py --manifest jobs.json --report delivery-verification.json
python scripts/verify_delivery_bundle.py --manifest jobs.json --report delivery-verification.json --zip deliverables.zip
```

The verifier runs the existing Photoshop edit gate against every exact PSD, requires a completed visual-review record, checks an optional QA SHA-256, rejects duplicate or unsafe ZIP paths, and CRC-tests the resulting archive. It never edits the Photoshop evidence or source job files. Add only intended user-facing files to `deliver`; keep atlases, staging PSDs, generated JSX and temporary continuation markers out of the delivery archive.
