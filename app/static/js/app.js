function _weekMonday(d) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const m = new Date(d); m.setDate(d.getDate() + diff); return m;
}
function _weekSunday(d) {
  const m = _weekMonday(d); const s = new Date(m); s.setDate(m.getDate() + 6); return s;
}
function _setDates(start, end) {
  document.getElementById('start').value = start.toISOString().slice(0,10);
  document.getElementById('end').value   = end.toISOString().slice(0,10);
  // Auto-submit if there's a GET form (Utilization page) or trigger HTMX form
  const getForm = document.querySelector('form[method="get"]');
  const htmxForm = document.querySelector('form[hx-get]');
  if (getForm) getForm.submit();
  else if (htmxForm) htmx.trigger(htmxForm, 'submit');
}
function setWeek() {
  const now = new Date();
  const mon = new Date(now); mon.setDate(now.getDate() - now.getDay() + 1);
  const fri = new Date(mon); fri.setDate(mon.getDate() + 4);
  _setDates(mon, fri);
}
function setMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  _setDates(first, now);
}
function setYear() {
  const now = new Date();
  const first = new Date(now.getFullYear(), 0, 1);
  _setDates(first, now);
}
function setLastMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0);
  _setDates(first, last);
}
function setLast3Months() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 3, 1);
  _setDates(first, now);
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
