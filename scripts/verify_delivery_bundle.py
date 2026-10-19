"""Verify exact PSD edit evidence and optionally package declared deliverables.

The JSON manifest is the source of truth. Each job must name a PSD, its exact
Photoshop edit evidence, and a completed visual-review record. Optional QA
reports can provide a second recorded SHA-256. Packaging never modifies evidence.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from check_photoshop_edit_gate import check


def resolve(base, value, field):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing field: ' + field)
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()


def nested(data, dotted):
    value = data
    for key in dotted.split('.'):
        if not isinstance(value, dict) or key not in value:
            raise ValueError('Missing QA hash field: ' + dotted)
        value = value[key]
    return value


def safe_arcname(value):
    value = str(value).replace('\\', '/')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe archive path: ' + value)
    return str(path)


def verify_visual_review(path):
    if not path.is_file():
        raise ValueError('Visual review missing: ' + str(path))
    review = json.loads(path.read_text(encoding='utf-8-sig'))
    required = review.get('overview') is True and review.get('layout') == 'reviewed'
    required = required and review.get('missingImagery') is False and review.get('largeOffsets') is False
    required = required and isinstance(review.get('nativePixelCrops'), list) and bool(review['nativePixelCrops'])
    if not required:
        raise ValueError('Visual review is incomplete: ' + str(path))


def verify_manifest(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    base = manifest_path.parent
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    jobs = data.get('jobs')
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('Manifest jobs must be a nonempty list')
    names = set()
    archive_entries = []
    summaries = []
    for job in jobs:
        name = job.get('name') if isinstance(job, dict) else None
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('Every job needs a unique nonempty name')
        names.add(name)
        psd = resolve(base, job.get('psd'), name + '.psd')
        evidence = resolve(base, job.get('evidence'), name + '.evidence')
        review = resolve(base, job.get('visualReview'), name + '.visualReview')
        verify_visual_review(review)
        gate = check(psd, evidence)
        digest = hashlib.sha256(psd.read_bytes()).hexdigest()
        if digest != gate['finalPsdSha256']:
            raise ValueError('Gate hash mismatch: ' + name)
        qa_value = None
        if job.get('qaReport'):
            qa_path = resolve(base, job['qaReport'], name + '.qaReport')
            qa = json.loads(qa_path.read_text(encoding='utf-8-sig'))
            qa_value = nested(qa, job.get('qaShaField', 'structure.finalPsdSha256'))
            if qa_value != digest:
                raise ValueError('QA hash mismatch: ' + name)
        psd_arc = safe_arcname(job.get('psdArchiveName', name + '/' + psd.name))
        archive_entries.append((psd, psd_arc))
        for item in job.get('deliver', []):
            if isinstance(item, str):
                source = resolve(base, item, name + '.deliver')
                arcname = name + '/' + source.name
            elif isinstance(item, dict):
                source = resolve(base, item.get('path'), name + '.deliver.path')
                arcname = item.get('archiveName', name + '/' + source.name)
            else:
                raise ValueError('Invalid deliver entry for ' + name)
            if not source.is_file():
                raise ValueError('Deliverable missing: ' + str(source))
            archive_entries.append((source, safe_arcname(arcname)))
        summaries.append({'name': name, **gate, 'visualReview': 'passed', 'qaSha256': qa_value})
    arcnames = [entry[1] for entry in archive_entries]
    if len(arcnames) != len(set(arcnames)):
        raise ValueError('Duplicate archive paths')
    return summaries, archive_entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--zip', dest='zip_path', type=Path)
    args = parser.parse_args()
    summaries, entries = verify_manifest(args.manifest)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.zip_path:
        args.zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
            for source, arcname in entries:
                archive.write(source, arcname=arcname)
        with zipfile.ZipFile(args.zip_path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError('ZIP CRC failed: ' + bad)
    print(json.dumps({'jobs': summaries, 'archiveEntries': len(entries), 'zip': str(args.zip_path.resolve()) if args.zip_path else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
