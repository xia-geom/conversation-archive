"""Self-contained, offline review views; untrusted archive strings are text only."""
from __future__ import annotations
import base64
import hashlib
import html
import json

CSS = """
:root{font:16px/1.5 system-ui,sans-serif;color:#17212b;background:#f6f7f8}
*{box-sizing:border-box}h2,h3,p{overflow-wrap:anywhere}select,input{max-width:100%}body{max-width:1160px;margin:auto;padding:24px}h1{margin:0}header,p{margin-bottom:14px}
button,select,input,textarea{font:inherit;padding:8px;border:1px solid #aeb9c2;border-radius:5px;background:white}
button{cursor:pointer}button:disabled{cursor:default;opacity:.5}input[type=search]{min-width:230px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0;align-items:center}.card{background:white;border:1px solid #d8dfe4;border-radius:8px;padding:20px;margin:18px 0}
.evidence{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.witness{border-left:3px solid #98aabc;padding:0 14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}textarea{box-sizing:border-box;width:100%;min-height:60px}
.small{font-size:13px;color:#536271;overflow-wrap:anywhere}.notice{background:#fff8dd;padding:12px;border-radius:5px}.status{font-weight:600}summary{cursor:pointer}
@media(max-width:600px){body{padding:14px}.card{padding:14px}.evidence{grid-template-columns:1fr}.toolbar label{width:100%;min-width:0}.toolbar select,.toolbar input,.card select{width:100%}.witness{min-width:0}}
[hidden]{display:none!important}:focus-visible{outline:3px solid #216baa;outline-offset:2px}label{display:block;margin:10px 0}a{color:#145b94}
"""
JS = r"""
'use strict';
const data=JSON.parse(document.getElementById('review-data').textContent);
const entries=Object.fromEntries(data.entries.map(e=>[e.entry_id,e]));
const drafts=new Map(); let dirty=false,page=0;
const $=id=>document.getElementById(id);
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
const labels={confirm:'Confirm this relationship',reject:'Reject this relationship',insufficient:'Insufficient evidence',defer:'Defer; do not ask again until reopened',reopen:'Withdraw this decision and reopen',disagree:'The sources genuinely disagree (truth not decided)',different_events:'Different events or subjects',different_date_roles:'Different meanings of the dates',transcription_discrepancy:'A transcription discrepancy',corrected_report:'A corrected or superseding report'};
function status(q){if(q.blocked)return 'blocked';if(!q.current)return 'pending';if(q.current.choice==='defer')return 'deferred';if(q.current.choice==='insufficient')return 'waiting';return 'reviewed';}
function reply(){return {protocol:data.protocol,session_id:data.session_id,basis_snapshot_id:data.basis_snapshot_id,actor:$('actor').value,answers:data.questions.filter(q=>drafts.has(q.question_id)).map(q=>drafts.get(q.question_id))};}
function changes(q,choice,note){if(!choice)drafts.delete(q.question_id);else drafts.set(q.question_id,{question_id:q.question_id,choice,note,previous_rule_id:q.current?q.current.rule_id:null});dirty=true;updateCount();}
function updateCount(){$('draft-count').textContent=drafts.size+' explicit draft answers; nothing applied';}
function download(value,name){const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function card(q){
 const c=q.case,box=node('article',undefined,'card');box.id=q.question_id;
 box.append(node('h2',c.title),node('p',c.prompt),node('p','Why this case: '+c.reason),node('p',c.kind+' · '+status(q),'status'),node('p',q.question_id,'small'));
 if(c.kind==='identity')box.append(node('p','Optional identity question. This interface supports deferral/reopening, not identity grouping. It is not required to finish contradiction review.','notice'));
 if(q.current)box.append(node('p','Recorded answer: '+labels[q.current.choice]+(q.current.note?' — '+q.current.note:'')));
 if(q.blocked)box.append(node('p',q.blocked,'notice'));
 if(c.relation)box.append(node('p','Direction: '+c.source_entry_id+' → '+c.target_entry_id+' ('+c.relation+')'));
 if(c.depends_on.length)box.append(node('p','Recorded comparison dependencies: '+c.depends_on.join(', '),'small'));
 const ev=node('div',undefined,'evidence');
 for(const w of c.evidence){const e=entries[w.entry_id],panel=node('section',undefined,'witness');
  panel.append(node('h3',e.title||e.entry_id),node('pre',w.quote),node('p','Entry '+w.entry_id+' · Unicode character range ['+w.start+', '+w.end+')','small'));
  const metadata=data.metadata.filter(m=>m.entry_id===w.entry_id);if(metadata.length)panel.append(node('p',metadata.map(m=>m.field+': '+m.value).join('\n'),'small'));
  const refs=data.source_references.filter(r=>r.entry_id===w.entry_id);if(refs.length)panel.append(node('p','Stored source references: '+refs.map(r=>r.source_ref).join(', '),'small'));
  const full=node('details');full.append(node('summary','Open complete preserved entry'),node('pre',e.raw_markdown));panel.append(full);ev.append(panel);
 }box.append(ev);
 const choice=node('select');choice.setAttribute('aria-label','Decision for '+q.question_id);choice.append(new Option('No answer selected',''));
 for(const value of q.choices){if(value==='reopen'&&!q.current)continue;const opt=new Option(labels[value],value);if(q.blocked&&!['defer','reopen'].includes(value))opt.disabled=true;choice.append(opt);}
 const note=node('textarea');note.setAttribute('aria-label','Explanation for '+q.question_id);note.placeholder='Optional explanation; this will be preserved as your answer, not added to the source text.';
 const draft=drafts.get(q.question_id);if(draft){choice.value=draft.choice;note.value=draft.note;}
 choice.addEventListener('change',()=>changes(q,choice.value,note.value));note.addEventListener('input',()=>{if(choice.value)changes(q,choice.value,note.value);});
 const lab=node('label','Your decision ');lab.append(choice);box.append(lab,note);return box;
}
function render(){
 const area=$('cards');area.replaceChildren();
 if($('view').value==='history'){
  for(const h of data.history){const b=node('article',undefined,'card');b.append(node('p',h.question_id,'small'),node('p',labels[h.choice]+' · '+(h.active?'active':'withdrawn')),node('p',h.note),node('p','Rule '+h.rule_id+' · Event '+h.event_id,'small'));area.append(b);}
  $('page-status').textContent=data.history.length+' historical answers';$('previous').disabled=true;$('next').disabled=true;return;
 }
 const query=$('search').value.toLocaleLowerCase();
 const rows=data.questions.filter(q=>{
  if($('view').value==='batch'&&(q.case.kind==='identity'||status(q)!=='pending'))return false;
  if($('kind').value&&q.case.kind!==$('kind').value)return false;
  if($('state').value&&status(q)!==$('state').value)return false;
  return (JSON.stringify(q.case)+' '+q.case.evidence.map(w=>entries[w.entry_id].title).join(' ')).toLocaleLowerCase().includes(query);
 });
 const size=Number($('size').value);page=Math.min(page,Math.max(0,Math.ceil(rows.length/size)-1));
 for(const q of rows.slice(page*size,(page+1)*size))area.append(card(q));
 if(!rows.length)area.append(node('p','No prepared questions match this view. This does not establish that your sources have no contradictions.','notice'));
 $('page-status').textContent=rows.length?('Questions '+(page*size+1)+'–'+Math.min(rows.length,(page+1)*size)+' of '+rows.length):'0 prepared questions';
 $('previous').disabled=page===0;$('next').disabled=(page+1)*size>=rows.length;
}
$('overview').textContent=data.coverage.snapshot_entries+' snapshot entries · '+data.questions.length+' prepared questions · '+data.coverage.conflict_cases+' supplied conflict cases · '+data.blocked.length+' blocked proposals';
$('coverage').textContent='Coverage: existing snapshot questions and explicitly supplied cases only. No automatic contradiction discovery; no certification against live Notes/chat apps or original medical PDFs. Entry quotations do not establish their interpretation.';
$('size').value=String(data.batch_size);
for(const id of ['view','kind','state','size'])$(id).addEventListener('change',()=>{page=0;render();});
$('search').addEventListener('input',()=>{page=0;render();});
$('previous').addEventListener('click',()=>{page--;render();});$('next').addEventListener('click',()=>{page++;render();});
$('actor').addEventListener('input',()=>{dirty=true;});
$('save').addEventListener('click',()=>{download({kind:'review-draft',reply:reply()},'review-draft.json');dirty=false;$('message').textContent='Draft downloaded. Saving a draft does not apply decisions.';});
$('export').addEventListener('click',()=>{if(!$('actor').value.trim()||!drafts.size){$('message').textContent='Enter a reviewer label and choose at least one answer.';return;}download(reply(),'review-answers.json');dirty=false;$('message').textContent='Answers exported. Run the checked preview, inspect preview.html, then apply explicitly.';});
$('restore').addEventListener('change',async event=>{try{
 const file=event.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('Draft is too large.');
 const loaded=JSON.parse(await file.text()),r=loaded.kind==='review-draft'?loaded.reply:loaded;
 if(r.protocol!==data.protocol||r.session_id!==data.session_id||r.basis_snapshot_id!==data.basis_snapshot_id||!Array.isArray(r.answers)||typeof r.actor!=='string')throw Error('This draft belongs to another session.');
 const pending=new Map();for(const a of r.answers){const q=data.questions.find(x=>x.question_id===a.question_id);
  if(!q||pending.has(a.question_id)||!q.choices.includes(a.choice)||typeof a.note!=='string'||a.previous_rule_id!==(q.current?q.current.rule_id:null))throw Error('Invalid draft answer or changed scope.');pending.set(a.question_id,a);}
 drafts.clear();for(const [k,v]of pending)drafts.set(k,v);$('actor').value=r.actor;dirty=false;updateCount();render();$('message').textContent='Draft restored locally; nothing applied.';
 }catch(error){$('message').textContent='Could not restore draft. Check its session and format.';}event.target.value='';});
const blocked=$('blocked-list');for(const item of data.blocked)blocked.append(node('p',item.id+': '+item.reason));
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
updateCount();render();
"""


