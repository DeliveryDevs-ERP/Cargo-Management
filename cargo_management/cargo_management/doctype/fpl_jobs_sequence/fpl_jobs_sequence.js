frappe.ui.form.on('FPL Jobs Sequence', {
    setup(frm) {
        frm.set_query('service_name', () => ({filters: {
            transport_mode: frm.doc.transport_mode,
            company: frm.__cargo_service_company || ['is', 'not set'],
        }}));
    },
    async refresh(frm) { await cargo_sequence_company(frm); },
    async company(frm) { await cargo_sequence_company(frm); },
    async transport_mode(frm) { await cargo_sequence_company(frm); },
});
async function cargo_sequence_company(frm) {
    const company = frm.doc.company;
    const count = company ? await frappe.db.count('Service Type', {company}) : 0;
    if (company === frm.doc.company) frm.__cargo_service_company = count ? company : null;
}
