function _weekMonday(d) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const m = new Date(d); m.setDate(d.getDate() + diff); return m;
}
function _weekSunday(d) {
  const m = _weekMonday(d); const s = new Date(m); s.setDate(m.getDate() + 6); return s;
}
function _fmt(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}
function _setDates(start, end, view) {
  document.getElementById('start').value = _fmt(start);
  document.getElementById('end').value   = _fmt(end);
  const viewEl = document.getElementById('filter-view');
  if (viewEl && view) viewEl.value = view;
  // Auto-submit if there's a GET form (Utilization page) or trigger HTMX form
  const getForm = document.querySelector('form[method="get"]');
  const htmxForm = document.querySelector('form[hx-get]');
  if (getForm) (getForm.requestSubmit ? getForm.requestSubmit() : getForm.submit());
  else if (htmxForm) htmx.trigger(htmxForm, 'submit');
}
function setWeek() {
  const now = new Date();
  const mon = new Date(now); mon.setDate(now.getDate() - now.getDay() + 1);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  _setDates(mon, sun, 'week');
}
function setMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  _setDates(first, now, 'month');
}
function setYear() {
  const now = new Date();
  const first = new Date(now.getFullYear(), 0, 1);
  _setDates(first, now, 'month');
}
function setLastMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0);
  _setDates(first, last, 'month');
}
function setLast3Months() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 3, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0); // last day of prev month
  _setDates(first, last, 'month');
}
function setLast6Months() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 6, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0); // last day of prev month
  _setDates(first, last, 'month');
}
// Block all clicks during HTMX requests (except project lazy-load on submit page)
const overlay = document.getElementById('htmx-overlay');
if (overlay) {
  document.body.addEventListener('htmx:beforeRequest', (e) => {
    if (e.detail.elt.id === 'parse-form') return;
    if (e.detail.requestConfig.verb !== 'get' ||
        !e.detail.elt.id.includes('project-select')) {
      overlay.classList.add('active');
    }
  });
  document.body.addEventListener('htmx:afterRequest', () => {
    overlay.classList.remove('active');
  });
  document.body.addEventListener('htmx:responseError', () => {
    overlay.classList.remove('active');
  });
}

function toggleUserField(val) {
  document.getElementById('user-field').style.display = val === 'Single' ? '' : 'none';
}
