function setWeek() {
  const now = new Date();
  const mon = new Date(now); mon.setDate(now.getDate() - now.getDay() + 1);
  const fri = new Date(mon); fri.setDate(mon.getDate() + 4);
  document.getElementById('start').value = mon.toISOString().slice(0,10);
  document.getElementById('end').value   = fri.toISOString().slice(0,10);
}
function setMonth() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last  = new Date(now.getFullYear(), now.getMonth()+1, 0);
  document.getElementById('start').value = first.toISOString().slice(0,10);
  document.getElementById('end').value   = last.toISOString().slice(0,10);
}
function setYear() {
  const y = new Date().getFullYear();
  document.getElementById('start').value = `${y}-01-01`;
  document.getElementById('end').value   = `${y}-12-31`;
}
function toggleUserField(val) {
  document.getElementById('user-field').style.display = val === 'Single' ? '' : 'none';
}
