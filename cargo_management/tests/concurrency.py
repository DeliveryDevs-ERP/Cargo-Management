"""Four independent disposable sessions: job identity and expense reservation races."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import frappe

from cargo_management.tests.isolated_fixtures import directory,require_disposable
ROOT=None
FINANCIAL={'Sales Invoice','Purchase Invoice','Payment Entry','Journal Entry'}

@contextlib.contextmanager
def guards(owned):
    from frappe.model.document import Document
    original_insert,original_save,original_submit=Document.db_insert,Document.save,Document.submit
    def insert(doc,*a,**k):
        out=original_insert(doc,*a,**k);owned.add((doc.doctype,doc.name));return out
    def save(doc,*a,**k):
        if not doc.is_new() and (doc.doctype,doc.name) not in owned:
            raise AssertionError('Concurrency cannot save a retained document: '+doc.doctype+' '+doc.name)
        return original_save(doc,*a,**k)
    def submit(doc,*a,**k):
        if doc.doctype in FINANCIAL:raise AssertionError('Synthetic concurrency forbids accounting posting')
        return original_submit(doc,*a,**k)
    def deny(*a,**k):raise AssertionError('Financial cancellation/external request is prohibited')
    with contextlib.ExitStack() as stack:
        for target,name,value in [(Document,'db_insert',insert),(Document,'save',save),(Document,'submit',submit),
                (Document,'cancel',deny),(frappe,'sendmail',lambda *a,**k:None),(frappe,'enqueue',lambda *a,**k:None)]:
            stack.enter_context(patch.object(target,name,value))
        stack.enter_context(patch('requests.sessions.Session.request',side_effect=deny))
        yield

def wait(path):
    deadline=time.monotonic()+45
    while not path.exists():
        if time.monotonic()>deadline:raise RuntimeError('Concurrency rendezvous timed out')
        time.sleep(.03)

def worker(kind,label):
    global ROOT
    require_disposable()
    ROOT=directory()/'concurrency'
    settings=json.loads((ROOT/'concurrency-fixtures.private.json').read_text())
    owned={(r['doctype'],r['name']) for r in settings['owned_records']}
    initial=set(owned);case=ROOT/'concurrency-active'/kind
    try:
        with guards(owned):
            if kind=='jobs':doc=frappe.get_doc('FPL Freight Orders',settings['freight'])
            else:
                from cargo_management.cargo_management.api.expense_billing import fetch_expenses_items
                base=frappe.get_doc('Sales Invoice',settings['invoice']);response=fetch_expenses_items(base.name)
                doc=frappe.copy_doc(base);doc.is_debit_note=1;doc.return_against=base.name
                doc.set('items',[r for r in response['expenses'] if r['custom_cargo_expense_row']==settings['expense']])
                assert len(doc.items)==1,'Owned concurrent source expense unavailable'
            (case/(label+'-ready')).write_text('ready');wait(case/'start')
            if kind=='jobs':doc.process_jobs()
            else:doc.insert()
            frappe.db.commit()
            result=dict(status='committed',name=doc.name)
    except frappe.ValidationError as error:
        frappe.db.rollback();result=dict(status='rejected',error_type=type(error).__name__,reason=str(error))
    except BaseException as error:
        frappe.db.rollback();result=dict(status='error',error_type=type(error).__name__,reason=str(error))
    result.update(worker=label,created=[dict(doctype=dt,name=n) for dt,n in sorted(owned-initial)])
    (case/(label+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
    if result['status']=='error':raise RuntimeError('Concurrency worker failed; inspect private result')

def run():
    global ROOT
    require_disposable()
    ROOT=directory()/'concurrency'
    ROOT.mkdir(mode=0o700,exist_ok=False)
    from cargo_management.tests.isolated_fixtures import Fixtures,make_booking
    from cargo_management.cargo_management.utils.configuration import resolve_service
    f=Fixtures();owned=set()
    try:
        with guards(owned):
            booking=make_booking(f,'Concurrency-'+require_disposable(),selected_labels=['Long Haul'])
            freight=frappe.get_doc('FPL Freight Orders',{'sales_order_number':booking.name})
            freight.append('jobs',dict(job_name=resolve_service('Short Haul','Road (Truck)',booking.company),
                status='Draft',start_location=f.get('location-1').name,end_location=f.get('location-2').name))
            freight.save()
            invoice=frappe.get_doc('Sales Invoice',booking.create_and_submit_sales_invoice())
            job=frappe.get_doc('FPLRoadJob',freight.jobs[0].job_id);expense=job.expenses[0]
            expense.invoiced_=1;job.save()
            settings=dict(booking=booking.name,freight=freight.name,invoice=invoice.name,expense=expense.name,
                owned_records=[dict(doctype=dt,name=n) for dt,n in sorted(owned)])
            (ROOT/'concurrency-fixtures.private.json').write_text(json.dumps(settings,indent=2)+'\n')
            frappe.db.commit()
        active=ROOT/'concurrency-active';active.mkdir(mode=0o700)
        cases=[]
        for kind in ('jobs','expense'):
            case=active/kind;case.mkdir(mode=0o700);processes=[]
            try:
                for label in ('one','two'):
                    with (case/(label+'.log')).open('w') as log:
                        processes.append(subprocess.Popen([sys.executable,'-B',__file__,'worker',kind,label],stdout=log,stderr=log,cwd=str(Path(frappe.local.sites_path).resolve())))
                deadline=time.monotonic()+45
                while not all((case/(label+'-ready')).exists() for label in ('one','two')):
                    if time.monotonic()>deadline or any(p.poll() is not None for p in processes):raise RuntimeError('Concurrency worker did not reach rendezvous')
                    time.sleep(.03)
                (case/'start').write_text('start')
                for p in processes:assert p.wait(timeout=60)==0,'Concurrency worker exited with failure'
                results=[json.loads((case/(label+'-result.json')).read_text()) for label in ('one','two')]
                frappe.db.rollback()
                if kind=='jobs':
                    assert all(r['status']=='committed' for r in results),results
                    actual=frappe.get_doc('FPL Freight Orders',freight.name)
                    assert all(r.job_id for r in actual.jobs)
                    assert len(actual.jobs)==2
                    assert frappe.db.count('FPLRoadJob',{'freight_order_id':freight.name})==2
                else:
                    assert sorted(r['status'] for r in results)==['committed','rejected'],results
                    assert 'reserved' in next(r['reason'] for r in results if r['status']=='rejected')
                    winner=next(r['name'] for r in results if r['status']=='committed')
                    assert frappe.db.get_value('Sales Invoice',winner,'docstatus')==0
                cases.append(dict(case=kind,passed=True,workers=results))
            finally:
                for p in processes:
                    if p.poll() is None:p.terminate();p.wait(timeout=10)
        summary=dict(passed=True,independent_db_sessions=4,cases=cases,financial_posting=False,new_owned_fixtures_retained=True)
        (ROOT/'concurrency-results.private.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
    finally:frappe.db.rollback()

if __name__=='__main__':
    frappe.init(os.environ['CARGO_TEST_SITE']);frappe.connect();require_disposable()
    try:
        if sys.argv[1:] and sys.argv[1]=='worker':worker(*sys.argv[2:])
        else:run()
    finally:frappe.db.rollback();frappe.destroy()
