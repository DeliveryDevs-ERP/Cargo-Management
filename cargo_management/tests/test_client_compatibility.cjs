// Targeted current-source UI regressions. No database, network or saved records.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const app=path.resolve(__dirname,'..');
const train='cargo_management/doctype/fpl_perform_middle_mile/fpl_perform_middle_mile.js';
const freight='cargo_management/doctype/fpl_freight_orders/fpl_freight_orders.js';

test('Train Link validation retains its own selection while excluding allocations in other rows',()=>{
 const f=fixture(train);f.frm.doc.middle_mile=[{name:'A',container:'CA'},{name:'B',container:'CB'}];
 f.handlers['FPL Perform Middle Mile'].setup(f.frm);
 const getQuery=f.frm.fields_dict.middle_mile.grid.get_field('container').get_query;
 assert.deepEqual(Array.from(getQuery(f.frm.doc,'FPL MM cdt','A').filters.not_in_container),['CB']);
 assert.deepEqual(Array.from(getQuery(f.frm.doc,'FPL MM cdt','B').filters.not_in_container),['CA']);
});
test('Booking Company and semantic Yard timestamp controls are portable without legacy service IDs',()=>{
 const booking=JSON.parse(fs.readFileSync(path.join(app,'cargo_management/doctype/booking_order/booking_order.json')));
 assert.equal(booking.fields.find(f=>f.fieldname==='company').hidden,0);
 const yard=JSON.parse(fs.readFileSync(path.join(app,'cargo_management/doctype/fplyardjob/fplyardjob.json')));
 assert.equal(yard.fields.find(f=>f.fieldname==='gate_in').depends_on,"eval: doc.job_name === 'Gate In';");
 assert.equal(yard.fields.find(f=>f.fieldname==='gate_out').depends_on,"eval: doc.job_name === 'Gate Out';");
});
test('Cross-Stuff native cancellation ignores only the journal-restored Request backlink',()=>{
 const f=fixture('cargo_management/doctype/perform_cross_stuff/perform_cross_stuff.js');
 f.handlers['Perform Cross Stuff'].setup(f.frm);
 assert.deepEqual(Array.from(f.frm.ignore_doctypes_on_cancel_all),['Container or Vehicle Request']);
 f.handlers['Perform Cross Stuff'].setup(f.frm);
 assert.equal(f.frm.ignore_doctypes_on_cancel_all.length,1);
});
test('Cost lookup returns a catalogue without whole-document synchronization and discards stale scope replies',async()=>{
 const f=fixture(train);f.frm.doc.company='Company-A';f.frm.doctype='FPL Perform Middle Mile';
 f.frm.call=()=>{throw Error('A catalogue must not synchronize a full document');};
 let resolve;f.frappe.call=options=>{assert.equal(options.method,'cargo_management.expense_controls.get_cost_catalog');assert.equal(options.args.docname,'UI-ONLY');return new Promise(r=>{resolve=r;});};
 const pending=f.context.set_cost_type_filter(f.frm,'Train Job');f.frm.doc.company='Company-B';resolve({message:[{name:'COST-A'}]});await pending;
 assert.equal(f.frm.fields_dict.expenses.grid.get_field('expense_type').get_query,undefined);
 f.frappe.call=async()=>({message:[{name:'COST-B'}]});await f.context.set_cost_type_filter(f.frm,'Train Job');
 assert.deepEqual(Array.from(f.frm.fields_dict.expenses.grid.get_field('expense_type').get_query().filters.name[1]),['COST-B']);
});

