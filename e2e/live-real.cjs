// MANUAL integration check. Real official sources and the configured local model.
// Not part of CI; no SYNTHETIC data. No external publication or approvals.
const {chromium}=require("playwright");
const fs=require("node:fs");
const path=require("node:path");
const assert=require("node:assert/strict");
const output=path.resolve(__dirname,"../test-results");
fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000},baseURL:"http://127.0.0.1:8000"}), errors=[];
    page.on("pageerror",err=>errors.push(err.message));
    await page.goto("http://127.0.0.1:8000/");
    await page.locator("#live-auto").uncheck();
    // GUESS: generous manual integration-test deadline, not a latency target.
    await page.waitForFunction(()=>document.querySelector("#live-job-state").textContent.includes("completed"),{},{timeout:90000});
    const snapshot=await (await page.request.get("/api/live/status")).json();
    console.log("REAL_SOURCES",JSON.stringify(Object.fromEntries(Object.entries(snapshot.checks).map(([id,c])=>[id,{status:c.status,detail:c.detail,checked_at:c.checked_at}]))));
    assert(snapshot.documents.length>0,"No real documents received");
    await page.screenshot({path:path.join(output,"live-real-inbox.png"),fullPage:true});
    await page.locator("#live-search").fill("LNG exports");
    const matches=await page.locator("#live-documents input").count();
    if(!matches)throw new Error("The live feed no longer contains the LNG example; choose a new grounded question.");
    await page.locator("#live-documents input").first().check();
    await page.locator("#live-question").fill("What does EIA report about U.S. LNG exports in the first half of 2026?");
    await page.locator("#live-engine").selectOption("model");
    await page.locator("#live-ask").click();
    await page.waitForFunction(()=>document.querySelector("#live-job-state").textContent.startsWith("Research")&&/completed|failed/.test(document.querySelector("#live-job-state").textContent),{},{timeout:140000});
    const status=await (await page.request.get("/api/live/status")).json();
    const latest=status.jobs.find(job=>job.kind==="ask");
    const job=await (await page.request.get(`/api/live/jobs/${latest.id}`)).json();
    fs.writeFileSync(path.join(output,"live-real-job.json"),JSON.stringify(job,null,2));
    console.log("REAL_JOB",JSON.stringify({state:job.state,error:job.error,answer:job.result?.answer,passages:job.result?.passages?.length}));
    await page.screenshot({path:path.join(output,"live-real-answer.png"),fullPage:true});
    assert.equal(job.state,"completed");assert(job.result.answer.statements.length>0);
    await page.locator("#live-statements [data-live-citation]").first().click();
    assert(await page.locator("#live-passages").getAttribute("open")!==null);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),"Mobile overflow");
    await page.screenshot({path:path.join(output,"live-real-mobile.png"),fullPage:true});
    assert.deepEqual(errors,[]);console.log("PASS real source ingestion, AI brief, citation navigation and mobile layout");
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