def _hash(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


def _head(title, script=False):
    policy = "default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; img-src 'none'; object-src 'none'; "
    policy += "style-src 'sha256-" + _hash(CSS) + "'; "
    policy += "script-src 'sha256-" + _hash(JS) + "';" if script else "script-src 'none';"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer">'
            '<meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">'
            '<title>' + html.escape(title) + '</title><style>' + CSS + '</style></head><body>')


def render(session):
    payload = json.dumps(session, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return _head('Evidence review', script=True) + """
<header><h1>Evidence review</h1><p id="overview"></p><p id="coverage" class="notice"></p></header>
<p>Review here → export answers → inspect a checked preview → apply a new snapshot. Nothing on this page edits the archive.</p>
<div class="toolbar"><label>View <select id="view"><option value="batch">Current batch</option><option value="all">All prepared questions</option><option value="history">Decision history</option></select></label>
<label>Type <select id="kind"><option value="">All types</option><option value="conflict">Potential contradictions</option><option value="relationship">Relationships</option><option value="identity">Optional identity questions</option></select></label>
<label>Status <select id="state"><option value="">All statuses</option><option>pending</option><option>reviewed</option><option>deferred</option><option>waiting</option><option>blocked</option></select></label>
<label>Batch size <select id="size">""" + ''.join('<option>'+str(n)+'</option>' for n in range(1,21)) + """</select></label>
<label>Search <input id="search" type="search" placeholder="Search prepared evidence"></label></div>
<div class="toolbar"><button id="previous">Previous</button><span id="page-status" aria-live="polite"></span><button id="next">Next</button></div>
<section id="cards" aria-label="Review questions"></section>
<details><summary>Blocked proposals</summary><div id="blocked-list"></div></details>
<section class="card"><h2>Save your answers</h2><p id="draft-count" aria-live="polite"></p>
<label>Reviewer label <input id="actor" autocomplete="off" placeholder="For example: Owner"></label>
<div class="toolbar"><button id="save">Save draft</button><label>Restore draft <input type="file" id="restore" accept="application/json,.json"></label><button id="export">Export answers for preview</button></div>
<p id="message" aria-live="polite"></p><p class="small">Drafts stay in memory until explicitly downloaded. No browser localStorage, model calls, uploads, external assets, or automatic archive writes. Keep this HTML and downloaded answers private.</p></section>
<script type="application/json" id="review-data">""" + payload + '</script><script>' + JS + '</script></body></html>'


def render_preview(receipt):
    esc = lambda value: html.escape(str(value))
    text = _head('Checked decision preview') + '<h1>Checked decision preview</h1><p>No changes have been applied.</p>'
    text += '<p>Basis snapshot: ' + esc(receipt['basis_snapshot_id']) + '</p>'
    for item in receipt['impact']:
        text += '<article class="card"><h2>' + esc(item['title']) + '</h2><p>' + esc(item['kind']) + ': <strong>' + esc(item['choice']) + '</strong></p>'
        text += '<p>' + esc(item['note']) + '</p>'
        if item['withdrawn_rules']:
            text += '<p class="notice">Withdraw support from: ' + esc(', '.join(item['withdrawn_rules'])) + '. Dependent assertions listed below are affected too.</p>'
        for old in item.get('withdrawn_decisions', []):
            text += '<p>' + esc(old) + '</p>'
        for witness in item['evidence']:
            text += '<p>' + esc(witness['entry_id']) + '</p><pre>' + esc(witness['quote']) + '</pre>'
        text += '</article>'
    text += '<p>Unanswered questions remain unchanged. A conflict classification is a recorded review judgment, not a diagnosis or a decision about which medical account is true.</p>'
    return text + '</body></html>'
