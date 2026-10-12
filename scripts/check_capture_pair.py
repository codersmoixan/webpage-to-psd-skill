"""Reject layout/animation drift across screenshot acquisition."""
import argparse
import json
from pathlib import Path


def compare(before, after, tolerance=0.25):
    issues=[]
    for key in ('url','width','height','viewportHeight','scrollX','scrollY','clientWidth','scrollbarWidth'):
        if before.get(key) != after.get(key): issues.append(f'Capture {key} changed')
    for label,state in [('before',before),('after',after)]:
        if state.get('fontStatus','loaded') != 'loaded':
            issues.append(f'{label}: fonts have not finished loading')
        if state.get('pendingVisibleImages'):
            issues.append(f'{label}: visible images have not finished loading')
    a={e['index']:e for e in before['elements']}; b={e['index']:e for e in after['elements']}
    if a.keys()!=b.keys(): issues.append('Visible element set changed')
    for index in a.keys() & b.keys():
        first,second=a[index],b[index]
        if any(abs(first['rect'][k]-second['rect'][k])>tolerance for k in ('x','y','w','h')):
            issues.append(f'Element {index} moved/resized')
        for key in ('src','naturalSize','text','pseudo','css'):
            if first.get(key)!=second.get(key): issues.append(f'Element {index} {key} changed')
    return {'stable':not issues, 'issues':issues, 'toleranceCSSPixels':tolerance,
            'scope':'Parent document DOM; cross-origin frame contents require visual checking'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir',type=Path,required=True)
    args=parser.parse_args(); root=args.job_dir
    before=json.loads((root/'web_dom.json').read_text(encoding='utf-8-sig'))
    after=json.loads((root/'web_dom_after.json').read_text(encoding='utf-8-sig'))
    report=compare(before,after)
    (root/'capture_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'stable':report['stable'],'issueCount':len(report['issues'])}))
    if not report['stable']: raise SystemExit(1)


if __name__=='__main__': main()
