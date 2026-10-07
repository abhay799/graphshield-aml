import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const s=JSON.parse(process.argv[1]),ctx={TextDecoder,TextEncoder,Uint8Array,ArrayBuffer};
vm.runInNewContext(fs.readFileSync('ui/portfolio/batch-scoring.js','utf8'),ctx);
const B=ctx.GraphShieldBatch;
const fields=['transaction_id','event_ts','from_bank','from_account','to_bank','to_account',
 'amount_paid','amount_received','payment_currency','receiving_currency','payment_format'];
const row=(id='TX1',ts='2026-10-07T12:00:00Z')=>[id,ts,'BANK_A','000123','BANK_B','000456','100','100','US Dollar','US Dollar','ACH'];
function csv(rows=[row()],heads=fields){return [heads,...rows].map(r=>r.map(x=>/[",\r\n]/.test(x)?'"'+x.replaceAll('"','""')+'"':x).join(',')).join('\n');}
function parse(text){return B.parse(text);}
function fails(text,match){assert.throws(()=>parse(text),new RegExp(match));}
const good=id=>({transaction_id:id,raw_model_score:0,calibrated_score:0});
async function tick(){await Promise.resolve();await Promise.resolve();}
(async()=>{
 if(s.kind==='parse'){
  let heads=[...fields],r=row(),text;
  if(s.field)r[fields.indexOf(s.field)]=s.value;
  if(s.mode==='missing')heads.pop();
  if(s.mode==='extra'){heads.push('comment');r.push('ignored');}
  if(s.mode==='label'){heads.push(s.value||'is_laundering');r.push('1');}
  if(s.mode==='duplicate_header')heads.push('transaction_id');
  if(s.mode==='empty_header')heads.push('');
  if(s.mode==='columns'){heads.push(...Array.from({length:22},(_,i)=>'extra'+i));r.push(...Array(22).fill('x'));}
  if(s.mode==='cell')r[0]='x'.repeat(1025);
  if(s.mode==='column_boundary'){heads.push(...Array.from({length:21},(_,i)=>'extra'+i));r.push(...Array(21).fill('x'));}
  if(s.mode==='cell_boundary')r[0]='x'.repeat(1024);
  text=csv([r],heads);
  if(s.mode==='bom')text='﻿'+text;
  if(s.mode==='crlf')text=text.replaceAll('\n','\r\n');
  if(s.mode==='newline')text+='\n\n';
  if(s.mode==='unterminated')text=fields.join(',')+'\n"bad';
  if(s.mode==='malformed')text=fields.join(',')+'\nbad"quote';
  if(s.mode==='trailing_quote')text=fields.join(',')+'\n"bad"x';
  if(s.mode==='count')text=fields.join(',')+'\nTX,one';
  if(s.mode==='delimiter')text=fields.join(',')+'\n'+','.repeat(10);
  if(s.mode==='reorder'){heads.reverse();text=csv([[...r].reverse()],heads);}
  if(s.mode==='duplicate')text=csv([row('TX'),row(' TX ')]);
  if(s.mode==='order')text=csv([row('A','2026-10-07T12:00:01Z'),row('B')]);
  if(s.mode==='equal')text=csv([row('A'),row('B')]);
  if(s.mode==='offset_order')text=csv([row('A','2026-10-07T12:00:00+05:30'),row('B','2026-10-07T07:00:00Z')]);
  if(s.mode==='micro_order')text=csv([row('A','2026-10-07T12:00:00.000002Z'),row('B','2026-10-07T12:00:00.000001Z')]);
  if(s.mode==='rows')text=csv(Array.from({length:s.count},(_,i)=>row('TX'+i)));
  if(s.error){fails(text,s.error);return;}
  const d=parse(text);
  if(s.invalid){assert.ok(d.rows.every(r=>r.errors.length));return;}
  if(s.blocked){assert.ok(d.orderError);assert.equal(d.rows.length,2);return;}
  assert.equal(d.orderError,'');assert.ok(d.rows.every(r=>r.errors.length===0));
  assert.equal(d.rows.length,s.count||((s.mode==='equal'||s.mode==='offset_order')?2:1));
  assert.equal(d.rows[0].payload.from_account,'000123');
  assert.equal(Object.keys(d.rows[0].payload).length,11);
  if(s.mode==='extra')assert.deepEqual(Array.from(d.ignored),['comment']);
  if(s.field)assert.equal(d.rows[0].payload[s.field],
   s.field.startsWith('amount_')?Number(s.value):s.value.trim());
  if(s.mode==='equal')assert.deepEqual(Array.from(d.rows,r=>r.payload.transaction_id),['A','B']);
  return;
 }
 if(s.kind==='file'){
  let read=false;
  const content=csv();
  const bytes=new TextEncoder().encode(s.size===262144?content+"\n".repeat(262144-content.length):content);
  const f={name:s.name||'demo.csv',size:s.size||bytes.length,arrayBuffer:async()=>{read=true;return (s.invalidUTF8?new Uint8Array([255]):bytes).buffer;}};
  if(s.error){await assert.rejects(()=>B.readFile(f),new RegExp(s.error));if(s.noRead)assert.equal(read,false);}
  else {assert.equal((await B.readFile(f)).rows.length,1);assert.equal(read,true);}
  return;
 }
 if(s.kind==='queue'){
  let active=false,uncertain=false,release,calls=[],notifications=[];
  const guard={acquire(){if(active||uncertain)return false;active=true;return true;},
   release(u){active=false;uncertain=!!u;}};
  const c=B.createController({...guard,request:async(base,payload)=>{
   calls.push({base,payload});
   return await new Promise((resolve,reject)=>{release={resolve,reject};});
  },notify(){notifications.push(c.snapshot().running);}});
  c.load(parse(csv([row('A'),row('B'),row('C')])));
  if(s.mode==='invalid'){const r=row('A');r[6]='bad';c.load(parse(csv([r,row('B')])));assert.equal(c.select(0),false);assert.equal(c.select(1),true);return;}
  if(s.mode==='guard'){active=true;await c.run('all','http://api');assert.equal(calls.length,0);return;}
  c.select(0);const run=c.run(s.mode==='selected'?'selected':'all','http://api');
  await tick();assert.equal(calls.length,1);assert.equal(c.snapshot().running,true);
  assert.equal(c.snapshot().rows[0].state,'Submitting');
  assert.equal(c.select(1),false);assert.equal(c.clear(),false);
  await c.run('all','http://other');assert.equal(calls.length,1);
  if(s.mode==='stop')c.stop();
  if(s.mode==='network'||s.mode==='timeout')release.reject(Object.assign(new Error('connection'),{name:s.mode==='timeout'?'AbortError':'NetworkError'}));
  else if(s.mode==='http')release.resolve({response:{ok:false,status:400},data:{detail:'bad timestamp'}});
  else if(s.mode==='malformed')release.resolve({response:{ok:true,status:200},data:{transaction_id:'A',raw_model_score:null,calibrated_score:0}});
  else if(s.mode==='mismatch')release.resolve({response:{ok:true,status:200},data:good('OTHER')});
  else release.resolve({response:{ok:true,status:200},data:good('A')});
  await tick();
  if(['stop','selected','network','timeout','http','malformed','mismatch'].includes(s.mode)){
   await run;assert.equal(calls.length,1);assert.equal(c.snapshot().running,false);
   const first=c.snapshot().rows[0];
   if(['network','timeout'].includes(s.mode)){assert.equal(first.state,'Completion unknown');assert.ok(uncertain);await c.run('all','http://api');assert.equal(calls.length,1);}
   else if(['http','malformed','mismatch'].includes(s.mode)){assert.equal(first.state,'Failed');assert.equal(first.result,null);}
   else {assert.equal(first.state,'Completed');assert.equal(first.result.calibrated_score,0);}
   if(s.mode==='stop'){
    assert.equal(c.snapshot().rows[1].state,'Not submitted');
    const resume=c.run('all','http://api');await tick();assert.equal(calls.length,2);assert.equal(calls[1].payload.transaction_id,'B');
    c.stop();release.resolve({response:{ok:true,status:200},data:good('B')});await resume;
    assert.equal(c.snapshot().rows[0].state,'Completed');
   }
   return;
  }
  assert.equal(calls.length,2);assert.equal(calls[1].payload.transaction_id,'B');
  assert.equal(c.snapshot().rows[0].state,'Completed');
  if(s.mode==='second_failure'){
   release.resolve({response:{ok:false,status:500},data:null});await run;
   assert.equal(calls.length,2);assert.equal(c.snapshot().rows[0].state,'Completed');
   assert.equal(c.snapshot().rows[1].state,'Failed');
   assert.equal(c.snapshot().rows[2].state,'Not submitted');return;
  }
  release.resolve({response:{ok:true,status:200},data:good('B')});await tick();
  assert.equal(calls.length,3);release.resolve({response:{ok:true,status:200},data:good('C')});await run;
  assert.ok(c.snapshot().rows.every(r=>r.state==='Completed'));assert.equal(active,false);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


CASES = [
    {"kind": "parse"},
    *[{"kind": "parse", "mode": mode} for mode in
      ("extra", "bom", "crlf", "newline", "reorder", "equal", "offset_order",
       "column_boundary", "cell_boundary")],
    *[{"kind": "parse", "field": "from_bank", "value": value}
      for value in ('Bank, synthetic', 'Bank\nsynthetic', 'Bank "synthetic"', ' Bank ')],
    *[{"kind": "parse", "field": "event_ts", "value": value}
      for value in ("2026-10-07T12:00:00Z", "2026-10-07T12:00:00+05:30",
                    "2026-10-07T12:00:00.123456", "2024-02-29T12:00:00Z")],
    *[{"kind": "parse", "mode": mode, "error": error}
      for mode, error in (("missing", "Missing"), ("label", "label"),
                          ("duplicate_header", "Duplicate header"),
                          ("empty_header", "Empty header"), ("columns", "32"),
                          ("cell", "1024"), ("unterminated", "quot"),
                          ("malformed", "quot"), ("trailing_quote", "quot"),
                          ("count", "column"))],
    *[{"kind": "parse", "field": "amount_paid", "value": value, "invalid": True}
      for value in ("", "NaN", "Infinity", "-1", "0x10", "$100", "1,000", "1e309")],
    *[{"kind": "parse", "field": "event_ts", "value": value, "invalid": True}
      for value in ("2026-02-29T12:00:00Z", "2026-04-31T12:00:00Z",
                    "2026-10-07T24:00:00Z", "2026-10-07T12:00:60Z",
                    "2026-10-07T12:00:00+24:00", "not-a-date")],
    *[{"kind": "parse", "mode": mode, "invalid": True}
      for mode in ("duplicate", "delimiter")],
    *[{"kind": "parse", "mode": mode, "blocked": True} for mode in ("order", "micro_order")],
    {"kind": "parse", "mode": "rows", "count": 100},
    {"kind": "parse", "mode": "rows", "count": 101, "error": "100"},
    *[{"kind": "parse", "field": field, "value": " ", "invalid": True}
      for field in ("transaction_id", "from_bank", "from_account", "to_bank",
                    "to_account", "payment_currency", "receiving_currency", "payment_format")],
    *[{"kind": "parse", "field": "amount_paid", "value": value}
      for value in ("0", "123.45")],
    *[{"kind": "parse", "field": "event_ts", "value": value, "invalid": True}
      for value in ("2026-10-07T12:60:00Z", "2026-10-07T12:00:00+05:60")],
    {"kind": "parse", "mode": "label", "value": "IS_LAUNDERING", "error": "label"},
    {"kind": "file"},
    {"kind": "file", "size": 262144},
    {"kind": "file", "size": 262145, "error": "256", "noRead": True},
    {"kind": "file", "invalidUTF8": True, "error": "UTF-8"},
    {"kind": "file", "name": "data.txt", "error": "CSV", "noRead": True},
    *[{"kind": "queue", "mode": mode}
      for mode in ("sequential", "second_failure", "selected", "invalid", "guard", "stop", "network",
                   "timeout", "http", "malformed", "mismatch")],
]


@pytest.mark.parametrize("scenario", CASES)
def test_batch_parser_and_execution(scenario):
    node = shutil.which("node")
    assert node, "Node.js is required for browser-script checks"
    result = subprocess.run(
        [node, "-e", HARNESS, json.dumps(scenario)], capture_output=True, text=True, timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_batch_surface_privacy_and_template_contract():
    html = Path("ui/portfolio/index.html").read_text(encoding="utf-8")
    js = Path("ui/portfolio/batch-scoring.js").read_text(encoding="utf-8")
    for text in ("Upload Transaction Dataset", "Use only synthetic or anonymized",
                 "UPI IDs", "government identifiers", "Redis runtime history",
                 "Stop after current request", "Score selected row",
                 "Score all valid rows", "Download CSV Template"):
        assert text in html
    for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie",
                      "console.log", 'split(",")'):
        assert forbidden not in js
    assert 'aria-live="polite"' in html
    assert 'id="batch-file"' in html
    assert 'src="batch-scoring.js"' in html
PAGE_HARNESS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const mode=process.argv[1],elements={},calls=[],timers=[];
let ready, resolveRequest, pendingRead, downloaded, blob, revoked;
function el(id){return elements[id]??=( {value:'',disabled:false,innerHTML:'',textContent:'',
 attrs:{},listeners:{},addEventListener(k,fn){this.listeners[k]=fn;},
 setAttribute(k,v){this.attrs[k]=v;}});}
let focusRestored=false;
const document={activeElement:{dataset:{}},querySelector(){return {disabled:false,focus(){focusRestored=true;}};},
 getElementById:el,addEventListener(k,fn){ready=fn;},
 createElement(tag){return {innerHTML:'',get textContent(){return this.innerHTML.replace(/<[^>]*>/g,'');},
 click(){downloaded=this.download;}};}};
el('scoring-api-base').value='http://127.0.0.1:8000';
const values={transaction_id:'MANUAL',event_ts:'2026-10-07T12:00:00Z',
 from_bank:'BANK',from_account:'0001',to_bank:'BANK',to_account:'0002',
 amount_paid:'1',amount_received:'1',payment_currency:'USD',receiving_currency:'USD',payment_format:'ACH'};
class TestURL extends URL {}
TestURL.createObjectURL=x=>{blob=x;return 'blob:local-template';};
TestURL.revokeObjectURL=x=>{revoked=x;};
const ctx={document,URL:TestURL,Blob,TextDecoder,TextEncoder,Uint8Array,ArrayBuffer,AbortController,
 FormData:class{get(k){return values[k];}},
 setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout(){},
 fetch:async(url,options)=>{calls.push({url,options});return await new Promise((resolve,reject)=>{
  resolveRequest=(body,status=200)=>resolve({ok:status===200,status,json:async()=>body});
  options.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'})));
 });}};
vm.runInNewContext(fs.readFileSync('ui/portfolio/batch-scoring.js','utf8'),ctx);
vm.runInNewContext(fs.readFileSync('ui/portfolio/live-scoring.js','utf8'),ctx);
ready();
const csv=ctx.GraphShieldBatch.template+
 'A,2026-10-07T12:00:00Z,BANK,0001,BANK,0002,1,1,USD,USD,ACH,ignored\n'+
 'B,2026-10-07T12:00:01Z,BANK,0001,BANK,0002,1,1,USD,USD,ACH,ignored\n';
const withExtra=csv.replace('payment_format\r\n','payment_format,comment\r\n');
const file={name:'test.csv',size:withExtra.length,arrayBuffer:async()=>new TextEncoder().encode(withExtra).buffer};
async function tick(){for(let i=0;i<8;i++)await Promise.resolve();}
function success(id){return {transaction_id:id,raw_model_score:0,calibrated_score:0};}
async function load(){await el('batch-file').listeners.change({target:{files:[file]}});}
(async()=>{
 if(mode==='template'){
  el('batch-template').listeners.click();assert.equal(await blob.text(),ctx.GraphShieldBatch.template);
  assert.equal(ctx.GraphShieldBatch.template.trim().split(',').length,11);
  assert.ok(downloaded.endsWith('.csv'));assert.equal(revoked,'blob:local-template');assert.equal(calls.length,0);return;
 }
 if(mode==='race'){
  const slow={...file,arrayBuffer:()=>new Promise(r=>{pendingRead=r;})};
  const loading=el('batch-file').listeners.change({target:{files:[slow]}});
  el('batch-clear').listeners.click();pendingRead(new TextEncoder().encode(withExtra).buffer);await loading;
  assert.ok(el('batch-summary').textContent.startsWith('0 total'));assert.equal(calls.length,0);return;
 }
 await load();assert.ok(el('batch-summary').textContent.includes('2 valid'));
 assert.ok(el('batch-ignored').textContent.includes('comment'));assert.equal(calls.length,0);
 if(mode==='manual'){
  const promise=el('live-scoring-form').listeners.submit({preventDefault(){},currentTarget:el('live-scoring-form')});
  await tick();assert.equal(calls.length,1);assert.equal(el('batch-all').disabled,true);
  assert.equal(el('batch-file').disabled,true);
  el('batch-all').listeners.click();assert.equal(calls.length,1);
  resolveRequest(success('MANUAL'));await promise;assert.equal(el('batch-all').disabled,false);
  return;
 }
 document.activeElement={dataset:{row:'0'}};
 el('batch-body').listeners.change({target:{dataset:{row:'0'}}});
 assert.ok(focusRestored,'Restore native selection focus after table rendering');
 el('batch-all').listeners.click();await tick();
 assert.equal(calls.length,1);assert.equal(el('score-submit').disabled,true);
 assert.equal(el('scoring-api-base').disabled,true);assert.equal(el('batch-file').disabled,true);
 await el('live-scoring-form').listeners.submit({preventDefault(){},currentTarget:el('live-scoring-form')});
 el('batch-all').listeners.click();assert.equal(calls.length,1);
 const payload=JSON.parse(calls[0].options.body);
 assert.equal(Object.keys(payload).length,11);assert.equal(payload.comment,undefined);
 assert.equal(calls[0].options.method,'POST');assert.equal(payload.from_account,'0001');
 if(mode==='timeout'){
  timers[0].fn();await tick();
  assert.ok(el('batch-body').innerHTML.includes('Completion unknown'));
  assert.equal(el('score-submit').disabled,true);assert.equal(el('batch-all').disabled,true);
  assert.ok(el('batch-body').innerHTML.includes('Redis'));assert.equal(calls.length,1);return;
 }
 el('batch-stop').listeners.click();
 const data=mode==='xss'?{...success('A'),boundary_note:'<img src=x>',
  feature_breakdown:{history:{signal:'<script>x</script>'}}}:success('A');
 resolveRequest(data);await tick();
 assert.equal(calls.length,1);assert.equal(el('score-submit').disabled,false);
 assert.ok(el('batch-body').innerHTML.includes('Completed'));assert.ok(el('batch-body').innerHTML.includes('Not submitted'));
 assert.ok(el('batch-body').innerHTML.includes('Unavailable'));
 assert.ok(el('batch-detail').innerHTML.includes('class="score-value">0</div>'));
 if(mode==='xss'){assert.ok(el('batch-detail').innerHTML.includes('&lt;img'));assert.ok(!el('batch-detail').innerHTML.includes('<script>x'));}
 if(mode==='reload'){
  await load();assert.ok(el('batch-body').innerHTML.includes('already submitted'));
  assert.ok(el('batch-summary').textContent.includes('1 invalid'));return;
 }
 el('batch-body').listeners.change({target:{dataset:{row:'1'}}});
 el('batch-selected').listeners.click();await tick();assert.equal(calls.length,2);
 assert.equal(JSON.parse(calls[1].options.body).transaction_id,'B');
 resolveRequest(success('B'));await tick();
 assert.ok(el('batch-body').innerHTML.includes('Completed'));assert.equal(el('batch-all').disabled,true);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


@pytest.mark.parametrize("mode", ["template", "race", "manual", "batch", "timeout", "xss", "reload"])
def test_batch_page_with_actual_live_scoring_script(mode):
    result = subprocess.run(
        [shutil.which("node"), "-e", PAGE_HARNESS, mode],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr