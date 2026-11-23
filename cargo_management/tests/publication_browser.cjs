// Explicit disposable UI/print verification; never runs during installation.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');

(async()=>{
 const {CARGO_TEST_URL:base,CARGO_TEST_SITE:site,CARGO_TEST_RUN:run,CARGO_TEST_ADMIN_PASSWORD:password}=process.env;
 assert(/^[a-f0-9]{16}$/.test(run||''),'Explicit disposable run is required');
 assert.equal(site,`cargo-publication-${run}.localhost`);
 const url=new URL(base);
 assert(['127.0.0.1','localhost',site].includes(url.hostname),'Use an owned disposable address');
 assert(password,'Supply the disposable password privately');
 const output=process.env.CARGO_TEST_OUTPUT_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'cargo-test-'));
 fs.mkdirSync(output,{recursive:true,mode:0o700});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CARGO_TEST_CHROMIUM_PATH||undefined,
  args:['--no-sandbox','--disable-dev-shm-usage']});
 const checks=[];
 try{
  const context=await browser.newContext({baseURL:base});
  const login=await context.request.post('/api/method/login',{form:{usr:'Administrator',pwd:password}});
  assert.equal(login.status(),200,'Disposable login');
  const response=await context.request.get('/api/method/cargo_management.tests.isolated_fixtures.browser_context');
  assert.equal(response.status(),200,'Guarded disposable context');
  const ctx=(await response.json()).message;
  assert.equal(ctx.run,run);assert.equal(ctx.site,site);
  const page=await context.newPage();
  await page.goto('/desk/cargo-management');
  await page.waitForFunction(()=>window.frappe?.boot?.user?.name==='Administrator');
  await page.waitForFunction(()=>document.body.innerText.includes('Cargo Management'));
  checks.push('workspace');
  const logo=await context.request.get('/assets/cargo_management/images/cargo-management-logo.webp');
  assert.equal(logo.status(),200);assert.equal((await logo.body()).subarray(0,4).toString(),'RIFF');
  checks.push('latest logo');
  for(const dt of ctx.parents){
   await page.evaluate(async name=>{
    if(window.cur_frm?.doc)cur_frm.doc.__unsaved=0;
    await frappe.model.with_doctype(name);
    const doc=frappe.model.get_new_doc(name);
    frappe.set_route('Form',name,doc.name);
   },dt);
   await page.waitForFunction(name=>window.cur_frm?.doctype===name,dt,{timeout:30000});
   assert(await page.locator('.form-layout').count(),dt+' form');
   checks.push('form '+dt);
  }
  for(const name of ctx.reports){
   const filters={company:ctx.company,from_date:'2000-01-01',to_date:'2099-01-01'};
   const result=await context.request.get('/api/method/frappe.desk.query_report.run',
    {params:{report_name:name,filters:JSON.stringify(filters),ignore_prepared_report:'1'}});
   assert.equal(result.status(),200,name+' report');
   const data=(await result.json()).message;
   assert(Array.isArray(data.columns),name+' columns');assert(Array.isArray(data.result),name+' rows');
   await page.evaluate(report=>{if(window.cur_frm?.doc)cur_frm.doc.__unsaved=0;frappe.set_route('query-report',report);},name);
   await page.waitForFunction(report=>frappe.query_report?.report_name===report,name,{timeout:30000});
   checks.push('report '+name);
  }
  for(const format of ctx.formats){
   const result=await context.request.get('/api/method/frappe.utils.print_format.download_pdf',
    {params:{doctype:'Sales Invoice',name:ctx.invoice,format,no_letterhead:'1'}});
   assert.equal(result.status(),200,format+' PDF');
   const bytes=await result.body();assert.equal(bytes.subarray(0,4).toString(),'%PDF');
   const target=path.join(output,format.replace(/[^a-z0-9]/gi,'_')+'.pdf');fs.writeFileSync(target,bytes);
   const python=path.resolve(__dirname,'../../../../env/bin/python');
   const resultText=execFileSync(python,['-B','-c',
    'from pypdf import PdfReader; import json,sys; r=PdfReader(sys.argv[1]); print(json.dumps({"pages":len(r.pages),"text":" ".join(p.extract_text() or "" for p in r.pages)}))',target],{encoding:'utf8'});
   const parsed=JSON.parse(resultText);assert(parsed.pages>0);assert(parsed.text.replace(/\s/g,'').includes(ctx.invoice.replace(/\s/g,'')));
   checks.push('PDF '+format);
  }
  await page.goto('/printview?'+new URLSearchParams({doctype:'Sales Invoice',name:ctx.invoice,format:ctx.formats.find(x=>/qr/i.test(x)),no_letterhead:'1'}));
  const pixels=await page.evaluate(async()=>{
   const img=document.querySelector('img[src^="data:image/png;base64,"]');if(!img)throw Error('Missing QR');
   await img.decode();const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
   const c=canvas.getContext('2d');c.drawImage(img,0,0);const rgba=c.getImageData(0,0,canvas.width,canvas.height).data;
   const rgb=[];for(let i=0;i<rgba.length;i+=4)rgb.push((rgba[i]<<16)|(rgba[i+1]<<8)|rgba[i+2]);
   return {width:canvas.width,height:canvas.height,rgb};
  });
  const frappeRoot=process.env.CARGO_TEST_FRAPPE_PATH||path.resolve(__dirname,'../../../frappe');
  const zxing=require(path.join(frappeRoot,'node_modules/html5-qrcode/third_party/zxing-js.umd.js'));
  const decoded=new zxing.QRCodeReader().decode(new zxing.BinaryBitmap(new zxing.HybridBinarizer(
   new zxing.RGBLuminanceSource(Int32Array.from(pixels.rgb),pixels.width,pixels.height)))).getText();
  assert(decoded.includes(encodeURIComponent(ctx.invoice))||decoded.includes(ctx.invoice));
  const qr=new URL(decoded);assert.equal(qr.username,'');assert.equal(qr.password,'');
  assert(!/token|password|api_key/i.test(qr.search));checks.push('independently decoded QR');
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,run,checks},null,2));
  console.log(JSON.stringify({passed:true,checks:checks.length,forms:ctx.parents.length,reports:ctx.reports.length,pdfs:ctx.formats.length}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
