// Browser checks use real recorded excerpts. API outage tests are SYNTHETIC faults.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const {spawn} = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const root = path.resolve(__dirname,"..");
const temp = fs.mkdtempSync(path.join(os.tmpdir(),"infodesk-SYNTHETIC-browser-"));
const output = path.join(root,"test-results");
fs.mkdirSync(output,{recursive:true});
// SOURCE: test-only loopback ports; no domain thresholds or latency benchmark.
const apiUrl = "http://127.0.0.1:8766";
const staticUrl = "http://127.0.0.1:8767/info-desk/";
const python = spawn(process.env.PYTHON || "python",["-m","uvicorn","infodesk.app:app","--host","127.0.0.1","--port","8766"],{cwd:root,env:{...process.env,INFODESK_DB:path.join(temp,"test.sqlite3"),OLLAMA_URL:""},windowsHide:true,stdio:["ignore","pipe","pipe"]});
let logs="";python.stdout.on("data",chunk=>logs+=chunk);python.stderr.on("data",chunk=>logs+=chunk);
const staticServer=http.createServer((req,res)=>{
  const name=new URL(req.url,staticUrl).pathname.replace(/^\/info-desk\//,"") || "index.html";
  if(!["index.html","desk.css","desk.js","live.css","live.js","workbench.json","harness.json","case.json"].includes(name)){res.writeHead(404).end();return;}
  const types={".html":"text/html",".css":"text/css",".js":"text/javascript",".json":"application/json"};
  res.setHeader("Content-Type",types[path.extname(name)]);res.end(fs.readFileSync(path.join(root,"public",name)));
});
let browser;
async function ready(){for(let attempt=0;attempt<60;attempt++){try{if((await fetch(apiUrl+"/api/health")).ok)return;}catch{}await new Promise(resolve=>setTimeout(resolve,250));}throw new Error("API did not start: "+logs);}
async function stable(page){await page.waitForFunction(()=>document.querySelector("#workspace").getAttribute("aria-busy")==="false" && !document.querySelector("#result").hidden);}
async function noOverflow(page){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),"page has horizontal overflow");}
async function workflow(width, height){
  const page=await browser.newPage({viewport:{width,height}}), errors=[];page.on("pageerror",err=>errors.push(err.message));
  await page.goto(staticUrl+"?mode=recorded");await stable(page);assert.equal(await page.locator("#mode").innerText(),"Recorded replay");
  assert.equal(await page.locator("#claims tbody tr").count(),16);await noOverflow(page);
  await page.screenshot({path:path.join(output,`desktop-${width}.png`),fullPage:true});
  await page.locator("#search").fill("royalties");assert.equal(await page.locator("#claims tbody tr").count(),1);
  await page.locator("#claims tbody button").click();assert.match(await page.locator("#inspector").innerText(),/200 billion/);
  await page.locator("#search").fill("no such claim SYNTHETIC");assert(await page.locator("#empty").isVisible());
  await page.locator("#search").fill("");await page.locator("#filter").selectOption("shared");assert(await page.locator("#claims tbody tr").count()>0);
  const ids=["ofac","white-house","ap"];
  for(let mask=1;mask<(1<<ids.length);mask++){
    for(let i=0;i<ids.length;i++)await page.locator(`#source-options input[value="${ids[i]}"]`).setChecked(!!(mask&(1<<i)));
    await page.locator("#compare").click();await stable(page);
    const expected=ids.filter((_,i)=>mask&(1<<i));assert.equal(await page.locator("#claims thead th").count(),expected.length+1);
    await noOverflow(page);
  }
  for(const id of ids)await page.locator(`#source-options input[value="${id}"]`).uncheck();assert(await page.locator("#compare").isDisabled());
  await page.locator('[data-scenario="ranking"]').first().click();assert.equal(await page.locator("#decision").innerText(),"Hold");
  await page.locator('[data-scenario="jailbreak"]').first().click();assert.match(await page.locator("#result-context").innerText(),/SYNTHETIC/);assert.match(await page.locator("#trace").innerText(),/SYNTHETIC_ATTACK/);
  await page.locator('[data-scenario="retry-429"]').first().click();assert.match(await page.locator("#db").textContent(),/429/);
  await page.locator('[data-scenario="ranking"]').first().click();
  await page.locator("#tab-review").click();await page.locator("#findings input").first().check();
  await page.locator("#review-notes").fill("SYNTHETIC reviewer note for export test");
  await page.screenshot({path:path.join(output,`review-${width}.png`),fullPage:true});
  const downloadPromise=page.waitForEvent("download");await page.locator("#export-md").click();const download=await downloadPromise;assert.equal(download.suggestedFilename(),"info-desk-review.md");
  const content=fs.readFileSync(await download.path(),"utf8");assert.match(content,/NOT PUBLISHED/);assert.match(content,/SYNTHETIC reviewer note/);assert.match(content,/SHA-256/);
  assert(await page.locator("#approve").isDisabled());assert(await page.locator("#reject").isDisabled());
  const jsonPromise=page.waitForEvent("download");await page.locator("#export-json").click();assert.equal((await jsonPromise).suggestedFilename(),"info-desk-evidence.json");
  await page.locator('[data-scenario="retry-429"]').first().click();
  await page.locator('[data-scenario="ranking"]').first().click();await page.locator("#tab-review").click();
  assert.equal(await page.locator("#review-notes").inputValue(),"SYNTHETIC reviewer note for export test");
  assert(await page.locator("#findings input").first().isChecked());assert(await page.locator("#compare").isEnabled());
  await page.locator("#tab-review").focus();await page.keyboard.press("ArrowRight");assert.equal(await page.locator("#tab-evaluations").getAttribute("aria-selected"),"true");
  assert.deepEqual(errors,[]);await page.close();console.log(`PASS recorded workflow ${width}x${height}`);
}
async function liveWorkflow(width){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on("pageerror",err=>errors.push(err.message));
  const timestamp="2026-09-09T12:00:00+00:00";
  const document={id:"SYNTHETIC-doc",source_id:"eia",title:"SYNTHETIC gas production update",url:"https://www.eia.gov/todayinenergy/SYNTHETIC",published_at:timestamp,first_seen:timestamp,last_seen:timestamp,latest_version:2,version_count:2,coverage:"SYNTHETIC summary",text_hash:"SYNTHETIC-hash"};
  const passage={...document,document_id:document.id,chunk_id:"2:0",version_id:2,received_at:timestamp,body:"SYNTHETIC gas output reached 14 units."};
  const snapshot={sources:[{id:"eia",name:"EIA · SYNTHETIC test",coverage:"SYNTHETIC summary"}],checks:{eia:{status:"ok",detail:"SYNTHETIC HTTP success",checked_at:timestamp,next_check_at:timestamp}},documents:[document],jobs:[],poll_seconds:60,model_available:true,model:"SYNTHETIC model (not called)"};
  let job,failAnswer=false;
  await page.route("**/api/live/**",async route=>{
    const url=new URL(route.request().url()),method=route.request().method();let payload;
    if(url.pathname.endsWith("/status"))payload=snapshot;
    else if(method==="POST"&&/\/(sync|ask)$/.test(url.pathname)){
      const request=route.request().postDataJSON(),kind=url.pathname.split("/").pop();
      job={id:"SYNTHETIC-job",kind,state:kind==="ask"&&failAnswer?"failed":"completed",request,created_at:timestamp,updated_at:timestamp,trace:[{step:"SYNTHETIC test checkpoint",at:timestamp}],error:failAnswer?"SYNTHETIC citation validation failure":null,result:{source_checks:[],degraded:false,passages:kind==="ask"?[passage]:[],answer:kind==="ask"&&!failAnswer?{statements:[{text:"SYNTHETIC gas output reached 14 units.",citations:[{chunk_id:"2:0",quote:"gas output reached 14 units."}]}],insufficient_evidence:false}:null}};payload=job;
    }else if(url.pathname.includes("/jobs/"))payload=job;
    else if(url.pathname.includes("/documents/"))payload={...document,versions:[{id:2,body:passage.body,received_at:timestamp,coverage:document.coverage,text_hash:"SYNTHETIC-new"},{id:1,body:"SYNTHETIC gas output reached 12 units.",received_at:timestamp,coverage:document.coverage,text_hash:"SYNTHETIC-old"}],diff:"-SYNTHETIC gas output reached 12 units.\n+SYNTHETIC gas output reached 14 units."};
    else throw new Error("Unmocked live endpoint: "+url.pathname);
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(payload)});
  });
  await page.goto(apiUrl);await page.waitForFunction(()=>document.querySelector("#live-refresh").disabled===false&&document.querySelector("#live-job-state").textContent.includes("completed"));
  await page.locator("#live-auto").uncheck();assert(await page.locator("#workspace").isHidden());await noOverflow(page);
  await page.locator("#live-documents [data-live-document]").click();await page.getByRole("dialog").waitFor();assert.match(await page.getByRole("dialog").innerText(),/2 stored version/);await page.getByRole("button",{name:"Close document"}).click();
  await page.locator("#live-documents input").check();await page.locator("#live-question").fill("SYNTHETIC gas output?");await page.locator("#live-ask").click();await page.locator("#live-statements .live-statement").waitFor();
  assert.deepEqual(job.request.document_ids,["SYNTHETIC-doc"]);
  await page.locator("#live-statements [data-live-citation]").click();assert(await page.locator("#live-passages").getAttribute("open")!==null);
  const downloadPromise=page.waitForEvent("download");await page.locator("#live-export").click();const download=await downloadPromise;assert.equal(download.suggestedFilename(),"info-desk-live-research.json");
  const exported=JSON.parse(fs.readFileSync(await download.path(),"utf8"));assert.match(exported.label,/HUMAN REVIEW REQUIRED/);
  await noOverflow(page);await page.screenshot({path:path.join(output,`live-SYNTHETIC-${width}.png`),fullPage:true});
  failAnswer=true;await page.locator("#live-ask").click();await page.locator("#live-error").waitFor();assert.match(await page.locator("#live-answer-status").innerText(),/No validated AI answer/);assert.equal(await page.locator("#live-statements .live-statement").count(),0);assert.match(await page.locator("#live-evidence").innerText(),/14 units/);
  assert.deepEqual(errors,[]);await page.close();console.log(`PASS SYNTHETIC live workflow, citations, versions and failed-answer state ${width}px`);
}
(async()=>{
  await new Promise(resolve=>staticServer.listen(8767,"127.0.0.1",resolve));await ready();browser=await chromium.launch({headless:true});
  for(const viewport of [[1440,1000],[820,1000],[390,844]])await workflow(...viewport);
  const page=await browser.newPage();await page.goto(apiUrl+"/?mode=recorded");await stable(page);assert.equal(await page.locator("#mode").innerText(),"Local Python + SQLite");
  await page.locator("#compare").click();await stable(page);await page.locator("#tab-review").click();assert(await page.locator("#approve").isDisabled());assert(await page.locator("#reject").isEnabled());
  await page.locator("#reject").click();await page.waitForFunction(()=>document.querySelector("#decision-feedback").textContent.startsWith("Rejected"));assert(await page.locator("#reject").isDisabled());
  assert.equal((await (await fetch(apiUrl+"/api/db")).json()).notes,0);console.log("PASS local execution and persisted rejection");
  await page.route("**/api/analyses",route=>route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"SYNTHETIC API outage"})}));
  await page.locator("#compare").click();await page.locator("#error").waitFor();assert.match(await page.locator("#error").innerText(),/SYNTHETIC API outage/);assert(await page.locator("#compare").isEnabled());console.log("PASS SYNTHETIC API outage keeps prior result and enables retry");
  await page.close();const failed=await browser.newPage();await failed.route("**/workbench.json",route=>route.fulfill({status:503,body:"SYNTHETIC failure"}));await failed.goto(staticUrl+"?mode=recorded");await failed.locator("#error").waitFor();assert(await failed.locator("#compare").isDisabled());console.log("PASS SYNTHETIC missing replay error state");await failed.close();
  for(const width of [1440,390])await liveWorkflow(width);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();python.kill();staticServer.close();console.log("Screenshots:",output);});
