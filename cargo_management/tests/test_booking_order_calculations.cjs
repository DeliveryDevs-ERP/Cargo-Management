// Run with node --test inside the existing Docker container. No database,
// network, saved documents, or browser authentication are used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const repo = path.resolve(__dirname, '../..');
const frappeRoot = process.env.CARGO_TEST_FRAPPE_PATH || path.resolve(repo, '../frappe');
const relativeScript = 'cargo_management/cargo_management/doctype/booking_order/booking_order.js';
const sources = {
  model: fs.readFileSync(path.join(frappeRoot, 'frappe/public/js/frappe/model/model.js'), 'utf8'),
  manager: fs.readFileSync(path.join(frappeRoot, 'frappe/public/js/frappe/form/script_manager.js'), 'utf8'),
  app: fs.readFileSync(path.join(repo, relativeScript), 'utf8'),
};

function harness(initialRows = [{}], options = {}) {
  const pending = [], calls = [], lookups = [], messages = [], errors = [];
  const context = { locals: {}, cur_frm: null, flt: value => Number(value) || 0,
    __: text => text, console: { log() {}, error(...args) { errors.push(args); } } };
  context.window = context;
  context.$ = {
    extend: Object.assign,
    isPlainObject: value => Object.prototype.toString.call(value) === '[object Object]',
    each(collection, callback) {
      for (const key of Object.keys(collection)) if (callback(key, collection[key]) === false) break;
    },
  };
  context.frappe = {
    provide(name) {
      let current = context;
      for (const part of name.split('.')) current = current[part] ||= {};
    },
    // Same serial promise contract used by the pinned Frappe dispatcher.
    run_serially(tasks) { return tasks.reduce((promise, task) => promise.then(task), Promise.resolve()); },
    after_server_call: () => Promise.resolve(),
    db: { get_list(doctype, args) {
      lookups.push({ doctype, args });
      return Promise.resolve().then(() => options.lookup ? options.lookup(doctype, args) :
        [{ size: 20, max_cargo_weight_kg: 30000 }]);
    } },
    msgprint(message) { messages.push(message); },
  };
  vm.createContext(context);
  vm.runInContext(sources.model, context);
  vm.runInContext(sources.manager, context);
  const dt = 'Cargo Detail cdt';
  const rows = initialRows.map((values, index) => ({ doctype: dt, name: 'ROW-' + index,
    parent: 'UNSAVED', parenttype: 'Booking Order', parentfield: 'cargo_details',
    rate_type: '', rate: 0, qty: 0, bag_qty: 0, bag_weight: 0, avg_weight: 0,
    amount: null, size: '20', ...values }));
  const doc = { doctype: 'Booking Order', name: 'UNSAVED', cargo_details: rows };
  context.locals[dt] = Object.fromEntries(rows.map(row => [row.name, row]));
  context.locals['Booking Order'] = { UNSAVED: doc };
  const frm = { doctype: doc.doctype, docname: doc.name, doc, events: {}, cscript: {},
    fields_dict: { customer: { df: {} }, cargo_owner: { df: {} } },
    set_df_property() {},
    set_value(field, value) { return context.frappe.model.set_value(doc.doctype, doc.name, field, value); } };
  context.cur_frm = frm;
  frm.script_manager = new context.frappe.ui.form.ScriptManager({ frm });
  // Equivalent to Form's model-to-ScriptManager event bridge, without grid DOM.
  for (const doctype of [dt, doc.doctype]) {
    context.frappe.model.on(doctype, '*', (field, value, changed) =>
      frm.script_manager.trigger(field, changed.doctype, changed.name));
  }
  const setValue = context.frappe.model.set_value;
  context.frappe.model.set_value = function (...args) {
    calls.push({ doctype: args[0], name: args[1], field: args[2], value: args[3] });
    const promise = setValue.apply(this, args);
    pending.push(promise);
    return promise;
  };
  vm.runInContext(options.source || sources.app, context);
  return { context, frm, doc, rows, calls, lookups, messages, errors,
    change(field, value, row = rows[0]) {
      return context.frappe.model.set_value(dt, row.name, field, value);
    },
    async flush() {
      let count = 0;
      while (pending.length) {
        assert.ok(++count < 100, 'Unexpected event loop');
        await Promise.all(pending.splice(0));
      }
    },
    trigger(event) { return frm.script_manager.trigger(event, doc.doctype, doc.name); },
    addRow(row) {
      const child = { ...rows[0], ...row, name: 'ADDED' };
      doc.cargo_details.push(child); context.locals[dt][child.name] = child;
      return frm.script_manager.trigger('cargo_details_add', dt, child.name);
    },
    removeRow(row) {
      doc.cargo_details.splice(doc.cargo_details.indexOf(row), 1);
      delete context.locals[dt][row.name];
      return frm.script_manager.trigger('cargo_details_remove', dt, row.name);
    },
  };
}

function permutations(items) {
  if (!items.length) return [[]];
  return items.flatMap((item, index) => permutations(items.filter((_, i) => i !== index))
    .map(rest => [item, ...rest]));
}

for (const [rateType, inputs, expected] of [
  ['Acre (US)', [['rate', 12.5], ['qty', 2]], 25],
  ['Nos', [['rate', 12.5], ['qty', 2]], 25],
  ['Per Container', [['rate', 12.5], ['qty', 2]], 25],
  ['Per Bag', [['rate', 12.5], ['bag_qty', 4]], 50],
  ['Per Weight(Ton)', [['rate', 12.5], ['qty', 2], ['avg_weight', 3]], 75],
]) {
  test(`${rateType}: every input order calculates Amount and Total`, async () => {
    for (const sequence of permutations([['rate_type', rateType], ...inputs])) {
      const h = harness();
      for (const [field, value] of sequence) await h.change(field, value);
      await h.flush();
      assert.equal(h.rows[0].amount, expected, JSON.stringify(sequence));
      assert.equal(h.doc.total, expected, JSON.stringify(sequence));
    }
  });
}

test('rate-type changes select the existing formula', async () => {
  const h = harness([{ rate: 12.5, qty: 2, bag_qty: 4, avg_weight: 3 }]);
  for (const [type, amount] of [['Acre (US)', 25], ['Per Bag', 50], ['Per Weight(Ton)', 75], ['Per Container', 25]]) {
    await h.change('rate_type', type);
    assert.equal(h.rows[0].amount, amount);
    assert.equal(h.doc.total, amount);
  }
});

test('rapid Rate and Qty changes settle to the latest values', async () => {
  const h = harness([{ rate_type: 'Acre (US)' }]);
  await Promise.all([h.change('rate', 12.5), h.change('qty', 2)]);
  await h.flush();
  assert.equal(h.rows[0].amount, 25);
  assert.equal(h.doc.total, 25);
});

test('all supported formulas retain explicit expected results including zero rates', async () => {
  for (const type of ['Acre (US)', 'Nos', 'Per Container', 'Per Bag', 'Per Weight(Ton)']) {
    for (const rate of [0, 12.5, -3]) {
      const row = { rate_type: type, rate, qty: 2, bag_qty: 7, avg_weight: 3 };
      const h = harness([row]);
      h.context.calculate_amount(h.frm, 'Cargo Detail cdt', h.rows[0].name);
      await h.flush();
      const billable = type === 'Per Bag' ? 7 : type === 'Per Weight(Ton)' ? 6 : 2;
      assert.equal(h.rows[0].amount, billable * rate, `${type} / ${rate}`);
      assert.equal(h.rows[0].rate, rate);
      assert.equal(h.rows[0].qty, 2);
    }
  }
});

test('manual Amount changes sum correctly across multiple rows, including zero', async () => {
  const h = harness([{ amount: 25 }, { amount: 50 }, { amount: 75 }]);
  await h.change('amount', 99, h.rows[1]);
  assert.equal(h.doc.total, 199);
  await h.change('amount', 0, h.rows[1]);
  assert.equal(h.doc.total, 100);
  await h.change('amount', -10, h.rows[0]);
  assert.equal(h.doc.total, 65);
});

test('row addition and removal update Total without recalculating manual Amounts', async () => {
  const h = harness([{ amount: 41, rate: 2, qty: 1 }, { amount: 9 }]);
  await h.addRow({ amount: 7 });
  assert.equal(h.doc.total, 57);
  await h.removeRow(h.rows[1]);
  assert.equal(h.doc.total, 48);
  assert.equal(h.rows[0].amount, 41);
  assert.equal(h.calls.filter(call => call.field === 'amount').length, 0);
});

test('unrelated fields preserve manual Amount for every formula branch', async () => {
  for (const [type, fields] of [
    ['Acre (US)', ['bag_qty', 'avg_weight', 'bag_weight', 'size', 'cargo_type']],
    ['Per Container', ['bag_qty', 'avg_weight', 'bag_weight', 'size', 'cargo_type']],
    ['Per Bag', ['qty', 'avg_weight', 'bag_weight', 'size', 'cargo_type']],
    ['Per Weight(Ton)', ['bag_qty', 'bag_weight', 'size', 'cargo_type']],
  ]) {
    const h = harness([{ rate_type: type, rate: 12.5, qty: 2, amount: 91 }]);
    for (const field of fields) await h.change(field, ['size', 'cargo_type'].includes(field) ? 'changed' : 3);
    await h.flush();
    assert.equal(h.rows[0].amount, 91, type);
    assert.equal(h.calls.filter(call => call.field === 'amount').length, 0, type);
  }
});

