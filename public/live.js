"use strict";
const live = {snapshot:null,ready:false,enabled:false,busy:false,jobId:null,answerJob:null,selected:new Set(),sources:new Set(["eia","federal-register","ofac-live"]),timer:null,poll:null};
const liveNames={eia:"EIA", "federal-register":"Federal Register", "ofac-live":"OFAC"};
const localTime=value=>value?new Date(value).toLocaleString():"Not checked";
function liveError(message){$("live-error").hidden=!message;$("live-error").textContent=message;}
function liveBusy(value){live.busy=value;$("live-refresh").disabled=value||!live.ready||!live.sources.size;$("live-ask").disabled=value||!live.ready||!live.sources.size;document.querySelectorAll("#live-sources input").forEach(input=>input.disabled=value);$("live-cancel").disabled=!value;}
function setDeskMode(mode){
  const isLive=mode==="live";live.enabled=isLive;$("live-workspace").hidden=!isLive;$("workspace").hidden=isLive;
  $("open-live").setAttribute("aria-pressed",String(isLive));$("open-recorded").setAttribute("aria-pressed",String(!isLive));
  $("mode").textContent=isLive?"Live research":"Recorded case";
  $("recorded-instructions").hidden=isLive;$("live-instructions").hidden=!isLive;
  $("intro-purpose").textContent=isLive
    ?"Collect official energy and sanctions updates, ask a focused question and inspect the evidence behind the draft answer."
    :"Compare the claims in dated OFAC, White House and AP excerpts. Open the source quotations and export your review.";
  if(!isLive)window.loadRecordedDesk();
  if(isLive&&!live.ready)bootLive();
  if(!isLive){clearTimeout(live.timer);live.timer=null;}else if(live.ready)scheduleSync();
}
function paintSources(){
  const snapshot=live.snapshot;
  $("live-sources").innerHTML=snapshot.sources.map(source=>{const check=snapshot.checks[source.id];return `<article class="live-source"><label><input type="checkbox" value="${esc(source.id)}" ${live.sources.has(source.id)?"checked":""}><span>${esc(source.name)}</span></label><div class="source-state ${esc(check?.status||"pending")}"><span class="source-dot" aria-hidden="true"></span>${esc(check?check.status==="error"?"Source error — stored data may be stale":check.status==="unchanged"?"Unchanged at last check":"Connected · last check succeeded":"Not checked yet")}</div><small>${esc(check?.detail||source.coverage)}</small><small>Checked: ${esc(localTime(check?.checked_at))}</small>${check?`<small>Next request no earlier than ${esc(localTime(check.next_check_at))}</small>`:""}</article>`;}).join("");
  $("live-cadence").textContent=`Checks every ${snapshot.poll_seconds}s or later when the provider requires it. No background AI calls.`;
  $("live-model-note").textContent=snapshot.model_available?`Model: ${snapshot.model}. Used only when you request an AI brief. Citation checks do not replace editorial review.`:"AI is not configured. Evidence retrieval still works; set OLLAMA_URL and OLLAMA_MODEL to enable generation.";
  $("live-engine").querySelector('[value="model"]').disabled=!snapshot.model_available;
  if(!snapshot.model_available)$("live-engine").value="evidence";
  liveBusy(live.busy);
}
function paintDocuments(){
  const docs=live.snapshot?.documents||[], search=$("live-search").value.trim().toLowerCase();
  const shown=docs.filter(doc=>live.sources.has(doc.source_id)&&doc.title.toLowerCase().includes(search));
  $("live-count").textContent=`${docs.length} documents`;
  $("live-documents").innerHTML=shown.length?shown.map(doc=>`<article class="live-document"><input type="checkbox" value="${esc(doc.id)}" aria-label="Select ${esc(doc.title)}" ${live.selected.has(doc.id)?"checked":""}><div><button data-live-document="${esc(doc.id)}">${esc(doc.title)}</button><p>${esc(liveNames[doc.source_id])} · Published ${esc(doc.published_at?.slice(0,10)||"date not supplied")}</p><p class="${doc.version_count>1?"revised":""}">${doc.version_count>1?`${doc.version_count} captured versions · inspect changes`:`First seen ${esc(localTime(doc.first_seen))}`}</p><p>${esc(doc.coverage)}</p></div></article>`).join(""):"<p class=muted>No matching documents. Check the sources or clear this filter.</p>";
  $("live-selection").textContent=live.selected.size?`${live.selected.size} document(s) selected. Uncheck them to search the whole source collection.`:"No documents selected: search across selected sources.";
}
function paintHistory(){
  $("live-history").innerHTML=(live.snapshot.jobs||[]).map(job=>`<button data-live-job="${esc(job.id)}">${esc(job.kind==="ask"?"Research":"Source check")} · ${esc(job.state)} · ${esc(localTime(job.created_at))}</button>`).join("")||"<p class=muted>No jobs yet.</p>";
}
async function refreshSnapshot(){live.snapshot=await json("/api/live/status");paintSources();paintDocuments();paintHistory();if(live.answerJob)paintAnswer(live.answerJob);}
function paintJob(job){
  const running=["queued","running"].includes(job.state);
  const elapsed=Math.max(0,Math.floor(((running?Date.now():Date.parse(job.updated_at))-Date.parse(job.created_at))/1000));
  $("live-job").hidden=false;$("live-job-state").textContent=`${job.kind==="ask"?"Research":"Source check"} · ${job.state} · ${elapsed}s elapsed`;
  $("live-job-trace").innerHTML=job.trace.map(step=>`<li>${esc(step.step)}${step.duration_ms==null?"":` · ${Number(step.duration_ms).toFixed(1)} ms`}</li>`).join("");
  $("live-cancel").hidden=!["queued","running"].includes(job.state);
}
function paintAnswer(job){
  live.answerJob=job;const result=job.result||{}, answer=result.answer;
  $("live-answer").hidden=false;
  const revised=(result.passages||[]).some(p=>live.snapshot.documents.some(d=>d.id===p.document_id&&d.latest_version!==p.version_id));
  let note=`Question: ${job.request.question}. Analysis ${localTime(job.updated_at)}. `;
  if(job.state==="failed")note+=`No validated AI answer: ${job.error}. Retrieved evidence is retained below.`;
  else if(answer?.insufficient_evidence)note+=answer.reason||"Insufficient evidence to answer the question. No unsupported answer has been substituted.";
  else if(answer?.reason)note+=answer.reason;
  else note+="AI draft — review required. Citations and numbers matched retrieved text; semantic correctness is not guaranteed.";
  if(result.degraded)note+=" A selected source failed. Stored passages may be stale; see source status.";
  if(revised)note+=" A cited document has a newer captured version. Run the question again to use it.";
  if(answer?.citation_context_added?.length)note+=" An exact title citation from the same document version was added to support the reported year.";
  $("live-answer-status").innerHTML=`<p class="live-answer-note ${job.state==="failed"||result.degraded||revised?"warning":""}">${esc(note)}</p>`;
  const timing=[['Client wall time',answer?.duration_ms],['Model loading',answer?.provider_metrics?.load_ms],['Prompt processing',answer?.provider_metrics?.prompt_eval_ms],['Token generation',answer?.provider_metrics?.eval_ms]]
    .filter(([,value])=>typeof value==='number'&&Number.isFinite(value)&&value>=0);
  if(timing.length)$("live-answer-status").innerHTML+=`<details><summary>Timing for this run</summary><dl>${timing.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${value.toFixed(1)} ms</dd>`).join('')}</dl><p>Provider stages are reported by Ollama. Client wall time includes the request and validation; it excludes source collection and retrieval. One run is not a latency benchmark.</p></details>`;
  $("live-statements").innerHTML=(answer?.statements||[]).map(statement=>`<article class="live-statement"><p>${esc(statement.text)}</p>${statement.citations.map(c=>`<button class="live-citation" data-live-citation="${esc(c.chunk_id)}">Evidence ${esc(c.chunk_id)}</button>`).join("")}</article>`).join("");
  $("live-evidence").innerHTML=(result.passages||[]).map(p=>`<article class="live-evidence" id="passage-${esc(p.chunk_id.replace(":","-"))}"><strong>${esc(p.title)}</strong><p>${esc(liveNames[p.source_id])} · Published ${esc(p.published_at?.slice(0,10)||"unknown")} · Captured ${esc(localTime(p.received_at))} · version ${p.version_id}</p><blockquote>${esc(p.body)}</blockquote><p>${esc(p.coverage)}</p>${link(p.url,"Publisher document")} <button class="live-citation" data-live-document="${esc(p.document_id)}">Inspect versions</button></article>`).join("")||"<p class=muted>No matching passages were retrieved.</p>";
  if(!answer?.statements?.length)$("live-passages").open=true;
}
async function pollJob(){
  try{
    const job=await json(`/api/live/jobs/${live.jobId}`);paintJob(job);
    if(["queued","running"].includes(job.state)){
      // GUESS: UI progress polling cadence, not source refresh or a latency claim.
      live.poll=setTimeout(pollJob,1000);return;
    }
    liveBusy(false);await refreshSnapshot();
    if(job.kind==="ask")paintAnswer(job);
    if(job.state==="failed")liveError(job.error||"Job failed");
    if(job.state==="cancelled")liveError("Cancelled. An in-flight HTTP/model request may finish, but its answer will not be accepted. Wait before starting another job.");
    scheduleSync();
  }catch(err){liveBusy(false);liveError(`Connection lost while following the job: ${err.message}. The server may still be working. Reconnect using a source check.`);scheduleSync();}
}
async function startLiveJob(kind){
  if(live.busy||!live.ready||!live.sources.size)return;
  const question=$("live-question").value.trim();if(kind==="ask"&&!question)return;
  clearTimeout(live.timer);liveError("");liveBusy(true);
  try{
    const job=await post(`/api/live/${kind}`,{source_ids:[...live.sources],question:kind==="ask"?question:"",document_ids:kind==="ask"?[...live.selected]:[],use_model:kind==="ask"&&$("live-engine").value==="model"});
    live.jobId=job.id;paintJob(job);pollJob();
  }catch(err){liveBusy(false);liveError(err.message);scheduleSync();}
}
function scheduleSync(){
  clearTimeout(live.timer);if(!live.ready||!live.enabled||!$("live-auto").checked)return;
  live.timer=setTimeout(()=>{if(!document.hidden&&!live.busy)startLiveJob("sync");else scheduleSync();},live.snapshot.poll_seconds*1000);
}
async function openDocument(id){
  try{
    const doc=await json(`/api/live/documents/${id}`), latest=doc.versions[0];
    const existing=document.querySelector("dialog.live-document-dialog");if(existing)existing.remove();
    const dialog=document.createElement("dialog");dialog.className="live-document-dialog";
    dialog.innerHTML=`<div class="section-heading"><h3>${esc(doc.title)}</h3><button autofocus aria-label="Close document">Close</button></div><p>${link(doc.url,"Open publisher document")}</p><p class="muted">${esc(latest.coverage)} · Captured ${esc(localTime(latest.received_at))} · ${doc.versions.length} stored version(s)</p><div class="capture">${esc(latest.body)}</div><details><summary>Changes from the previous captured version</summary>${doc.diff!==null?`<pre class="diff">${esc(doc.diff||"Text unchanged; document metadata changed.")}</pre>`:"<p>No earlier version was captured. No historical change is inferred.</p>"}</details><details><summary>Version manifest</summary>${doc.versions.map(v=>`<p class="muted">Version ${v.id} · ${esc(localTime(v.received_at))}<br><code>${esc(v.text_hash)}</code></p>`).join("")}</details>`;
    document.body.append(dialog);dialog.querySelector("button").onclick=()=>dialog.close();dialog.addEventListener("close",()=>dialog.remove());dialog.showModal();
  }catch(err){liveError(err.message);}
}
async function bootLive(){
  liveError("");
  // GitHub Pages is deliberately not treated as an AI/backend host.
  if(!["127.0.0.1","localhost","[::1]"].includes(location.hostname)){
    $("live-mode").textContent="Backend required";$("live-unavailable").hidden=false;return;
  }
  try{
    await refreshSnapshot();live.ready=true;$("live-mode").textContent="Live connections · local backend";$("live-unavailable").hidden=true;liveBusy(false);
    const pending=live.snapshot.jobs.find(job=>["queued","running"].includes(job.state));
    if(pending){live.jobId=pending.id;liveBusy(true);pollJob();}else startLiveJob("sync");
  }catch(err){$("live-mode").textContent="Backend unavailable";$("live-unavailable").hidden=false;liveError(`Live connection unavailable: ${err.message}. No recorded data is being shown as live.`);}
}
$("open-live").onclick=()=>setDeskMode("live");$("open-recorded").onclick=()=>setDeskMode("recorded");
$("live-refresh").onclick=()=>startLiveJob("sync");
$("live-question-form").onsubmit=event=>{event.preventDefault();startLiveJob("ask");};
$("live-search").oninput=paintDocuments;
$("live-auto").onchange=scheduleSync;
$("live-sources").onchange=event=>{const input=event.target;if(!input.matches("input"))return;input.checked?live.sources.add(input.value):live.sources.delete(input.value);live.selected.clear();paintDocuments();liveBusy(live.busy);};
$("live-documents").onchange=event=>{if(!event.target.matches("input"))return;const id=event.target.value;if(event.target.checked&&live.selected.size>=10){event.target.checked=false;liveError("Select at most 10 documents, or leave all unchecked to search the full collection.");return;}event.target.checked?live.selected.add(id):live.selected.delete(id);paintDocuments();};
document.addEventListener("click",async event=>{
  const prompt=event.target.closest("[data-question]");if(prompt){$("live-question").value=prompt.dataset.question;$("live-question").focus();}
  const doc=event.target.closest("[data-live-document]");if(doc)openDocument(doc.dataset.liveDocument);
  const citation=event.target.closest("[data-live-citation]");if(citation){$("live-passages").open=true;$("passage-"+citation.dataset.liveCitation.replace(":","-")).scrollIntoView({block:"center"});}
  const jobButton=event.target.closest("[data-live-job]");if(jobButton){try{const job=await json(`/api/live/jobs/${jobButton.dataset.liveJob}`);paintJob(job);if(job.kind==="ask")paintAnswer(job);}catch(err){liveError(err.message);}}
});
$("live-cancel").onclick=async()=>{try{await post(`/api/live/jobs/${live.jobId}/cancel`,{});}catch(err){liveError(err.message);}};
$("live-export").onclick=()=>{if(live.answerJob)download("info-desk-live-research.json",JSON.stringify({label:"LIVE_SOURCE_RESEARCH — HUMAN REVIEW REQUIRED",job:live.answerJob},null,2),"application/json");};
document.addEventListener("visibilitychange",()=>{if(!document.hidden)scheduleSync();});
// The hosted page cannot fetch, persist or run a model, so it opens on the recorded
// case. Only a local backend defaults to the live desk; ?mode= still overrides both.
const requestedMode=new URLSearchParams(location.search).get("mode");
const backendPossible=["127.0.0.1","localhost","[::1]"].includes(location.hostname);
setDeskMode(requestedMode==="live"||(requestedMode!=="recorded"&&backendPossible)?"live":"recorded");
