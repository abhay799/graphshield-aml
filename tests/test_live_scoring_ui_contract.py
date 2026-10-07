import json
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path("ui/portfolio/index.html").read_text(encoding="utf-8")
JS = Path("ui/portfolio/live-scoring.js").read_text(encoding="utf-8")
SURFACE = HTML + "\n" + JS


def test_live_scoring_form_contract():
    assert 'id="live-scoring"' in HTML
    assert 'id="live-scoring-form"' in HTML
    for field in (
        "transaction_id",
        "event_ts",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_paid",
        "amount_received",
        "payment_currency",
        "receiving_currency",
        "payment_format",
    ):
        assert f'name="{field}"' in HTML


def test_live_scoring_ui_safety_and_result_contract():
    lower = SURFACE.lower()
    assert "synthetic-data research scoring" in lower
    assert "not real fraud detection" in lower
    assert "first-time/unknown accounts have structurally limited signal" in lower
    assert "https://graphshield-api-production.up.railway.app" in SURFACE
    assert "/score/transaction" in SURFACE
    assert "limited_signal" in SURFACE
    assert "boundary_note" in SURFACE
    assert "feature_breakdown" in SURFACE
    assert "public research demo" in lower


def test_live_scoring_metadata_and_safety_contract():
    for field in ("transaction_id", "scoring_mode", "boundary",
                  "synthetic_research_demo_only", "canonical_artifacts_modified"):
        assert field in JS
    assert 'typeof value === "number"' in JS
    assert 'typeof value === "boolean"' in JS
    assert "Number(data.calibrated_score)" not in JS
    assert "UI explanation derived from account_history" in JS
    for phrase in ("research / portfolio decision-support platform",
                   "public or synthetic data", "human review",
                   "production fraud-detection", "block transactions",
                   "close cases", "file regulatory reports",
                   "replace legal/compliance judgment"):
        assert phrase in HTML


def test_live_scoring_request_health_and_accessibility_contract():
    assert "AbortController" in JS
    assert "25000" in JS
    assert "if (scoringActive) return" in JS
    assert 'base + "/health"' in JS
    assert 'method: "GET"' in JS
    assert "Array.isArray(data?.detail)" in JS
    assert "does not guarantee that an individual scoring request will succeed" in HTML
    assert "Backend model inputs used for this scoring request." in JS
    assert 'aria-describedby="score-event-ts-help"' in HTML


# The actual browser script runs with DOM/transport adapters; no API/Redis writes.
NODE_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const scenario = JSON.parse(process.argv[1]);
const elements = {};
function element(id) {
  return elements[id] ||= {innerHTML:'',value:'',disabled:false,textContent:'',
    listeners:{},attrs:{},addEventListener(k,fn){this.listeners[k]=fn;},
    setAttribute(k,v){this.attrs[k]=v;}};
}
['live-scoring-form','live-scoring-results','score-submit','scoring-api-base',
 'scoring-health-check','scoring-health-results'].forEach(element);
element('scoring-api-base').value = 'http://127.0.0.1:8123/';
const fields = ['transaction_id','event_ts','from_bank','from_account','to_bank',
 'to_account','amount_paid','amount_received','payment_currency','receiving_currency','payment_format'];
const input = Object.fromEntries(fields.map(k=>[k,'demo']));
input.event_ts='2026-10-07T12:00:00+05:30';input.amount_paid='1000.25';
input.amount_received='1000';input.frontend_only='must not be sent';
const valid={transaction_id:'DEMO_RESPONSE',calibrated_score:0.02738545245606547,
 raw_model_score:0.9999999999996636,scoring_mode:'live_research_only',
 boundary:'synthetic_research_demo_only',boundary_note:'Backend boundary <safe>',
 synthetic_research_demo_only:true,account_history:{sender:'known',receiver:'known'},
 limited_signal:false,limitation_note:null,runtime_state_updated:true,
 canonical_artifacts_modified:false,feature_breakdown:{history:{prior_count:null}}};
