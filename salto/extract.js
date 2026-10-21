// Generic Pega page extractor. arguments[0] = root element (null = whole document).
// Returns {sections: [{name, fields: [[label, value]]}], grids: [{name, headers, rows}], subtabs, text}
const root = arguments[0] || document.body;
const vis = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
const clean = s => (s || '').replace(/\s+/g, ' ').trim();
const headerText = s => clean(s).replace(/(Enter|Click) to (sort|filter)/g, '').replace(/This column is sorted in (ascending|descending) order\.?\s*\.?/g, '').trim();
const EMPTY = /^(No items|No cases|No posts found|No records|No data)$/i;

// Section name = title of the nearest enclosing Pega layout that has a header
function sectionOf(el) {
  for (let x = el.parentElement; x && x !== root.parentElement; x = x.parentElement) {
    if (x.classList && x.classList.contains('layout')) {
      // header styles: div.header, fieldset > legend, accordion header-content
      const h = [...x.querySelectorAll('.header-title')].find(t => t.closest('.layout') === x && clean(t.textContent));
      if (h) return clean(h.textContent);
    }
  }
  return 'General';
}

// ---- label/value fields
const sections = [];
const byName = {};
const taken = [];  // value elements already read with a label
const valueOf = el => {
  const input = el.querySelector('input:not([type=hidden]),select,textarea');
  if (input && input.tagName === 'SELECT') return clean(input.options[input.selectedIndex] && input.options[input.selectedIndex].text);
  if (input && input.type === 'checkbox') return input.checked ? 'Yes' : 'No';
  if (input) return clean(input.value);
  return clean(el.innerText || el.textContent);
};
root.querySelectorAll('.field-caption, .dataLabelForRead').forEach(cap => {
  if (!vis(cap) || cap.closest('table.gridTable')) return;
  const label = clean(cap.textContent);
  if (!label) return;
  let val = cap.nextElementSibling;
  if (!val) return;
  const input = val.querySelector('input:not([type=hidden]),select,textarea');
  let v;
  if (input && input.tagName === 'SELECT') v = clean(input.options[input.selectedIndex] && input.options[input.selectedIndex].text);
  else if (input && input.type === 'checkbox') v = input.checked ? 'Yes' : 'No';
  else if (input) v = clean(input.value);
  else v = clean(val.textContent);
  const sec = sectionOf(cap);
  if (!byName[sec]) { byName[sec] = {name: sec, fields: []}; sections.push(byName[sec]); }
  byName[sec].fields.push([label, v]);
  taken.push(val, cap.parentElement);
});

// ---- values without a label of their own (e.g. "Provisioning Notes" text under its heading):
// kept under the heading's name
root.querySelectorAll('.content-field.dataValueRead, .content-field.dataValueWrite').forEach(f => {
  if (!vis(f) || f.closest('table.gridTable') || f.querySelector('.field-caption, .dataLabelForRead, table.gridTable')) return;
  if (taken.some(t => t && (t.contains(f) || f.contains(t)))) return;
  if (f.querySelector('a, button') && !f.querySelector('textarea, input, select') && clean(f.innerText).length < 40) return;  // a link/button
  const v = valueOf(f);
  if (!v || EMPTY.test(v)) return;
  const sec = sectionOf(f);
  if (!byName[sec]) { byName[sec] = {name: sec, fields: []}; sections.push(byName[sec]); }
  if (byName[sec].fields.some(x => x[1] === v)) return;
  byName[sec].fields.push([sec === 'General' ? 'Note' : sec, v]);
  taken.push(f);
});

// ---- grids (Pega gridTable); header names from data-attribute-name or the <th> row
const grids = [];
const seen = new Set();
root.querySelectorAll('table.gridTable').forEach(tbl => {
  if (!vis(tbl)) return;
  const trs = [...tbl.querySelectorAll(':scope > tbody > tr, :scope > tr')];
  const hr = trs.find(tr => tr.querySelector(':scope > th'));
  const ths = hr ? [...hr.querySelectorAll(':scope > th')].map(th => headerText(th.textContent)) : [];
  const bodyRows = trs.filter(tr => tr !== hr && tr.querySelector(':scope > td') && /cellCont|Row/.test(tr.className));
  if (!bodyRows.length) return;
  const headers = [];
  const rows = bodyRows.map(tr => {
    const o = {};
    [...tr.querySelectorAll(':scope > td')].forEach((td, i) => {
      const h = td.getAttribute('data-attribute-name') || ths[i] || '';
      if (!h) return;
      if (!headers.includes(h)) headers.push(h);
      o[h] = clean(td.textContent);
    });
    return o;
  }).filter(o => { const v = Object.values(o).filter(Boolean); return v.length && !(v.length === 1 && EMPTY.test(v[0])); });
  if (!rows.length) return;
  const key = JSON.stringify(rows);
  if (seen.has(key)) return;
  seen.add(key);
  grids.push({name: sectionOf(tbl), headers, rows});
});

const subtabs = [...root.querySelectorAll('[role=tab]')].filter(vis).map(t => clean(t.textContent)).filter(Boolean);
return {sections, grids, subtabs, text: (root.innerText || '').slice(0, 30000)};
