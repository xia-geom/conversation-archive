"""Offline review dashboard. Declarative data selects trusted, reusable controls."""
from __future__ import annotations

import base64
import hashlib
import html
import json

CSS = """
:root{font:16px/1.5 system-ui,sans-serif;color:#17212b;background:#f6f7f8}
*{box-sizing:border-box}h2,h3,p{overflow-wrap:anywhere}select,input{max-width:100%}
body{max-width:1160px;margin:auto;padding:24px}h1{margin:0}header,p{margin-bottom:14px}
button,select,input,textarea{font:inherit;padding:8px;border:1px solid #aeb9c2;border-radius:5px;background:white}
button{cursor:pointer}button:disabled{cursor:default;opacity:.5}input[type=search]{min-width:210px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0;align-items:center}
.card{background:white;border:1px solid #d8dfe4;border-radius:8px;padding:20px;margin:18px 0}
.evidence{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.witness{border-left:3px solid #98aabc;padding:0 14px;min-width:0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}
textarea{width:100%;min-height:65px}.small{font-size:13px;color:#536271;overflow-wrap:anywhere}
.notice{background:#fff8dd;padding:12px;border-radius:5px}.status{font-weight:600}summary{cursor:pointer}
[hidden]{display:none!important}:focus-visible{outline:3px solid #216baa;outline-offset:2px}
label{display:block;margin:10px 0}fieldset{border:1px solid #d8dfe4;border-radius:5px;margin:16px 0;padding:14px}
.group{display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #d8dfe4;padding:8px 0}
.member{display:grid;grid-template-columns:minmax(0,1fr) minmax(170px,250px);gap:14px;align-items:center}
.error{color:#942d22;white-space:pre-wrap}.field{margin:16px 0}.field legend{font-weight:600}
@media(max-width:600px){body{padding:14px}.card{padding:14px}.evidence,.member{grid-template-columns:1fr}
.toolbar label{width:100%;min-width:0}.toolbar select,.toolbar input,.card select{width:100%}}
"""
JS = r"""
'use strict';
const data=JSON.parse(document.getElementById('review-data').textContent);
const entries=Object.fromEntries(data.entries.map(e=>[e.entry_id,e]));
const work=new Map(); let dirty=false,page=0;
const $=id=>document.getElementById(id);
const clone=x=>JSON.parse(JSON.stringify(x));
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
const labels={confirm:'Confirm this relationship',reject:'Reject this relationship',insufficient:'Insufficient evidence',defer:'Defer until explicitly reopened',reopen:'Withdraw this decision and reopen',disagree:'The sources genuinely disagree (truth not decided)',different_events:'Different events or subjects',different_date_roles:'Different meanings of the dates',transcription_discrepancy:'A transcription discrepancy',corrected_report:'A corrected or superseding report',group:'Record these explicit identity groups',record:'Record this answer (no factual field is overwritten)'};
function status(q){if(q.blocked)return 'blocked';if(!q.current)return 'pending';if(q.current.choice==='defer')return 'deferred';if(q.current.choice==='insufficient')return 'waiting';if(q.current.choice==='group'&&q.current.values.identity.unknown.length)return 'partial';return 'reviewed';}
function allowed(q){return [...new Set([...q.choices,...(q.controls?[q.controls.action]:[])])];}
function draft(q){return work.get(q.question_id)||{choice:'',note:'',values:{}};}
function visible(field,values){return !field.visible_when||values[field.visible_when.field]===field.visible_when.equals;}
function submittedValues(q,d){const result={};for(const f of q.controls.form.fields){if(visible(f,result)&&Object.hasOwn(d.values,f.id))result[f.id]=d.values[f.id];}return result;}
function answer(q){const d=draft(q);const a={question_id:q.question_id,choice:d.choice,note:d.note,previous_rule_id:q.current?q.current.rule_id:null};if(q.controls&&d.choice===q.controls.action)a.values=submittedValues(q,d);return a;}
function reply(){return {protocol:data.protocol,session_id:data.session_id,basis_snapshot_id:data.basis_snapshot_id,actor:$('actor').value,answers:data.questions.filter(q=>draft(q).choice).map(answer)};}
function updateCount(){$('draft-count').textContent=data.questions.filter(q=>draft(q).choice).length+' explicit draft answers; nothing applied';}
function changed(q,d){work.set(q.question_id,d);dirty=true;updateCount();}
function download(value,name){const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function formErrors(q,values){const errors=[];for(const f of q.controls.form.fields){if(!visible(f,values))continue;const v=values[f.id];if(v===undefined){if(f.required)errors.push(f.label+': answer required');continue;}
 if(f.type==='text'&&(typeof v!=='string'||v.length>f.max_length||(f.required&&!v.trim())))errors.push(f.label+': invalid text');
 if(f.type==='choice'&&!f.options.some(o=>o.value===v))errors.push(f.label+': select one option');
 if(f.type==='multi_choice'&&(!Array.isArray(v)||(f.required&&!v.length)||v.some(x=>!f.options.some(o=>o.value===x))))errors.push(f.label+': select valid options');
 if(f.type==='groups'){if(!v||!Array.isArray(v.groups)||!Array.isArray(v.unknown)){errors.push(f.label+': assign references');continue;}
 const ids=[...v.unknown,...v.groups.flatMap(g=>g.items)];const targets=v.groups.map(g=>g.target).filter(Boolean);
 if(ids.length!==new Set(ids).size||ids.length!==f.items.length||ids.some(id=>!f.items.some(i=>i.id===id)))errors.push(f.label+': assign each reference once or mark it unknown');
 if(v.groups.some(g=>!g.items.length||!g.label.trim()||g.label.length>200))errors.push(f.label+': groups need a label and at least one reference');
 if(targets.length!==new Set(targets).size)errors.push(f.label+': two groups cannot use the same identity');
 if(q.controls.effect==='bind_mentions'&&!v.groups.length)errors.push(f.label+': choose a group or use insufficient evidence');
 }}return errors;}
const controlRenderers={
 choice(f,value,emit){const el=node('select');el.append(new Option('No answer selected',''));for(const o of f.options)el.append(new Option(o.label,o.value));el.value=value||'';el.addEventListener('change',()=>emit(el.value||undefined));return el;},
 multi_choice(f,value,emit){const el=node('div');const selected=new Set(value||[]);for(const o of f.options){const label=node('label');const input=node('input');input.type='checkbox';input.checked=selected.has(o.value);input.addEventListener('change',()=>{if(input.checked)selected.add(o.value);else selected.delete(o.value);emit(f.options.filter(x=>selected.has(x.value)).map(x=>x.value));});label.append(input,document.createTextNode(' '+o.label));el.append(label);}return el;},
 text(f,value,emit){const el=node('textarea');el.maxLength=f.max_length;el.value=value||'';el.addEventListener('input',()=>emit(el.value));return el;},
 groups(f,value,emit){const el=node('div');const model=clone(value||{groups:[],unknown:[]});
 function paint(){el.replaceChildren();const groups=node('div');model.groups.forEach((g,index)=>{const row=node('div',undefined,'group');
 const title=node('input');title.value=g.label;title.maxLength=200;title.setAttribute('aria-label','Label for group '+(index+1));title.addEventListener('input',()=>{g.label=title.value;emit(clone(model));});
 const target=node('select');target.setAttribute('aria-label','Identity for group '+(index+1));target.append(new Option('Create a new identity',''));for(const t of f.targets)target.append(new Option(t.label,t.id));target.value=g.target||'';target.addEventListener('change',()=>{g.target=target.value||null;emit(clone(model));});
 const remove=node('button','Remove group '+(index+1));remove.type='button';remove.addEventListener('click',()=>{model.groups.splice(index,1);emit(clone(model));paint();});row.append(node('span','Group '+(index+1)),title,target,remove);groups.append(row);});el.append(groups);
 const add=node('button','Add group');add.type='button';add.addEventListener('click',()=>{if(model.groups.length>=f.items.length)return;model.groups.push({label:'Group '+(model.groups.length+1),target:null,items:[]});emit(clone(model));paint();});el.append(add);
 for(const item of f.items){const row=node('label',undefined,'member');row.append(node('span',item.label));const sel=node('select');sel.setAttribute('aria-label','Group for '+item.id);sel.append(new Option('Not answered',''),new Option('Unknown / no decision','unknown'));model.groups.forEach((g,i)=>sel.append(new Option('Group '+(i+1),'g'+i)));
 const gi=model.groups.findIndex(g=>g.items.includes(item.id));sel.value=gi>=0?'g'+gi:model.unknown.includes(item.id)?'unknown':'';
 sel.addEventListener('change',()=>{for(const g of model.groups)g.items=g.items.filter(x=>x!==item.id);model.unknown=model.unknown.filter(x=>x!==item.id);if(sel.value==='unknown')model.unknown.push(item.id);else if(sel.value)model.groups[Number(sel.value.slice(1))].items.push(item.id);emit(clone(model));});row.append(sel);el.append(row);}
 const unknown=node('button','Mark remaining references unknown');unknown.type='button';unknown.addEventListener('click',()=>{const assigned=new Set(model.groups.flatMap(g=>g.items));model.unknown=f.items.filter(i=>!assigned.has(i.id)).map(i=>i.id);emit(clone(model));paint();});el.append(unknown);
 }paint();return el;}
};
function fields(q,d){const panel=node('div');const holders=[];for(const f of q.controls.form.fields){const box=node('fieldset',undefined,'field');box.dataset.fieldId=f.id;box.append(node('legend',f.label+(f.required?' *':'')));if(f.help)box.append(node('p',f.help,'small'));
 const renderer=controlRenderers[f.type];if(!renderer)throw Error('Unsupported renderer');const input=renderer(f,d.values[f.id],value=>{if(value===undefined)delete d.values[f.id];else d.values[f.id]=value;changed(q,d);for(const h of holders)h.box.hidden=!visible(h.field,submittedValues(q,d));});input.setAttribute('aria-label',f.label);box.append(input);holders.push({box,field:f});box.hidden=!visible(f,submittedValues(q,d));panel.append(box);}return panel;}
function card(q){const c=q.case,box=node('article',undefined,'card');box.id=q.question_id;const d=draft(q);
 box.append(node('h2',c.title),node('p',c.prompt),node('p','Why this case: '+c.reason),node('p',c.kind+' · '+status(q),'status'),node('p',q.question_id,'small'));
 if(c.kind==='identity')box.append(node('p',q.controls?'Grouping changes only the displayed references. Unknown does not mean different. Existing assignments are shown below and are not silently overwritten.':'Legacy session: prepare a new session to enable grouping.','notice'));
 if(q.controls&&q.controls.effect==='record_only')box.append(node('p','This form records your answer and explanation. It does not edit source facts, assign identities, or confirm graph links.','notice'));
 if(q.current){const previous=node('details');previous.append(node('summary','Recorded answer: '+(labels[q.current.choice]||q.current.choice)),node('p',q.current.note));if(q.current.values)previous.append(node('pre',JSON.stringify(q.current.values,null,2)));box.append(previous);}
 if(q.blocked)box.append(node('p',q.blocked,'notice'));if(c.relation)box.append(node('p','Direction: '+c.source_entry_id+' → '+c.target_entry_id+' ('+c.relation+')'));
 const ev=node('div',undefined,'evidence');for(const w of c.evidence){const e=entries[w.entry_id],panel=node('section',undefined,'witness');panel.append(node('h3',e.title||e.entry_id),node('pre',w.quote),node('p','Entry '+w.entry_id+' · Unicode character range ['+w.start+', '+w.end+')','small'));
 const metadata=data.metadata.filter(m=>m.entry_id===w.entry_id);if(metadata.length)panel.append(node('p',metadata.map(m=>m.field+': '+m.value).join('\n'),'small'));
 const refs=data.source_references.filter(r=>r.entry_id===w.entry_id);if(refs.length)panel.append(node('p','Stored source references: '+refs.map(r=>r.source_ref).join(', '),'small'));
 if(q.controls&&q.controls.scope){for(const m of q.controls.scope.mentions.filter(m=>m.entry_id===w.entry_id&&m.start===w.start&&m.end===w.end))panel.append(node('p','Reference '+m.mention_id+' · Current identity: '+(m.entity_id||'unassigned'),'small'));}
 const full=node('details');full.append(node('summary','Open complete preserved entry'),node('pre',e.raw_markdown));panel.append(full);ev.append(panel);}box.append(ev);
 if(q.controls){box.append(fields(q,d));if(q.current&&q.current.values){const load=node('button','Copy previous values into draft');load.type='button';load.addEventListener('click',()=>{d.values=clone(q.current.values);changed(q,d);render();});box.append(load);}}
 const choice=node('select');choice.setAttribute('aria-label','Decision for '+q.question_id);choice.append(new Option('No answer selected',''));for(const value of allowed(q)){if(value==='reopen'&&!q.current)continue;const opt=new Option(labels[value]||value,value);if(q.blocked&&!['defer','reopen'].includes(value))opt.disabled=true;choice.append(opt);}choice.value=d.choice;
 const note=node('textarea');note.setAttribute('aria-label','Explanation for '+q.question_id);note.placeholder='Optional explanation, preserved as your answer—not interpreted as a command.';note.value=d.note;
 choice.addEventListener('change',()=>{d.choice=choice.value;changed(q,d);});note.addEventListener('input',()=>{d.note=note.value;changed(q,d);});const lab=node('label','Your decision ');lab.append(choice);box.append(lab,note);return box;}
function render(){const area=$('cards');area.replaceChildren();if($('view').value==='history'){for(const h of data.history){const b=node('article',undefined,'card');b.append(node('p',h.question_id,'small'),node('p',(labels[h.choice]||h.choice)+' · '+(h.active?'active':'withdrawn')),node('p',h.note));if(h.values)b.append(node('pre',JSON.stringify(h.values,null,2)));b.append(node('p','Rule '+h.rule_id+' · Event '+h.event_id,'small'));area.append(b);}$('page-status').textContent=data.history.length+' historical answers';$('previous').disabled=true;$('next').disabled=true;return;}
 const query=$('search').value.toLocaleLowerCase();const rows=data.questions.filter(q=>{if($('view').value==='batch'&&((q.case.kind==='identity'&&$('kind').value!=='identity')||!['pending','partial'].includes(status(q))))return false;if($('kind').value&&q.case.kind!==$('kind').value)return false;if($('state').value&&status(q)!==$('state').value)return false;return (JSON.stringify(q.case)+' '+q.case.evidence.map(w=>entries[w.entry_id].title).join(' ')).toLocaleLowerCase().includes(query);});
 const size=Number($('size').value);page=Math.min(page,Math.max(0,Math.ceil(rows.length/size)-1));for(const q of rows.slice(page*size,(page+1)*size))area.append(card(q));if(!rows.length)area.append(node('p','No prepared questions match this view. This does not establish that your sources have no contradictions.','notice'));
 $('page-status').textContent=rows.length?('Questions '+(page*size+1)+'–'+Math.min(rows.length,(page+1)*size)+' of '+rows.length):'0 prepared questions';$('previous').disabled=page===0;$('next').disabled=(page+1)*size>=rows.length;}
$('overview').textContent=data.coverage.snapshot_entries+' snapshot entries · '+data.questions.length+' prepared questions · '+data.coverage.conflict_cases+' supplied conflict cases · '+data.blocked.length+' blocked proposals';
$('coverage').textContent='Prepared questions only. No automatic contradiction discovery, live-source completeness claim, model calls, or implicit corrections.';
$('size').value=String(data.batch_size);for(const id of ['view','kind','state','size'])$(id).addEventListener('change',()=>{page=0;render();});$('search').addEventListener('input',()=>{page=0;render();});$('previous').addEventListener('click',()=>{page--;render();});$('next').addEventListener('click',()=>{page++;render();});$('actor').addEventListener('input',()=>{dirty=true;});
$('save').addEventListener('click',()=>{download({kind:'review-draft',reply:reply(),work:Object.fromEntries(work)},'review-draft.json');dirty=false;$('message').textContent='Draft saved, including unfinished fields. Nothing applied.';});
$('export').addEventListener('click',()=>{const r=reply();if(!r.actor.trim()||!r.answers.length){$('message').textContent='Enter a reviewer label and choose at least one answer.';return;}const errors=[];for(const q of data.questions){const d=draft(q);if(q.controls&&d.choice===q.controls.action)errors.push(...formErrors(q,submittedValues(q,d)).map(e=>q.case.title+': '+e));}if(errors.length){$('message').textContent=errors.join('\n');return;}download(r,'review-answers.json');$('message').textContent='Answers exported. Inspect the checked preview before applying. Save a draft to retain unfinished edits.';});
$('restore').addEventListener('change',async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('Oversized draft');const loaded=JSON.parse(await file.text()),r=loaded.kind==='review-draft'?loaded.reply:loaded;
 if(r.protocol!==data.protocol||r.session_id!==data.session_id||r.basis_snapshot_id!==data.basis_snapshot_id||!Array.isArray(r.answers)||typeof r.actor!=='string')throw Error('Different session');const pending=new Map();
 for(const a of r.answers){const q=data.questions.find(x=>x.question_id===a.question_id);if(!q||pending.has(a.question_id)||!allowed(q).includes(a.choice)||typeof a.note!=='string'||a.previous_rule_id!==(q.current?q.current.rule_id:null))throw Error('Invalid answer');pending.set(a.question_id,{choice:a.choice,note:a.note,values:a.values||{}});}
 if(loaded.work){if(typeof loaded.work!=='object'||Array.isArray(loaded.work))throw Error('Invalid working draft');for(const [id,d]of Object.entries(loaded.work)){const q=data.questions.find(x=>x.question_id===id);if(!q||!d||typeof d.choice!=='string'||(d.choice&&!allowed(q).includes(d.choice))||typeof d.note!=='string'||!d.values||typeof d.values!=='object'||Array.isArray(d.values))throw Error('Invalid working item');pending.set(id,d);}}
 // Render into a temporary area first: malformed drafts cannot replace saved work.
 const old=new Map(work);work.clear();for(const [k,v]of pending)work.set(k,v);try{render();}catch(e){work.clear();for(const [k,v]of old)work.set(k,v);render();throw e;}
 $('actor').value=r.actor;dirty=false;updateCount();$('message').textContent='Draft restored locally; nothing applied.';
 }catch(error){$('message').textContent='Could not restore draft. Check its session and format.';}event.target.value='';});
for(const item of data.blocked)$('blocked-list').append(node('p',item.id+': '+item.reason));window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});updateCount();render();
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
<p>Review → save/export answers → checked preview → new snapshot. Saving never applies decisions.</p>
<div class="toolbar"><label>View <select id="view"><option value="batch">Current batch</option><option value="all">All prepared questions</option><option value="history">Decision history</option></select></label>
<label>Type <select id="kind"><option value="">All types</option><option value="conflict">Potential contradictions</option><option value="relationship">Relationships</option><option value="form">Custom questions</option><option value="identity">Identity grouping (optional)</option></select></label>
<label>Status <select id="state"><option value="">All statuses</option><option>pending</option><option>partial</option><option>reviewed</option><option>deferred</option><option>waiting</option><option>blocked</option></select></label>
<label>Batch size <select id="size">""" + ''.join('<option>'+str(n)+'</option>' for n in range(1,21)) + """</select></label>
<label>Search <input id="search" type="search" placeholder="Search prepared evidence"></label></div>
<div class="toolbar"><button id="previous">Previous</button><span id="page-status" aria-live="polite"></span><button id="next">Next</button></div>
<section id="cards" aria-label="Review questions"></section>
<details><summary>Blocked proposals</summary><div id="blocked-list"></div></details>
<section class="card"><h2>Save your answers</h2><p id="draft-count" aria-live="polite"></p>
<label>Reviewer label <input id="actor" autocomplete="off" placeholder="For example: Owner"></label>
<div class="toolbar"><button id="save">Save draft</button><label>Restore draft <input type="file" id="restore" accept="application/json,.json"></label><button id="export">Export answers for preview</button></div>
<p id="message" class="error" aria-live="polite"></p><p class="small">Local memory until saved. No browser localStorage, model calls, uploads, external assets, or automatic archive writes. Keep HTML and downloaded drafts private.</p></section>
<script type="application/json" id="review-data">""" + payload + '</script><script>' + JS + '</script></body></html>'