const calls=[],timers=[];let ready,release;
const context={console,AbortController,URL,
 document:{getElementById:element,addEventListener(k,fn){ready=fn;}},
 FormData:class {get(k){return input[k]??null;}
   forEach(fn){Object.entries(input).forEach(([k,v])=>fn(v,k));}},
 setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout(){},
 fetch:async(url,options={})=>{
   calls.push({url,options});
   if(scenario.kind==='network')throw new TypeError('Failed to fetch');
   if(scenario.kind==='timeout')return new Promise((resolve,reject)=>{
     options.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'})));});
   if(scenario.kind==='duplicate')await new Promise(resolve=>{release=resolve;});
   const body=['health','http'].includes(scenario.kind)?scenario.body:{...valid,...scenario.patch};
   for (const key of scenario.remove || []) delete body[key];
   return {ok:!scenario.status,status:scenario.status||200,async json(){
     if(scenario.kind==='invalid_json')throw new SyntaxError();return body;}};
 }};
vm.runInNewContext(fs.readFileSync('ui/portfolio/live-scoring.js','utf8'),context);
ready();
(async()=>{
 const health=scenario.kind==='health',form=element('live-scoring-form');
 const event={preventDefault(){},currentTarget:form};
 const promise=health?element('scoring-health-check').listeners.click():form.listeners.submit(event);
 if(scenario.kind==='duplicate'){
   assert.equal(element('score-submit').disabled,true);
   await form.listeners.submit(event);assert.equal(calls.length,1);release();}
 if(scenario.kind==='timeout'){assert.equal(timers[0].ms,25000);timers[0].fn();}
 await promise;
 assert.equal(calls.length,1,'Never automatically retry a request');
 assert.equal(calls[0].url,'http://127.0.0.1:8123/'+(health?'health':'score/transaction'));
 assert.equal(calls[0].options.method,health?'GET':'POST');
 if(!health){
   const payload=JSON.parse(calls[0].options.body);
   assert.deepEqual(Object.keys(payload).sort(),fields.sort());
   assert.equal(payload.event_ts,input.event_ts);assert.equal(payload.amount_paid,1000.25);
   assert.equal(element('score-submit').disabled,false);
   assert.equal(element('live-scoring-results').attrs['aria-busy'],'false');}
 const html=element(health?'scoring-health-results':'live-scoring-results').innerHTML;
 for(const text of scenario.includes||[])assert.ok(html.includes(text),text+'\n'+html);
 for(const text of scenario.excludes||[])assert.ok(!html.includes(text),text+'\n'+html);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


@pytest.mark.parametrize("scenario", [
    {"includes": ["DEMO_RESPONSE", "live_research_only", "synthetic_research_demo_only",
                  "canonical_artifacts_modified", "false", "Backend boundary &lt;safe&gt;",
                  "Warm-state context", "UI explanation derived from account_history",
                  "Null (missing)", "0.02738545245606547"]},
    {"patch": {"scoring_mode": None, "boundary": {}, "synthetic_research_demo_only": "true",
               "canonical_artifacts_modified": None, "runtime_state_updated": None,
               "limited_signal": None, "account_history": {}},
     "includes": ["Unavailable"], "excludes": ["Warm-state context", "Redis updated"]},
    {"patch": {"account_history": {"sender": "unknown", "receiver": "known"},
               "limited_signal": True, "limitation_note": "First-time <account>"},
     "includes": ["Limited-history / cold-start context", "First-time &lt;account&gt;"]},
    {"patch": {"limited_signal": False, "limitation_note": "Never invent this warning"},
     "excludes": ["limited-signal-warning", "Never invent this warning"]},
    *[{"patch": {field: value}, "includes": ["Unexpected API response"],
       "excludes": ['class="score-value"', "GS_ALLOWED_ORIGINS"]}
      for field, value in [("calibrated_score", None), ("calibrated_score", "0.1"),
                           ("raw_model_score", None), ("raw_model_score", 2),
                           ("transaction_id", None)]],
    {"patch": {"calibrated_score": 0, "raw_model_score": 0},
     "includes": ['class="score-value">0</div>']},
    *[{"remove": [field], "includes": [field + "</span><strong>Unavailable"]}
      for field in ("scoring_mode", "boundary", "synthetic_research_demo_only",
                    "canonical_artifacts_modified", "runtime_state_updated", "limited_signal")],
    {"remove": ["boundary_note"], "includes": ["boundary_note:</strong> Unavailable"]},
    {"patch": {"canonical_artifacts_modified": True},
     "includes": ["canonical_artifacts_modified</span><strong>true"]},
    {"patch": {"account_history": {"sender": "bad", "receiver": None},
               "limited_signal": "false"},
     "includes": ["Account-history context: Unavailable", "limited_signal</span><strong>Unavailable"],
     "excludes": ["Warm-state context"]},
    {"patch": {"limited_signal": True, "limitation_note": None},
     "includes": ["limitation_note</strong><p>Unavailable"]},
    {"patch": {"transaction_id": "<img src=x onerror=alert(1)>",
               "feature_breakdown": {"transaction": {"amount_paid": 0},
                                     "pass_through": {"signal": "<script>bad</script>"}}},
     "includes": ["&lt;img", "&lt;script&gt;bad&lt;/script&gt;", "amount_paid"],
     "excludes": ["<img src=x", "<script>bad"]},
    {"kind": "invalid_json", "includes": ["Unexpected API response"]},
    {"kind": "http", "status": 400, "body": {"detail": "Invalid timestamp <input>"},
     "includes": ["Invalid timestamp &lt;input&gt;"], "excludes": ["GS_ALLOWED_ORIGINS"]},
    {"kind": "http", "status": 422, "body": {"detail": [
        {"loc": ["body", "event_ts"], "msg": "Field required"},
        {"loc": ["body", "amount_paid"], "msg": "Input should be a valid number"}]},
     "includes": ["event_ts: Field required", "amount_paid: Input should be a valid number"],
     "excludes": ["[object Object]", "GS_ALLOWED_ORIGINS"]},
    {"kind": "http", "status": 500, "body": None,
     "includes": ["Server/scoring failure", "500"], "excludes": ["GS_ALLOWED_ORIGINS"]},
    {"kind": "network", "includes": ["Connection failed", "GS_ALLOWED_ORIGINS"]},
    {"kind": "timeout", "includes": ["25 seconds", "not retried", "Redis"],
     "excludes": ["GS_ALLOWED_ORIGINS"]},
    {"kind": "duplicate", "includes": ["DEMO_RESPONSE"]},
    {"kind": "health", "body": {"status": "ok", "service": "GraphShield AML",
        "mode": "read_only", "champion": "lightgbm_graph", "phase_1_6_artifacts": "frozen",
        "scoring_mode": "live_research_only", "scoring_state": "redis_runtime_only",
        "synthetic_research_demo_only": True},
     "includes": ["read_only", "lightgbm_graph", "frozen", "live_research_only",
                  "redis_runtime_only", "synthetic_research_demo_only", "true"]},
    {"kind": "health", "body": {}, "includes": ["Unavailable"],
     "excludes": ["Redis ready", "Scorer ready"]},
])
def test_live_scoring_browser_script_behavior(scenario):
    node = shutil.which("node")
    assert node, "Node.js is required for browser-script regression checks"
    result = subprocess.run(
        [node, "-e", NODE_HARNESS, json.dumps(scenario)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