test('refresh/save events preserve manual Amount; Amount remains editable metadata', async () => {
  const h = harness([{ rate_type: 'Acre (US)', rate: 12.5, qty: 2, amount: 91 }]);
  await h.trigger('refresh'); await h.trigger('validate'); await h.trigger('before_save'); await h.flush();
  assert.equal(h.rows[0].amount, 91);
  assert.equal(h.doc.total, 91);
  assert.equal(h.calls.filter(call => call.field === 'amount').length, 0);
  const metadata = JSON.parse(fs.readFileSync(path.join(repo,
    'cargo_management/cargo_management/doctype/cargo_detail_cdt/cargo_detail_cdt.json'), 'utf8'));
  assert.ok(!metadata.fields.find(field => field.fieldname === 'amount').read_only);
});

test('manual Amount is recalculated when an applicable input changes', async () => {
  const h = harness([{ rate_type: 'Acre (US)', rate: 12.5, qty: 2, amount: 91 }]);
  await h.change('qty', 3);
  assert.equal(h.rows[0].amount, 37.5); assert.equal(h.doc.total, 37.5);
  await h.change('rate', 0);
  assert.equal(h.rows[0].amount, 0); assert.equal(h.doc.total, 0);
});

test('weight validation still looks up matching size and selects the largest capacity', async () => {
  const h = harness([{ rate_type: 'Per Weight(Ton)', rate: 12.5, qty: 2 }],
    { lookup: () => [{ max_cargo_weight_kg: 2 }, { max_cargo_weight_kg: 5 }] });
  await h.change('avg_weight', 3);
  assert.equal(h.rows[0].avg_weight, 3); assert.equal(h.rows[0].amount, 75);
  assert.equal(h.lookups[0].doctype, 'Container Type');
  assert.equal(h.lookups[0].args.filters.size, '20');
  assert.equal(h.messages.length, 0);
});

test('excessive weight resets to zero and weighted Amount/Total follow the reset', async () => {
  const h = harness([{ rate_type: 'Per Weight(Ton)', rate: 12.5, qty: 2 }],
    { lookup: () => [{ max_cargo_weight_kg: 5 }] });
  await h.change('avg_weight', 10); await h.flush();
  assert.equal(h.rows[0].avg_weight, 0); assert.equal(h.rows[0].amount, 0); assert.equal(h.doc.total, 0);
  assert.equal(h.messages.length, 1); assert.match(h.messages[0], /exceeds the maximum limit/);
});

test('missing container and missing size warnings remain intact', async () => {
  const h = harness([{ rate_type: 'Per Weight(Ton)', rate: 12.5, qty: 2 }], { lookup: () => [] });
  await h.change('avg_weight', 2);
  assert.match(h.messages[0], /No container found with the specified size/);
  assert.equal(h.rows[0].amount, 50);
  const missing = harness([{ rate_type: 'Acre (US)', size: '', amount: 91 }]);
  await missing.change('avg_weight', 2);
  assert.match(missing.messages[0], /Please enter the size/);
  assert.equal(missing.rows[0].amount, 91);
});

test('weight lookup failures retain the original warning behavior', async () => {
  const h = harness([{ rate_type: 'Per Weight(Ton)', rate: 12.5, qty: 2 }],
    { lookup: () => Promise.reject(new Error('test lookup failure')) });
  await h.change('avg_weight', 2);
  assert.match(h.messages[0], /Failed to validate weight/);
  assert.equal(h.errors.length, 1); assert.equal(h.rows[0].amount, 50);
});

test('a delayed validator does not overwrite a manual Amount after switching to an ordinary UOM', async () => {
  let resolveLookup;
  const h = harness([{ rate_type: 'Per Weight(Ton)', rate: 12.5, qty: 2 }],
    { lookup: () => new Promise(resolve => { resolveLookup = resolve; }) });
  const pendingValidation = h.change('avg_weight', 3);
  while (!resolveLookup) await Promise.resolve();
  await h.change('rate_type', 'Acre (US)');
  await h.change('amount', 91);
  resolveLookup([{ max_cargo_weight_kg: 30000 }]);
  await pendingValidation; await h.flush();
  assert.equal(h.rows[0].amount, 91); assert.equal(h.doc.total, 91);
});
