"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const names = {ofac:"OFAC", "white-house":"White House", ap:"AP"};
const descriptions = {ofac:"Selected general-license titles. Defines scope, not the announced deal.","white-house":"The administration’s announcement. Claims are not independently verified.",ap:"Selected reporting excerpts. Some statements are attributed to the White House."};
const statusNames = {stated:"Stated", attributed:"Attributed", absent:"Not found", not_named:"Not named on this page"};
const actionNames = {hold:"Hold", verify_first:"Verify first", publish_draft:"Eligible for review"};
const kindNames = {ranking_conflict:"Different ranking scopes", scope_gap:"License scope ≠ announcement", attribution_gap:"Attribution needs checking", single_source:"Single-source figure", conflict:"Conflicting quantities", policy_attack:"Untrusted instruction detected"};
const state = {bundle:null, report:null, current:null, live:false, selectedClaim:null, reviewed:new Set(), reviews:new Map(), busy:false, token:0};
const findingKey = finding => JSON.stringify([finding.kind,finding.summary,finding.quotes,finding.urls]);
function safeUrl(value) { try {const url = new URL(value); return ["https:","http:"].includes(url.protocol) ? url.href : "#";} catch {return "#";} }
function link(url, text) {return `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(text)} ↗</a>`;}
async function json(url, options = {}) {
  // GUESS: UI timeout budget, not a measured service latency target; allows the optional model's bounded request.
  const response = await fetch(url, {...options, signal:AbortSignal.timeout(40000)});
  if (!response.ok) {let message = `Request failed (${response.status})`; try {const body=await response.json();if(typeof body.detail === "string") message=body.detail;} catch {} throw new Error(message);}
  return response.json();
}
const post = (url, body) => json(url, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
function selectedIds() {return [...document.querySelectorAll("#source-options input:checked")].map(el=>el.value);}
function setSelection(ids) {document.querySelectorAll("#source-options input").forEach(el=>el.checked=ids.includes(el.value));}
function busy(value) {state.busy=value; $("compare").disabled=value || !selectedIds().length; document.querySelectorAll("#source-options input, [data-scenario], #use-model").forEach(el=>el.disabled=value); $("workspace").setAttribute("aria-busy",String(value));}
function error(message) {$("error").hidden=!message; $("error").textContent=message;}
function scopeClaims() {return (state.current?.claims || []).filter(row=>Object.values(row.cells).some(cell=>cell.status!=="absent"));}
function repeated(row) {const cells=Object.values(row.cells); return cells.filter(c=>["stated","attributed"].includes(c.status)).length>1 && !cells.some(c=>c.status==="not_named");}
function needsReview(row) {return !repeated(row) || Object.values(row.cells).some(c=>c.status==="attributed") || row.id.startsWith("rank_");}
function showTab(tab, focus=false) {
  document.querySelectorAll("[data-tab]").forEach(button=>{const active=button.dataset.tab===tab; button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;$("panel-"+button.dataset.tab).hidden=!active;if(active&&focus)button.focus();});
}
function paintClaims() {
  const search=$("search").value.trim().toLowerCase(), filter=$("filter").value;
  const rows=scopeClaims().filter(row=>row.label.toLowerCase().includes(search)&&(filter!=="review"||needsReview(row))&&(filter!=="shared"||repeated(row)));
  $("visible-count").textContent=`${rows.length} of ${scopeClaims().length} claims`;
  $("empty").hidden=rows.length>0;
  const sources=state.current.sources;
  $("claims").querySelector("thead").innerHTML=`<tr><th scope="col">Claim</th>${sources.map(s=>`<th scope="col">${esc(names[s.id])}</th>`).join("")}</tr>`;
  if(!rows.some(row=>row.id===state.selectedClaim))state.selectedClaim=rows[0]?.id;
  $("claims").querySelector("tbody").innerHTML=rows.map(row=>`<tr data-claim="${esc(row.id)}" class="${row.id===state.selectedClaim?"selected":""}"><th scope="row"><button aria-pressed="${row.id===state.selectedClaim}" data-claim="${esc(row.id)}">${esc(row.label)}</button></th>${sources.map(s=>{const cell=row.cells[s.id]||{status:"absent"};return `<td><span class="cell-status ${esc(cell.status)}">${esc(statusNames[cell.status]||cell.status)}</span></td>`;}).join("")}</tr>`).join("");
  inspect(state.selectedClaim);
}
function inspect(id) {
  const row=scopeClaims().find(row=>row.id===id);
  if(!row){$("inspector").innerHTML="<h3>No claim selected</h3><p class=muted>Change the filters to inspect evidence.</p>";return;}
  $("inspector").innerHTML=`<p class="eyebrow">Selected claim</p><h3>${esc(row.label)}</h3><p class="muted">${repeated(row)?"Repeated in selected excerpts. This does not prove independent corroboration.":"This selection does not provide multiple supporting excerpts."}</p>`+state.current.sources.map(source=>{
    const cell=row.cells[source.id]||{status:"absent",quote:""};
    return `<article class="evidence-card"><header><strong>${esc(names[source.id])}</strong><span class="cell-status ${esc(cell.status)}">${esc(statusNames[cell.status])}</span></header>${cell.quote?`<blockquote>${esc(cell.quote)}</blockquote>`:"<p class=muted>No matching statement in this stored excerpt. This is not a denial by the publisher.</p>"}<small>${esc(source.capture_note)}</small><p>${link(source.url,"Open original source")}</p><small>Recorded ${esc(source.fetched_at)} · ${esc(source.label||"PUBLIC_RECORDING")}</small><details><summary>Analysed text fingerprint</summary><code>${esc(source.sha256)}</code><p>A hash identifies this input; it does not verify the publisher or the claim.</p></details></article>`;
  }).join("");
}
function reviewProgress(){ $("review-progress").textContent=`${state.reviewed.size} / ${state.current.findings.length} read`; }
function paintReview(){
  const data=state.current;
  $("findings").innerHTML=data.findings.length?data.findings.map((finding,index)=>`<article class="finding"><label><input type="checkbox" data-review="${index}"> Mark as read · ${esc(kindNames[finding.kind]||finding.kind)}</label><p>${esc(finding.summary)}</p><details><summary>Inspect supporting excerpts</summary>${(finding.quotes||[]).map((quote,i)=>`<blockquote>${esc(quote)}</blockquote>${finding.urls?.[i]?link(finding.urls[i],"Source"):""}`).join("")}</details></article>`).join(""):"<p>No configured rule raised a finding. That does not establish factual correctness.</p>";
  $("memo-title").textContent=data.headline; $("memo-body").textContent=data.body;
  $("review-notes").value=state.reviews.get(data.id)?.notes||"";
  document.querySelectorAll("[data-review]").forEach(input=>input.checked=state.reviewed.has(findingKey(data.findings[Number(input.dataset.review)])));
  $("decision-feedback").textContent="";
  reviewProgress(); paintApproval(data.db);
}
function paintApproval(db){
  const draft=db?.drafts?.find(d=>d.id===state.current.draft_id);
  const writable=state.live && !state.current.replay_only && !!state.current.run_id;
  $("approve").disabled=!(writable&&draft?.status==="pending"&&state.current.action==="publish_draft");
  $("reject").disabled=!(writable&&draft?.status==="pending");
  $("approval-explanation").textContent=writable?`Local draft: ${draft?.status||"unknown"}. ${state.current.action!=="publish_draft"?"Policy blocks approval; you can reject this draft.":"Approval inserts a local note only; nothing is posted externally."}`:"Recorded replay: no database is connected to these controls. Export is available; real decisions require running the local Python app.";
}
function paintTrace(){
  const data=state.current;
  $("trace-mode").textContent=`${data.run_id?"Measured during this local run":"Recorded during Python execution"}. Durations exclude browser/network delivery. ${data.generated_at||state.report.generated_at||""}`;
  $("trace").innerHTML=(data.trace||[]).map(step=>`<li><strong>${esc(step.step)}</strong>${step.source_id?` · ${esc(names[step.source_id])}`:""}<small>${esc(step.detail)} · ${Number(step.duration_ms).toFixed(2)} ms</small></li>`).join("")+`<li><strong>Review policy</strong><small>${esc(actionNames[data.action])}. No automatic approval.</small></li>`;
  $("engine-note").textContent=`Interpreter: ${data.interpreter}. Model: ${data.model_status||"not_requested"}. The comparison reference shares the same rules; it is not an independent AI judge.`;
  $("db").textContent=JSON.stringify(data.db,null,2);
}
function paint(data){
  if(state.current)state.reviews.set(state.current.id,{notes:$("review-notes").value,read:new Set(state.reviewed)});
  state.current=data;state.reviewed=new Set(state.reviews.get(data.id)?.read||[]);state.selectedClaim=null;
  $("result").hidden=false;$("decision").textContent=actionNames[data.action]||data.action;$("decision").className="badge "+data.action;
  $("headline").textContent=data.headline;
  $("result-context").textContent=`${data.sources.map(s=>names[s.id]).join(" + ")} · ${data.run_id?"Executed locally":"Recorded analysis replay"}${data.fixture_label?.startsWith("SYNTHETIC")?" · SYNTHETIC test modification":""}`;
  $("claim-count").textContent=scopeClaims().length;$("finding-count").textContent=data.findings.length;
  $("search").value="";$("filter").value="all";
  $("license-section").hidden=!data.licenses?.length;
  $("licenses").querySelector("tbody").innerHTML=(data.licenses||[]).map(item=>`<tr><th scope="row">${esc(item.code)}</th><td>${esc(item.title)}</td><td>${esc(item.issued)}</td></tr>`).join("");
  paintClaims();paintReview();paintTrace();
}
async function compare(){
  if(state.busy||!selectedIds().length)return;
  const ids=selectedIds(), token=++state.token;busy(true);error("");$("selection-status").textContent=state.live?"Running extraction and policy checks…":"Opening the recorded comparison…";
  try{
    const data=state.live?await post("/api/analyses",{source_ids:ids,use_model:$("use-model").checked}):structuredClone(state.bundle.selections[ids.join("+")]);
    if(token!==state.token)return;if(!data)throw new Error("No recorded comparison for this selection");
    paint(data);showTab("evidence");$("selection-status").textContent=state.live?"Analysis complete. Review the evidence below.":"Recorded result loaded. No live AI call or database write.";
  }catch(err){error(err.message+". Your previous result, if any, is unchanged.");$("selection-status").textContent="Comparison failed. Retry when ready.";}
  finally{busy(false);}
}
async function scenario(id){
  if(state.busy)return;
  const row=state.report.cases.find(item=>item.id===id);if(!row)return;
  setSelection(row.source_ids);error("");
  busy(false);
  // Safety cases are explicitly replays of harness runs, including simulated human outcomes.
  paint({...structuredClone(row),replay_only:true,generated_at:state.report.generated_at});
  $("selection-status").textContent=`Recorded evaluation: ${row.title}. Compare selected sources to return to the normal analysis.`;
  showTab(id==="jailbreak"||id==="retry-429"?"evaluations":"evidence");
  $("result").scrollIntoView({block:"start"});
}
function paintEvaluations(){
  const cases=state.report.cases;$("eval-score").textContent=`${cases.filter(row=>row.passed).length} / ${cases.length} passed`;
  $("eval-cases").innerHTML=cases.map(row=>`<details class="eval-case"><summary><span>${esc(row.title)}</span><span class="${row.passed?"check-pass":"check-fail"}">${row.passed?"Pass":"Fail"}</span></summary><p>${esc(row.fixture_label)} · ${esc(actionNames[row.action])} · ${row.approved_writes} approved writes</p><div class="checks">${Object.entries(row.checks).map(([key,value])=>`<span class="${value?"check-pass":"check-fail"}">${value?"✓":"✗"} ${esc(key.replaceAll("_"," "))}</span>`).join("")}</div><button data-scenario="${esc(row.id)}">Inspect this recorded case</button></details>`).join("");
}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),0);}
function exportMemo(){
  const data=state.current;
  const lines=["# Info Desk — review memo","",`Status: ${actionNames[data.action]} — NOT PUBLISHED`, `Mode: ${data.run_id?"local execution":"recorded replay"}`,`Analysis: ${data.generated_at||state.report.generated_at}`,"",`## ${data.headline}`,"",data.body,"","## Verification findings"];
  data.findings.forEach(finding=>{lines.push("",`- ${state.reviewed.has(findingKey(finding))?"[read]":"[unread]"} ${finding.summary}`);(finding.urls||[]).forEach(url=>lines.push(`  Source: ${url}`));});
  lines.push("","## Source manifest");data.sources.forEach(s=>lines.push("",`- ${names[s.id]}: ${s.url}`,`  Captured: ${s.fetched_at}`,`  Analysed text SHA-256: ${s.sha256||"not available"}`,`  ${s.capture_note||"Selected recorded excerpts."}`));
  lines.push("","## Reviewer notes (not source evidence)","",$("review-notes").value||"No notes entered.","","Limits: curated excerpts and rules, not live verification, legal advice or independent corroboration. Marking a finding read does not resolve it. Exporting this memo does not approve a note.");
  download("info-desk-review.md",lines.join("\n"),"text/markdown;charset=utf-8");
}
async function decide(decision){
  $("approve").disabled=true;$("reject").disabled=true;
  try{const db=await post(`/api/drafts/${state.current.draft_id}/decide`,{decision});state.current.db=db;paintApproval(db);$("db").textContent=JSON.stringify(db,null,2);$("decision-feedback").textContent=`${decision==="reject"?"Rejected":"Approved"}. Ledger: ${db.notes} notes, ${db.approved_writes} approved writes.`;}
  catch(err){$("decision-feedback").textContent=err.message;paintApproval(state.current.db);}
}
async function boot(){
  try{
    state.bundle=await json("workbench.json");state.report=await json("harness.json");
    if(!state.bundle.selections||!Array.isArray(state.report.cases))throw new Error("Invalid replay bundle");
    if(["127.0.0.1","localhost","[::1]"].includes(location.hostname)){
      try{const health=await json("/api/health");state.live=health.ok&&health.mode==="local_api";$("model-control").hidden=!(state.live&&health.model_available);}catch{/* A plain static server is a supported replay mode. */}
    }
    $("mode").textContent=state.live?"Local Python + SQLite":"Recorded replay";
    $("source-options").innerHTML=state.bundle.sources.map(source=>`<label class="source-option"><input type="checkbox" value="${esc(source.id)}" checked><span><strong>${esc(names[source.id])}</strong><small>${esc(descriptions[source.id])}</small></span></label>`).join("");
    paintEvaluations();paint(structuredClone(state.bundle.selections["ofac+white-house+ap"]));
    $("selection-status").textContent=state.live?"Recorded preview. Compare to execute Python and save a local run.":"Explore recorded Python results. No live AI call or database write.";
    busy(false);
  }catch(err){error(`Unable to load the workbench: ${err.message}. Reload this page to retry. Locally, generate files with python -m infodesk.harness.`);$("mode").textContent="Unavailable";$("selection-status").textContent="Required data did not load.";}
}
$("compare").addEventListener("click",compare);
$("source-options").addEventListener("change",()=>{$("compare").disabled=!selectedIds().length;$("selection-status").textContent=selectedIds().length?"Selection changed. Compare to update the results below.":"Select at least one source.";});
$("claims").addEventListener("click",event=>{const row=event.target.closest("[data-claim]");if(!row)return;state.selectedClaim=row.dataset.claim;paintClaims();if(matchMedia("(max-width: 1000px)").matches){$("inspector").focus({preventScroll:true});$("inspector").scrollIntoView({block:"start"});}});
$("search").addEventListener("input",paintClaims);$("filter").addEventListener("change",paintClaims);
document.addEventListener("click",event=>{const button=event.target.closest("[data-scenario]");if(button)scenario(button.dataset.scenario);const tab=event.target.closest("[data-tab]");if(tab)showTab(tab.dataset.tab);});
document.querySelector(".tabs").addEventListener("keydown",event=>{const tabs=[...document.querySelectorAll("[data-tab]")],index=tabs.indexOf(document.activeElement);if(index<0)return;let target;if(event.key==="ArrowRight")target=(index+1)%tabs.length;if(event.key==="ArrowLeft")target=(index+tabs.length-1)%tabs.length;if(event.key==="Home")target=0;if(event.key==="End")target=tabs.length-1;if(target!==undefined){event.preventDefault();showTab(tabs[target].dataset.tab,true);}});
$("findings").addEventListener("change",event=>{if(!event.target.matches("[data-review]"))return;const key=findingKey(state.current.findings[Number(event.target.dataset.review)]);event.target.checked?state.reviewed.add(key):state.reviewed.delete(key);reviewProgress();});
$("export-md").addEventListener("click",exportMemo);
$("export-json").addEventListener("click",()=>download("info-desk-evidence.json",JSON.stringify({mode:state.current.run_id?"local_execution":"recorded_replay",analysis:state.current,reviewer_notes:$("review-notes").value,findings_read:[...state.reviewed]},null,2),"application/json"));
$("approve").addEventListener("click",()=>decide("approve"));$("reject").addEventListener("click",()=>decide("reject"));
// The live workspace does not download replay bundles until the user opens the lab.
let recordedBoot;
window.loadRecordedDesk = () => recordedBoot ||= boot();
if(new URLSearchParams(location.search).get("mode")==="recorded")window.loadRecordedDesk();
