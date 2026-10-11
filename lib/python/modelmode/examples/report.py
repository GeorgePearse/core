"""Produce a standalone, sortable benchmark report with embedded raw evidence."""

import argparse
import json
from pathlib import Path

TEMPLATE = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ModelMode · small models, measured</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101720;color:#e7edf4;font:16px system-ui,sans-serif;line-height:1.55}main{max-width:1180px;margin:auto;padding:52px 28px}h1{font-size:clamp(32px,5vw,60px);line-height:1.1;margin:12px 0 22px}h2{margin-top:40px}.eyebrow{color:#73dbbb;letter-spacing:.15em;font-size:13px;text-transform:uppercase}.intro{max-width:820px;color:#b9c7d4;font-size:19px}.cards{display:flex;gap:16px;flex-wrap:wrap;margin:28px 0}.card{flex:1;min-width:170px;padding:22px;background:#1b2734;border:1px solid #314254;border-radius:14px}.value{font-size:28px;color:#87e3c6}small,.muted{color:#a5b7c7}button,select{border:1px solid #486078;background:#223548;color:#fff;padding:10px 14px;border-radius:8px;font:inherit;cursor:pointer}a{color:#86cfef}table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}th,td{text-align:left;padding:13px;border-bottom:1px solid #314254}th{color:#a5b7c7;white-space:nowrap}tr.selected{background:#163b35}.scroll{overflow:auto}.bar{height:12px;border-radius:5px;background:#6ad4b0;margin-top:6px;min-width:1px}.note{border-left:3px solid #6ad4b0;padding-left:20px;color:#b9c7d4}pre{white-space:pre-wrap;word-break:break-word;background:#192532;padding:20px;border-radius:12px;font-size:12px}.matrix td{font-variant-numeric:tabular-nums;text-align:center;padding:7px}.matrix th{font-size:11px;max-width:170px;white-space:normal}.badge{color:#81dfc0}footer{color:#94a8ba;margin-top:48px;border-top:1px solid #314254;padding-top:24px}
</style><main><div class="eyebrow">ModelMode / executable experiment</div>
<h1>Small models.<br>Actual training.</h1>
<p class="intro">A supervising agent turns labelled examples into a reusable classifier. This pilot compares fine-tuning on Modal with a random-weight control and local-style linear baselines, all on the same fixed intent dataset.</p>
<div class="cards" id="cards"></div>
<p class="note" id="context"></p>
<h2>Validation comparison</h2>
<label>Sort by <select id="sort"><option value="quality">Macro F1</option><option value="train">Training time</option><option value="latency">Warm CPU inference</option></select></label>
<div class="scroll"><table><thead><tr><th>Candidate</th><th>Validation macro F1</th><th>Train loop</th><th>Fit incl. load</th><th>Warm CPU / item</th><th>Parameters</th><th>Artifact</th></tr></thead><tbody id="candidates"></tbody></table></div>
<p class="muted">Training-loop time excludes download and tokenization. Fit time includes them. Inference includes tokenization and uses two CPU threads; values are median amortized batch costs, not single-request latency. Neural models train on one T4, then move to CPU for evaluation. Candidate order and caching affect loading time.</p>
<h2>Final test</h2><p id="test"></p><div class="scroll"><table class="matrix" id="matrix"></table></div>
<h2>Training curves</h2><p class="muted">Mean training loss by epoch, not validation or test loss.</p><div id="curves"></div>
<h2>Evidence and reproducibility</h2><p><button id="download">Download raw JSON</button></p>
<details><summary>Dataset provenance and deduplication</summary><pre id="provenance"></pre></details>
<details><summary>Run configuration and environment</summary><pre id="config"></pre></details>
<details><summary>All raw evidence</summary><pre id="raw"></pre></details>
<footer>Public data: <a href="https://github.com/PolyAI-LDN/task-specific-datasets">PolyAI BANKING77</a>, CC BY 4.0. Subset selection, deduplication and validation split are described above. This is one seeded pilot on a subset, not a general model ranking. Teacher labels were not used. Model probabilities are not calibrated correctness.</footer>
</main><script>
const data=__DATA__;
const el=id=>document.getElementById(id), n=(x,d=2)=>Number(x).toFixed(d), esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const run=data.run, successful=run.candidates.filter(c=>c.status==='succeeded'), parts=data.dataset.counts;
el('cards').innerHTML=[['Selected',run.selected],['Training examples',Object.values(parts.train).reduce((a,b)=>a+b,0)],['Classes',data.dataset.classes.length],['Total wall time',n(run.total_seconds)+' s']].map(([label,value])=>`<div class="card"><small>${esc(label)}</small><div class="value">${esc(value)}</div></div>`).join('');
el('context').textContent=`${data.provenance.selection}. ${Object.values(parts.validation).reduce((a,b)=>a+b,0)} validation examples; ${Object.values(parts.test).reduce((a,b)=>a+b,0)} test examples. Selection uses validation macro F1. Only the selected candidate and dummy baseline see final test data. Run ${run.run_id}.`;
function draw(){const sort=el('sort').value;const candidates=[...successful].sort((a,b)=>sort==='quality'?b.validation.macro_f1-a.validation.macro_f1:sort==='latency'?a.warm_ms_per_item-b.warm_ms_per_item:(a.training?.train_seconds??a.fit_seconds)-(b.training?.train_seconds??b.fit_seconds));el('candidates').innerHTML=candidates.map(c=>`<tr class="${c.name===run.selected?'selected':''}"><td>${esc(c.name)}${c.name===run.selected?' <span class="badge">✓</span>':''}</td><td>${n(c.validation.macro_f1*100)}%<div class="bar" style="width:${c.validation.macro_f1*100}%"></div></td><td>${c.training?n(c.training.train_seconds)+' s':'—'}</td><td>${n(c.fit_seconds)} s</td><td>${n(c.warm_ms_per_item,3)} ms</td><td>${c.training?n(c.training.parameters/1e6)+'M':'—'}</td><td>${n(c.artifact_bytes/1e6)} MB</td></tr>`).join('');for(const c of run.candidates.filter(c=>c.status!=='succeeded'))el('candidates').insertAdjacentHTML('beforeend',`<tr><td>${esc(c.name)}</td><td colspan="6">Failed: ${esc(c.error)}</td></tr>`)}
el('sort').addEventListener('change',draw);draw();
if(data.test){const t=data.test.models[run.selected];el('test').textContent=`${run.selected}: ${n(t.macro_f1*100)}% macro F1, ${n(t.accuracy*100)}% accuracy on ${t.examples} examples. Dummy macro F1: ${n(data.test.models.dummy.macro_f1*100)}%. Dataset sealed; rows are actual classes, columns are predictions.`;el('matrix').innerHTML='<tr><th>Actual → predicted</th>'+t.classes.map((_,i)=>`<th>${i+1}</th>`).join('')+'</tr>'+t.confusion_matrix.map((row,i)=>`<tr><th>${i+1}. ${esc(t.classes[i])}</th>`+row.map(v=>`<td style="background:rgba(105,220,181,${v/Math.max(...row)*.4})">${v}</td>`).join('')+'</tr>').join('');}else{el('test').textContent='Final test remains unopened.'}
for(const c of successful.filter(c=>c.training)){const epochs=c.training.epochs,max=Math.max(...epochs.map(e=>e.train_loss));const points=epochs.map((e,i)=>`${35+i*420/Math.max(1,epochs.length-1)},${130-e.train_loss/max*100}`).join(' ');el('curves').insertAdjacentHTML('beforeend',`<p>${esc(c.name)} · ${n(c.training.train_seconds)} s training · ${esc(c.training.gpu??'CPU')}</p><svg role="img" aria-label="${esc(c.name)} training loss" viewBox="0 0 500 155" width="500" style="max-width:100%;background:#192532;border-radius:12px"><polyline points="${points}" fill="none" stroke="#7bddbc" stroke-width="3"/><text x="35" y="150" fill="#a5b7c7" font-size="12">Epoch 1 → ${epochs.length} · loss ${n(epochs[0].train_loss,3)} → ${n(epochs.at(-1).train_loss,3)}</text></svg>`)}
el('provenance').textContent=JSON.stringify(data.provenance,null,2);el('config').textContent=JSON.stringify({config:run.config,environment:run.environment,modal:run.modal},null,2);el('raw').textContent=JSON.stringify(data,null,2);el('download').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='modelmode-benchmark.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
</script></html>"""


def render(data: dict, output: Path) -> None:
    """Embed escaped JSON, so the report needs neither a server nor external assets."""
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c")
    output.write_text(TEMPLATE.replace("__DATA__", payload))


def main() -> None:
    """Read the saved benchmark and write a standalone report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(json.loads(args.input.read_text()), args.output)


if __name__ == "__main__":
    main()