def render_preview(receipt):
    esc = lambda value: html.escape(str(value))
    text = _head('Checked decision preview') + '<h1>Checked decision preview</h1><p>No changes have been applied.</p>'
    text += '<p>Basis snapshot: ' + esc(receipt['basis_snapshot_id']) + '</p>'
    text += '<p>Retain ' + esc(receipt.get('retained_proposals', 0)) + ' prepared cases as proposals.</p>'
    for item in receipt['impact']:
        text += '<article class="card"><h2>' + esc(item['title']) + '</h2><p>' + esc(item['kind']) + ': <strong>' + esc(item['choice']) + '</strong></p>'
        text += '<p>' + esc(item['note']) + '</p>'
        if 'values' in item:
            text += '<p>Effect: <strong>' + esc(item['effect']) + '</strong></p><pre>' + esc(json.dumps(item['values'], ensure_ascii=False, indent=2)) + '</pre>'
            if item.get('identity_changes'):
                text += '<h3>Exact identity changes</h3><pre>' + esc(json.dumps(item['identity_changes'], ensure_ascii=False, indent=2)) + '</pre>'
        if item['withdrawn_rules']:
            text += '<p class="notice">Withdraw support from: ' + esc(', '.join(item['withdrawn_rules'])) + '</p>'
        for old in item.get('withdrawn_decisions', []):
            text += '<p>' + esc(old) + '</p>'
        for witness in item['evidence']:
            text += '<p>' + esc(witness['entry_id']) + '</p><pre>' + esc(witness['quote']) + '</pre>'
        text += '</article>'
    return text + '<p>Unanswered cases remain proposals. Free text is not executed or promoted to source evidence.</p></body></html>'
