from pathlib import Path
from datetime import datetime,timezone
import json,time,urllib.request,statistics,uuid
root=Path('/home/cyberdid/Projects/B-12/benchmarks/bolt-e4b-smoke-2026-10-24')
out=root/('prefill-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
rows=[]
for count in [20,60,120]:
 for repeat in range(3):
  text='\n'.join(f'Запис {i}: це синтетичні дані для вимірювання.' for i in range(count))
  request={'model':'b12-bolt-e4b:q4km','messages':[{'role':'system','content':f'Тест {uuid.uuid4()}. Відповідай українською. На прохання підтвердити готовність повертай лише слово ГОТОВО.'},{'role':'user','content':'Прочитай синтетичні записи й підтверди готовність одним словом.\n'+text}], 'stream':True,'think':False,'keep_alive':'5m','options':{'num_ctx':2048,'num_predict':32,'temperature':0,'seed':42,'draft_num_predict':0}}
  row={'lines':count,'repeat':repeat+1,'request':request,'started_utc':datetime.now(timezone.utc).isoformat()};chunks=[];first=None;final=None;t=time.perf_counter()
  req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=120) as response,(out/f'{count}-{repeat+1}.stream.jsonl').open('w') as stream:
   for line in response:
    item=json.loads(line);elapsed=time.perf_counter()-t
    if 'error' in item:raise RuntimeError(item['error'])
    msg=item.get('message',{})
    if 'thinking' in msg:msg['thinking_chars_redacted']=len(msg.pop('thinking'))
    stream.write(json.dumps({'elapsed_s':elapsed,'response':item},ensure_ascii=False)+'\n')
    content=msg.get('content','');chunks.append(content)
    if first is None and content.strip():first=elapsed
    if item.get('done'):final=item
  if final is None:raise RuntimeError('No terminal response')
  row.update({'content':''.join(chunks),'ttft_content_s':first,'wall_s':time.perf_counter()-t,'metrics':{k:v for k,v in final.items() if k.endswith('_duration') or k.endswith('_count')},'done_reason':final.get('done_reason')})
  rows.append(row)
  with (out/'results.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print(json.dumps({k:row[k] for k in ['lines','repeat','ttft_content_s','content','metrics']},ensure_ascii=False),flush=True)
summary={'model':'b12-bolt-e4b:q4km','purpose':'Warm runtime, unique system prefix per request to reduce prompt-cache reuse; actual cached token counts recorded; synthetic Ukrainian text; no audio.','groups':[]}
for count in [20,60,120]:
 group=[r for r in rows if r['lines']==count]
 summary['groups'].append({'synthetic_lines':count,'n':len(group),'input_tokens':[r['metrics'].get('prompt_eval_count') for r in group],'cached_tokens':[r['metrics'].get('prompt_eval_cached_count') for r in group],'ttft_content_p50_s':statistics.median(r['ttft_content_s'] for r in group),'ttft_content_min_s':min(r['ttft_content_s'] for r in group),'ttft_content_max_s':max(r['ttft_content_s'] for r in group)})
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print('OUTPUT',out,flush=True)
print(json.dumps(summary,ensure_ascii=False),flush=True)