function fixture(file){
 const handlers={},calls=[],buttons={},messages=[],locals={};
 const state={reply:[],prompt:{},scope:null,inserted:[],routes:[],confirm:true,canCreate:true,dirty:0,reloaded:0};
 const frm={doc:{name:'UI-ONLY',doctype:'FPL Perform Middle Mile',company:null,finish_train_formation:0,
  finish_loading:0,finish_departure:0,finish_arrival:0,departure_location:'Yard-A',arrival_location:'Yard-B',
  movement_type:'Up',middle_mile:[],middle_mile_copy:[],middle_mile_in_loading:[],wagons:[],expenses:[],jobs:[]},
  fields_dict:{},is_dirty:()=>false,dirty:()=>state.dirty++,refresh_field:()=>{},
  clear_table:field=>{frm.doc[field]=[];},add_child:field=>{const row={};frm.doc[field].push(row);return row;},
  add_custom_button:(label,callback,group)=>{buttons[label]=callback;(state.buttonGroups??={})[label]=group;},
  set_value:async(field,value)=>{if(typeof field==='object')Object.assign(frm.doc,field);else frm.doc[field]=value;state.dirty++;},
  set_query:(field,fn)=>{frm.fields_dict[field]??={};frm.fields_dict[field].get_query=fn;},
  reload_doc:async()=>{state.reloaded++;},refresh:()=>{},save:()=>{throw Error('Saving is forbidden in UI tests');},
  call:async(method)=>{calls.push({method});return {message:[]};}};
 for(const field of ['expenses','middle_mile','middle_mile_copy','middle_mile_in_loading']){
  const fields={};frm.fields_dict[field]={grid:{get_field:name=>fields[name]??=( {})}};
 }
 const frappe={ui:{form:{on:(dt,events)=>{handlers[dt]??={};Object.assign(handlers[dt],events);}}},
  user_roles:['Accounts User'],model:{can_create:()=>state.canCreate,with_doctype:async()=>{},
   get_new_doc:dt=>({doctype:dt,docstatus:0,items:[]}),add_child:(doc,field)=>{const r={};doc[field].push(r);return r;},
   set_value:async(dt,name,field,value)=>{locals[dt][name][field]=value;}},
  call:async options=>{calls.push(options);const response={message:state.respond?state.respond(options):state.scope??state.reply};if(options.callback)options.callback(response);return response;},
  prompt:(fields,callback)=>{state.promptFields=fields;callback(state.prompt);},
  msgprint:message=>messages.push(message),throw:message=>{throw Error(message);},
  confirm:(message,yes,no)=>{state.confirmMessage=message;state.confirm?yes():no();},
  db:{insert:async doc=>{state.inserted.push(doc);return {...doc,name:'UI-ONLY-NEW'};}},
  get_doc:(dt,name)=>locals[dt][name],
  set_route:(...args)=>state.routes.push(args),datetime:{now_date:()=> '2026-11-13'}};
 const context=vm.createContext({frappe,locals,console:{log:()=>{},error:()=>{}},
  __:text=>text,$:{each:(rows,fn)=>rows.forEach((r,i)=>fn(i,r))}});
 vm.runInContext(fs.readFileSync(path.join(app,file),'utf8'),context,{filename:file});
 return {handlers,calls,buttons,messages,frm,state,frappe,locals,context};
}
const refresh=f=>f.handlers['FPL Perform Middle Mile'].refresh(f.frm);

test('Train Company uses the sole authorized Company and keeps it read-only',async()=>{
 const f=fixture(train),properties={};f.frm.is_new=()=>true;
 f.frm.set_df_property=(name,key,value)=>{properties[key]=value;};
 f.frm.doc.company='Unrelated global default';
 f.frappe.call=async()=>({message:{companies:['Company-A'],sole_company:'Company-A'}});
 await f.context.set_train_company_context(f.frm);
 assert.equal(f.frm.doc.company,'Company-A');assert.equal(properties.read_only,true);assert.equal(properties.reqd,true);
 assert.deepEqual(Array.from(f.frm.fields_dict.company.get_query().filters.name[1]),['Company-A']);
});
test('Train Company requires a choice for multiple Companies and locks saved ownership',async()=>{
 const f=fixture(train),properties={};f.frm.is_new=()=>true;
 f.frm.set_df_property=(name,key,value)=>{properties[key]=value;};
 f.frm.doc.company='Company-B';
 f.frappe.call=async()=>({message:{companies:['Company-A','Company-B'],sole_company:null}});
 await f.context.set_train_company_context(f.frm);
 assert.equal(f.frm.doc.company,null);assert.equal(properties.read_only,false);
 f.frm.doc.company='Company-A';f.frm.is_new=()=>false;
 f.context.present_train_company(f.frm);assert.equal(properties.read_only,true);assert.equal(properties.reqd,false);
});
test('A delayed Company context reply cannot overwrite a user selection',async()=>{
 const f=fixture(train);f.frm.is_new=()=>true;f.frm.set_df_property=()=>{};
 f.frm.doc.company='Company-B';let resolve;
 f.frappe.call=()=>new Promise(r=>{resolve=r;});
 const pending=f.context.set_train_company_context(f.frm);
 f.frm.doc.company='Company-A';f.frm._cargo_company_user_selected=true;
 resolve({message:{companies:['Company-A','Company-B'],sole_company:null}});await pending;
 assert.equal(f.frm.doc.company,'Company-A');
});

