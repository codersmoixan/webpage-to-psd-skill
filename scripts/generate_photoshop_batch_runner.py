"""Generate reusable Photoshop JSX runners from a JSON job manifest.

Modes:
  rebuild   Run each prepared rebuild JSX and verify its raw completion status.
  type-edit Open each final PSD and test text edit/undo plus 2x size/undo.

The generated JSX preserves documents that were already open and contains no
project-specific page names or paths beyond those supplied by the manifest.
"""
import argparse
import json
from pathlib import Path


def load_manifest(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    jobs = data.get('jobs')
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('Manifest jobs must be a nonempty list')
    names = []
    for job in jobs:
        name = job.get('name') if isinstance(job, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Every job needs a nonempty name')
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError('Job names must be unique')
    return path, data


def resolved(base, value, field, must_exist=False):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing job field: ' + field)
    path = Path(value)
    path = path if path.is_absolute() else base / path
    path = path.resolve()
    if must_exist and not path.is_file():
        raise ValueError(field + ' does not exist: ' + str(path))
    return path


def js(value):
    return json.dumps(str(value).replace('\\', '/'), ensure_ascii=False)


def rebuild_runner(manifest_path, data):
    base = manifest_path.parent
    wait_seconds = data.get('waitSeconds', 1200)
    if not isinstance(wait_seconds, (int, float)) or wait_seconds <= 0:
        raise ValueError('waitSeconds must be positive')
    log = resolved(base, data.get('log', 'photoshop-batch.log'), 'log')
    rows = []
    for job in data['jobs']:
        rows.append({
            'name': job['name'],
            'script': resolved(base, job.get('rebuildScript'), 'rebuildScript'),
            'result': resolved(base, job.get('result'), 'result'),
            'status': job.get('resultStatus', 'pending-independent-validation'),
        })
    literal = '[' + ','.join(
        '{name:%s,script:%s,result:%s,status:%s}' %
        (js(r['name']), js(r['script']), js(r['result']), js(r['status'])) for r in rows
    ) + ']'
    return """#target photoshop
(function(){
 var jobs=%s,logFile=new File(%s),waitMs=%d;
 logFile.encoding='UTF8';logFile.open('w');logFile.close();
 function log(s){logFile.open('a');logFile.writeln(new Date().toUTCString()+' '+s);logFile.close();}
 function readJson(file){file.encoding='UTF8';if(!file.open('r'))throw Error('Cannot read '+file.fsName);var value=eval('('+file.read()+')');file.close();return value;}
 for(var i=0;i<jobs.length;i++){
  var job=jobs[i],script=new File(job.script),deadline=new Date().getTime()+waitMs;
  log('WAIT '+job.name);
  while(!script.exists){if(new Date().getTime()>deadline)throw Error('Timed out waiting for '+job.name);$.sleep(1000);}
  log('START '+job.name);$.evalFile(script);
  var result=new File(job.result),raw=readJson(result);
  if(raw.status!==job.status)throw Error(job.name+' returned '+raw.status);
  log('COMPLETE '+job.name);
 }
 log('ALL COMPLETE');
})();
""" % (literal, js(log), int(wait_seconds * 1000))


def type_edit_runner(manifest_path, data):
    base = manifest_path.parent
    log = resolved(base, data.get('log', 'photoshop-type-edit-batch.log'), 'log')
    rows = []
    for job in data['jobs']:
        psd = resolved(base, job.get('psd'), 'psd', must_exist=True)
        type_log = resolved(base, job.get('typeLog', str(psd.with_name('photoshop-type-edit-test.txt'))), 'typeLog')
        rows.append({'name': job['name'], 'psd': psd, 'typeLog': type_log})
    literal = '[' + ','.join(
        '{name:%s,psd:%s,typeLog:%s}' % (js(r['name']), js(r['psd']), js(r['typeLog'])) for r in rows
    ) + ']'
    return """#target photoshop
(function(){
 var jobs=%s,previous=app.documents.length?app.activeDocument:null,oldDialogs=app.displayDialogs,failed=[],batchLog=new File(%s);
 app.displayDialogs=DialogModes.NO;batchLog.encoding='UTF8';batchLog.open('w');batchLog.close();
 function write(file,text){file.encoding='UTF8';file.open('w');file.writeln(text);file.close();}
 function batch(text){batchLog.open('a');batchLog.writeln(new Date().toUTCString()+' '+text);batchLog.close();}
 function findType(group){for(var i=0;i<group.layers.length;i++){var layer=group.layers[i];if(layer.typename==='LayerSet'){var nested=findType(layer);if(nested)return nested;}else if(layer.kind===LayerKind.TEXT)return layer;}return null;}
 function must(value,message){if(!value)throw Error(message);}
 function undo(){executeAction(charIDToTypeID('undo'),undefined,DialogModes.NO);}
 for(var i=0;i<jobs.length;i++){
  var job=jobs[i],doc=null,out=new File(job.typeLog);
  try{
   doc=app.open(new File(job.psd));var layer=findType(doc);must(layer,'No native type layer');doc.activeLayer=layer;
   var contents=layer.textItem.contents,size=layer.textItem.size.as('pt'),font=layer.textItem.font;
   layer.textItem.contents=contents+' test';must(layer.textItem.contents===contents+' test','Text edit did not commit');undo();must(layer.textItem.contents===contents,'Text undo failed');
   layer.textItem.size=UnitValue(size*2,'pt');must(Math.abs(layer.textItem.size.as('pt')-size*2)<.01,'Type enlargement failed');app.refresh();undo();must(Math.abs(layer.textItem.size.as('pt')-size)<.01,'Type enlargement undo failed');
   write(out,'PASS Photoshop '+app.version+' native type edit/undo and 2x size/undo; font='+font+'; originalSize='+size+'pt; layer='+layer.name);batch('PASS '+job.name);
  }catch(error){write(out,'FAILED '+error);failed.push(job.name+': '+error);batch('FAILED '+job.name+' '+error);}
  if(doc)doc.close(SaveOptions.DONOTSAVECHANGES);
 }
 app.displayDialogs=oldDialogs;if(previous){try{app.activeDocument=previous;}catch(ignore){}}
 if(failed.length)throw Error('Type edit validation failed: '+failed.join(' | '));
})();
""" % (literal, js(log))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--mode', required=True, choices=('rebuild', 'type-edit'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest_path, data = load_manifest(args.manifest)
    source = rebuild_runner(manifest_path, data) if args.mode == 'rebuild' else type_edit_runner(manifest_path, data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source, encoding='utf-8-sig')
    print(json.dumps({'mode': args.mode, 'jobs': len(data['jobs']), 'output': str(args.output.resolve())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
