import {element, pretty} from './client.js';

const labels = {READY:'通过', MISMATCH:'差异待复核', PENDING:'待复核', APPROVED:'已签发', HELD:'已暂缓'};
const headers = ['业务分组', '输入行', '计算值', '参考值', '判定'];
const outcomes = {SUCCESSOR:'影响 · 已生成后继批次', NO_IMPACT:'无影响 · 保持原签发批次'};
const reasons = {
  NOTE_ONLY:'仅备注变化',
  ISOLATED_ONLY:'仅隔离行变化',
  NO_CONCLUSION_CHANGE:'读数变化未改变结论',
  NO_EFFECTIVE_CHANGE:'无有效变化',
};
const changes = {PEAK:'峰值', STATUS:'判定', GROUP_ADDED:'新增分组', GROUP_REMOVED:'移除分组', PEAK_WINDOW:'峰值窗口'};

export function badge(status) {
  return element('span', labels[status] || status, {class:'badge', 'data-result':status, title: status});
}

export function snapshot(report, selected, stage) {
  const stats = report.intake;
  document.querySelector('[data-metric="input"]').textContent = stats.input;
  document.querySelector('[data-metric="accepted"]').textContent = stats.accepted;
  document.querySelector('[data-metric="isolated"]').textContent = stats.rejected;
  document.querySelector('[data-metric="cases"]').textContent = report.cases?.length ?? '—';
  const table = document.querySelector('#rows');
  table.replaceChildren();
  const head = element('tr');
  const body = table.createTBody();
  if (stage === 'intake') {
    head.append(...['源行', '记录键', '业务分组', '原因码'].map(title => element('th', title, {scope:'col'})));
    for (const item of stats.isolation) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    if (!stats.isolation.length) body.insertRow().insertCell().textContent = '当前文件没有隔离行';
  } else {
    head.append(...headers.map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      [row.records.length, row.measure?.value ?? '—', row.measure?.expected ?? '—'].forEach(value=>tr.insertCell().textContent=value);
      tr.insertCell().append(badge(row.status));
    }
  }
  table.createTHead().append(head);
  const picked = report.cases?.find(row=>row.case===selected);
  document.querySelector('#detail-title').textContent = picked ? `分组 ${picked.case}` : '采信摘要';
  const shown = picked ? picked.measure?.evidence ?? picked.prep?.details ?? {原因:picked.status} : stats.reasons;
  document.querySelector('#detail').textContent = pretty(shown);
  document.querySelector('#counts').textContent = report.balance ? `行数 ${report.balance.accounted}/${report.balance.input} · ${report.balance.ready} 组通过` : `采信 ${stats.accepted} 行 · 隔离 ${stats.rejected} 行`;
}

export function history(items, active) {
  const target = document.querySelector('#history');
  target.replaceChildren();
  for (const run of items) {
    const button = element('button', run.id.slice(0,10), {'data-run':run.id,'aria-pressed':String(run.id===active),type:'button'});
    if (run.kind === 'REVISION') button.title = `后继于 ${String(run.base_id).slice(0,10)}`;
    const item = element('li');
    item.append(button, badge(run.status));
    if (run.kind === 'REVISION') item.append(element('span', '修订后继', {class:'badge'}));
    target.append(item);
  }
  if (!items.length) target.append(element('li','尚无执行批次'));
}

export function revisions(items, base) {
  const target = document.querySelector('#revision-results');
  target.replaceChildren();
  for (const item of items) {
    const impact = item.detail;
    const entry = element('li', undefined, {class:'revision-item', 'data-outcome':item.outcome});
    entry.append(element('strong', outcomes[item.outcome] || item.outcome));
    entry.append(element('span', reasons[impact.reason] || impact.reason || ''));
    const changed = impact.changed_records || [];
    if (changed.length) {
      entry.append(element('span', `改动 ${changed.length} 条`, {class:'badge'}));
    }
    const moved = (impact.cases || []).filter(item=>item.changes.length);
    for (const group of moved) {
      const text = `${group.case}: ${group.changes.map(key=>changes[key]||key).join('、')}`;
      entry.append(element('span', text, {class:'badge'}));
    }
    if (item.successor_id) {
      entry.append(element('span', `后继 ${item.successor_id.slice(0,10)}`, {class:'badge'}));
    }
    target.append(entry);
  }
  const section = document.querySelector('#revisions');
  section.hidden = !(base && base.status === 'APPROVED');
  if (section.hidden) target.replaceChildren();
}