test('Fetch Wagons preserves existing selections and repeated fetching is idempotent',()=>{
 const f=fixture(train);Object.assign(f.frm.doc,{wagons:[{wagon_number:'W1',wagon_type:'Large'}],
  middle_mile:[{container:'C1',wagon_number:'W1'}]});
 f.state.reply=[{wagon_number:'W1',wagon_type:'Large',container:'C1'},
  {wagon_number:'W2',wagon_type:'Small',container:'C2',size:20,weight:12}];refresh(f);
 f.buttons['Fetch Wagons from Undeparted Trains']();
 assert.deepEqual(f.frm.doc.wagons.map(r=>r.wagon_number),['W1','W2']);
 assert.deepEqual(f.frm.doc.middle_mile.map(r=>r.container),['C1','C2']);
 f.buttons['Fetch Wagons from Undeparted Trains']();
 assert.equal(f.frm.doc.wagons.length,2);assert.equal(f.frm.doc.middle_mile.length,2);
 assert.equal(f.calls[0].args.departure_location,'Yard-A');assert.equal(f.calls[0].args.movement_type,'Up');
});
test('Fetch Wagons requires station and direction without erasing rows',()=>{
 const f=fixture(train);f.frm.doc.departure_location=null;f.frm.doc.wagons=[{wagon_number:'W1'}];refresh(f);
 f.buttons['Fetch Wagons from Undeparted Trains']();assert.equal(f.calls.length,0);assert.equal(f.frm.doc.wagons.length,1);assert.equal(f.messages.length,1);
});
test('Train custom-button visibility preserves the phase predicates',()=>{
 for(const [formation,departure,arrival,fetch,receive]of [[0,0,0,true,false],[1,1,0,false,true],[1,1,1,false,false]]){
  const f=fixture(train);Object.assign(f.frm.doc,{finish_train_formation:formation,finish_departure:departure,finish_arrival:arrival});refresh(f);
  assert.equal(!!f.buttons['Fetch Wagons from Undeparted Trains'],fetch);assert.equal(!!f.buttons['Receive All'],receive);
 }
});
test('Depart All marks changed child rows as unsaved without saving',()=>{
 const f=fixture(train);f.frm.doc.middle_mile_in_loading=[{departed_:0},{departed_:0}];
 f.handlers['FPL Perform Middle Mile'].depart_all(f.frm);assert(f.frm.doc.middle_mile_in_loading.every(r=>r.departed_===1));assert.equal(f.state.dirty,1);
});
test('Receive All marks changed child rows as unsaved without posting',()=>{
 const f=fixture(train);Object.assign(f.frm.doc,{finish_train_formation:1,finish_departure:1,middle_mile_copy:[{received_:0},{received_:0}]});refresh(f);
 f.buttons['Receive All']();assert(f.frm.doc.middle_mile_copy.every(r=>r.received_===1));assert.equal(f.state.dirty,1);
});
for(const action of ['cancel_loading','cancel_departure']){
 test(action+' refuses unsaved edits before RPC',async()=>{
  const f=fixture(train);f.frm.is_dirty=()=>true;await assert.rejects(f.handlers['FPL Perform Middle Mile'][action](f.frm),/Save or reload/);assert.equal(f.calls.length,0);
 });
 test(action+' uses the guarded server method then reloads',async()=>{
  const f=fixture(train);await f.handlers['FPL Perform Middle Mile'][action](f.frm);
  assert(f.calls[0].method.endsWith('.'+action));assert.equal(f.calls[0].args.docname,'UI-ONLY');assert.equal(f.state.reloaded,1);
 });
}
test('Cancel Formation changes only the client draft until explicitly saved',()=>{
 const f=fixture(train);f.frm.doc.middle_mile=[{container:'C1'}];f.frm.doc.finish_train_formation=1;
 f.handlers['FPL Perform Middle Mile'].cancel_formation(f.frm);assert.equal(f.frm.doc.middle_mile.length,0);assert.equal(f.frm.doc.finish_train_formation,0);assert.equal(f.calls.length,0);
});
test('Fetch from Train prompt keeps Arrived filter and maps wagon metadata',()=>{
 const f=fixture(train);f.state.prompt={train_number:'ARRIVED-UI'};f.state.reply=[{wagon_number:'W1',wagon_type:'Large'}];
 f.handlers['FPL Perform Middle Mile'].fetch_wagons_from_train(f.frm);
 assert.equal(f.state.promptFields.get_query().filters.status,'Arrived');assert.equal(f.calls[0].args.train_number,'ARRIVED-UI');
 assert.equal(f.frm.doc.wagons[0].wagon_number,'W1');assert.equal(f.frm.doc.wagons[0].loaded_,0);
});
test('Container event synchronizes both related grids and updates exclusion query',()=>{
 const f=fixture(train);const row={name:'ROW',mm_job_id:'J1',container:'C2',wagon_number:'W2',job:'Middle Mile'};
 f.locals['FPL MM cdt']={ROW:row};Object.assign(f.frm.doc,{middle_mile:[row],middle_mile_in_loading:[{mm_job_id:'J1',container:'OLD'}],middle_mile_copy:[{mm_job_id:'J1',container:'OLD'}]});
 f.handlers['FPL MM cdt'].container(f.frm,'FPL MM cdt','ROW');
 assert.equal(f.frm.doc.middle_mile_in_loading[0].container,'C2');assert.equal(f.frm.doc.middle_mile_copy[0].wagon_number,'W2');
 assert.equal(f.frm.fields_dict.middle_mile.grid.get_field('container').get_query().filters.not_in_container[0],'C2');
});
test('Unbound train rows cannot overwrite other rows with an empty Rail Job identity',()=>{
 const f=fixture(train);const row={name:'ROW',container:'C2',wagon_number:'W2'};
 f.locals['FPL MM cdt']={ROW:row};Object.assign(f.frm.doc,{middle_mile:[row],middle_mile_in_loading:[{container:'KEEP-LOADING'}],middle_mile_copy:[{container:'KEEP-ARRIVAL'}]});
 f.handlers['FPL MM cdt'].container(f.frm,'FPL MM cdt','ROW');
 assert.equal(f.frm.doc.middle_mile_in_loading[0].container,'KEEP-LOADING');assert.equal(f.frm.doc.middle_mile_copy[0].container,'KEEP-ARRIVAL');
 assert.equal(f.frm.fields_dict.middle_mile.grid.get_field('container').get_query().filters.not_in_container[0],'C2');
});
test('Train expense query uses live received allocation IDs instead of reusable container text',()=>{
 const f=fixture(train);f.frm.doc.middle_mile_copy=[
  {container:'ALLOCATION-A',container_number:'REUSED0000001',received_:1},
  {container:'ALLOCATION-B',container_number:'REUSED0000001',received_:0}];
 f.handlers['FPL Perform Middle Mile'].setup(f.frm);
 const query=f.frm.fields_dict.expenses.grid.get_field('container_number').get_query;
 assert.deepEqual(Array.from(query().filters.name[1]),['ALLOCATION-A']);
 f.frm.doc.middle_mile_copy[1].received_=1;
 assert.deepEqual(Array.from(query().filters.name[1]),['ALLOCATION-A','ALLOCATION-B']);
});
test('Arrival confirmation is awaited and declining cannot advance the phase',async()=>{
 for(const yes of [true,false]){
  const f=fixture(train);f.state.confirm=yes;Object.assign(f.frm.doc,{finish_train_formation:1,finish_loading:1,finish_departure:1,actual_arrival_datetime:'2026-11-13 12:00:00',middle_mile_copy:[{received_:1}]});
  const action=f.handlers['FPL Perform Middle Mile'].before_save(f.frm);
  if(yes){await action;assert.equal(f.frm.doc.finish_arrival,1);}else{await assert.rejects(action,/cancelled/);assert.equal(f.frm.doc.finish_arrival,0);}
  assert.equal(f.calls.length,0);
 }
});
test('Native Save advances formation, loading and departure one phase at a time',async()=>{
 for(const phase of ['formation','loading','departure']){
  const f=fixture(train);Object.assign(f.frm.doc,{loading_time:'2026-11-13 08:00:00',loading_end_time:'2026-11-13 09:00:00',departure_time:'2026-11-13 10:00:00',middle_mile:[{container:'UI-C1'}],middle_mile_in_loading:[{departed_:1}]});
  if(phase!=='formation')f.frm.doc.finish_train_formation=1;
  if(phase==='departure')f.frm.doc.finish_loading=1;
  await f.handlers['FPL Perform Middle Mile'].before_save(f.frm);
  assert.equal(f.frm.doc.status,{formation:'Train Formed',loading:'Loaded',departure:'Departed'}[phase]);
  if(phase==='formation')assert.equal(f.frm.doc.finish_loading,0);
  if(phase==='loading')assert.equal(f.frm.doc.finish_departure,0);
  assert.equal(f.calls.length,0);
 }
});
test('Loading and departure reject missing allocations before persistence',async()=>{
 const loading=fixture(train);Object.assign(loading.frm.doc,{finish_train_formation:1,loading_time:'2026-11-13 08:00:00',loading_end_time:'2026-11-13 09:00:00'});
 await assert.rejects(loading.handlers['FPL Perform Middle Mile'].before_save(loading.frm),/Allocate a container/);
 const departure=fixture(train);Object.assign(departure.frm.doc,{finish_train_formation:1,finish_loading:1,departure_time:'2026-11-13 10:00:00'});
 await assert.rejects(departure.handlers['FPL Perform Middle Mile'].before_save(departure.frm),/Select at least one/);
 assert.equal(loading.calls.length+departure.calls.length,0);
});
test('Freight Change Container prompt uses the exact endpoint and reloads',()=>{
 const f=fixture(freight);f.state.prompt={container_number:'DEMO9999999'};
 f.handlers['FPL Freight Orders'].change_container_number(f.frm);
 assert(f.calls[0].method.endsWith('.change_container_number'));assert.equal(f.calls[0].args.freight_order_id,'UI-ONLY');assert.equal(f.calls[0].args.new_container_number,'DEMO9999999');assert.equal(f.state.reloaded,1);
});
test('Freight after_save reloads the generated job identities',()=>{
 const f=fixture(freight);f.frm.doc.jobs=[{job_id:null}];f.handlers['FPL Freight Orders'].after_save(f.frm);
 assert(f.calls[0].method.endsWith('.create_Job_withoutId'));assert.equal(f.state.reloaded,1);
});
test('Freight after_save does not regenerate existing jobs',()=>{
 const f=fixture(freight);f.frm.doc.jobs=[{job_id:'J1'}];f.handlers['FPL Freight Orders'].after_save(f.frm);assert.equal(f.calls.length,0);
});
test('Extra-charge button requires submitted Cargo base, role and create permission',()=>{
 for(const mutation of [d=>d.docstatus=0,d=>d.custom_booking_order=null,d=>d.is_return=1,d=>d.is_debit_note=1,'role','permission']){
  const f=fixture('public/js/sales_invoice.js');Object.assign(f.frm.doc,{docstatus:1,custom_booking_order:'BO-UI'});
  if(mutation==='role')f.frappe.user_roles=['Employee'];else if(mutation==='permission')f.state.canCreate=false;else mutation(f.frm.doc);
  f.handlers['Sales Invoice'].refresh(f.frm);assert.equal(f.buttons['Invoice for Extra Charges'],undefined);
 }
});
test('Extra-charge click preserves Company, Booking and typed expense references',async()=>{
 const f=fixture('public/js/sales_invoice.js');Object.assign(f.frm.doc,{docstatus:1,custom_booking_order:'BO-UI'});
 f.state.scope={company:'COMPANY-UI',customer:'CUSTOMER-UI',currency:'PKR',conversion_rate:1,custom_booking_order:'BO-UI',sales_order:'SO-UI',
  expenses:[{item_code:'ITEM-UI',item_name:'Expense Item',uom:'Nos',qty:1,rate:35,amount:35,income_account:'INCOME-UI',sales_order:'SO-UI',custom_cargo_expense_parenttype:'FPLRoadJob',custom_cargo_expense_parent:'JOB-UI',custom_cargo_expense_row:'ROW-UI'}]};
 f.handlers['Sales Invoice'].refresh(f.frm);await f.buttons['Invoice for Extra Charges']();const doc=f.state.inserted[0];
 assert.equal(doc.company,'COMPANY-UI');assert.equal(doc.custom_booking_order,'BO-UI');assert.equal(doc.return_against,'UI-ONLY');assert.equal(doc.is_debit_note,1);assert.equal(doc.items[0].custom_cargo_expense_row,'ROW-UI');assert.equal(f.state.routes[0][2],'UI-ONLY-NEW');
 assert.equal(doc.doctype,'Sales Invoice');assert.equal(doc.docstatus,0);assert.equal(doc.customer,'CUSTOMER-UI');
 assert.equal(doc.items[0].sales_order,'SO-UI');assert.equal(doc.items[0].income_account,'INCOME-UI');
 assert.equal(doc.items[0].item_code,'ITEM-UI');assert.equal(doc.items[0].amount,35);
 assert.equal(f.state.buttonGroups['Invoice for Extra Charges'],'Create');
 assert(f.calls[0].method.endsWith('.api.fetch_expenses_items.fetch_expenses_items'));
 assert.equal(f.calls[0].args.sales_invoice_number,'UI-ONLY');
});
test('Extra-charge empty result creates no invoice',async()=>{
 const f=fixture('public/js/sales_invoice.js');Object.assign(f.frm.doc,{docstatus:1,custom_booking_order:'BO-UI'});f.state.scope={expenses:[]};
 f.handlers['Sales Invoice'].refresh(f.frm);await f.buttons['Invoice for Extra Charges']();assert.equal(f.state.inserted.length,0);assert.equal(f.messages.length,1);
});
test('Cross-Stuff allocation resolves weight by its exact Freight Order, not reused container text',()=>{
 const f=fixture('cargo_management/doctype/perform_cross_stuff/perform_cross_stuff.js');
 const row={name:'ROW',container_number:'ALLOCATION-A',weight:0,fo_bags_qty:0};
 f.locals['Grounded Filled Cdt']={ROW:row};f.frm.doc.grounded_filled_containers=[row];
 f.state.respond=options=>options.args.doctype==='FPL Containers'?[{freight_order_id:'FO-A',container_number:'REUSED0000001'}]:[{weight:20,bag_qty:5}];
 f.handlers['Grounded Filled Cdt'].container_number(f.frm,'Grounded Filled Cdt','ROW');
 assert.equal(f.calls[1].args.filters.name,'FO-A');assert.equal(f.calls[1].args.filters.container_number,undefined);
 assert.equal(row.weight,20);assert.equal(row.fo_bags_qty,5);
});
test('Cross-Stuff missing Freight binding cannot fall back to another allocation',()=>{
 const f=fixture('cargo_management/doctype/perform_cross_stuff/perform_cross_stuff.js');
 const row={name:'ROW',container_number:'ALLOCATION-A'};f.locals['Grounded Filled Cdt']={ROW:row};f.frm.doc.grounded_filled_containers=[row];
 f.state.reply=[{freight_order_id:null,container_number:'REUSED0000001'}];
 f.handlers['Grounded Filled Cdt'].container_number(f.frm,'Grounded Filled Cdt','ROW');assert.equal(f.calls.length,1);assert.equal(f.messages.length,1);
});
for(const file of [train,'cargo_management/doctype/fplroadjob/fplroadjob.js',
 'cargo_management/doctype/fplyardjob/fplyardjob.js','cargo_management/doctype/perform_cross_stuff/perform_cross_stuff.js']){
 test(file+' retains invoice-linked expense rows without any deletion RPC',()=>{
  const f=fixture(file);f.locals['Expenses cdt']={ROW:{}};
  f.handlers['Expenses cdt'].before_expenses_remove(f.frm,'Expenses cdt','ROW');
  for(const field of ['purchase_invoice_no','sales_invoice_no']){
   f.locals['Expenses cdt'].ROW={[field]:'UI-ONLY-INVOICE'};
   assert.throws(()=>f.handlers['Expenses cdt'].before_expenses_remove(f.frm,'Expenses cdt','ROW'),/must be retained/);
  }
  assert.equal(f.calls.length,0);
 });
 test(file+' preserves the expense-row move save event with intercepted persistence',()=>{
  const f=fixture(file);let saves=0;f.frm.save=()=>{saves++;};f.locals['Expenses cdt']={ROW:{}};
  f.handlers['Expenses cdt'].expenses_move(f.frm,'Expenses cdt','ROW');assert.equal(saves,1);assert.equal(f.calls.length,0);
 });
}
test('DB script equivalent: Freight container type follows the current size',()=>{
 const f=fixture(freight);f.frm.doc.size=20;f.handlers['FPL Freight Orders'].setup(f.frm);
 const query=f.frm.fields_dict.container_type.get_query;assert.equal(query().filters.size,20);
 f.frm.doc.size=40;assert.equal(query().filters.size,40);
});
test('DB script equivalent: train departure and arrival use the real Yard classifier',()=>{
 const f=fixture(train);f.handlers['FPL Perform Middle Mile'].setup(f.frm);
 for(const field of ['departure_location','arrival_location']){
  const filters=f.frm.fields_dict[field].get_query().filters;
  assert.equal(filters.custom_location_type,'Yard');assert.equal(filters.custom_disabled,0);
  assert.equal(filters.location_type,undefined);
 }
});
test('DB script equivalent: Booking setup registers Booking Order and both Yard links',()=>{
 const f=fixture('cargo_management/doctype/booking_order/booking_order.js');
 assert.equal(f.handlers['FPL Sales Order'],undefined);f.handlers['Booking Order'].setup(f.frm);
 for(const field of ['mm_loading_station','mm_offloading_station']){
  const filters=f.frm.fields_dict[field].get_query().filters;
  assert.equal(filters.custom_location_type,'Yard');assert.equal(filters.custom_disabled,0);
 }
});
test('DB script equivalent: Sequence mode filter preserves shared fallback and Company isolation',async()=>{
 const f=fixture('cargo_management/doctype/fpl_jobs_sequence/fpl_jobs_sequence.js');
 f.frm.doc.transport_mode='Road (Truck)';f.handlers['FPL Jobs Sequence'].setup(f.frm);
 const query=f.frm.fields_dict.service_name.get_query;
 assert.equal(query().filters.transport_mode,'Road (Truck)');assert.deepEqual(Array.from(query().filters.company),['is','not set']);
 f.frm.doc.company='COMPANY-UI';f.frappe.db.count=async()=>2;await f.handlers['FPL Jobs Sequence'].refresh(f.frm);
 assert.equal(query().filters.company,'COMPANY-UI');f.frm.doc.transport_mode='Rail (Train)';assert.equal(query().filters.transport_mode,'Rail (Train)');
 f.frappe.db.count=async()=>0;await f.handlers['FPL Jobs Sequence'].company(f.frm);assert.deepEqual(Array.from(query().filters.company),['is','not set']);
});
