// ============================================================
// 城市治理 Copilot 前端 —— 功能大厅 + 多视图
// ============================================================

// ---- GCJ-02 坐标转换（WGS84 -> 高德瓦片坐标） ----
const PI = Math.PI, A = 6378245.0, EE = 0.00669342162296594323;
function outOfChina(lng, lat) { return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271; }
function wgs84ToGcj02(lng, lat) {
  if (outOfChina(lng, lat)) return [lng, lat];
  let dLat = transformLat(lng - 105.0, lat - 35.0);
  let dLng = transformLng(lng - 105.0, lat - 35.0);
  const radLat = lat / 180.0 * PI;
  let magic = Math.sin(radLat);
  magic = 1 - EE * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / ((A * (1 - EE)) / (magic * sqrtMagic) * PI);
  dLng = (dLng * 180.0) / (A / sqrtMagic * Math.cos(radLat) * PI);
  return [lng + dLng, lat + dLat];
}
function transformLat(x, y) {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
  ret += (20.0 * Math.sin(y * PI) + 40.0 * Math.sin(y / 3.0 * PI)) * 2.0 / 3.0;
  ret += (160.0 * Math.sin(y / 12.0 * PI) + 320 * Math.sin(y * PI / 30.0)) * 2.0 / 3.0;
  return ret;
}
function transformLng(x, y) {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  ret += (20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0 / 3.0;
  ret += (20.0 * Math.sin(x * PI) + 40.0 * Math.sin(x / 3.0 * PI)) * 2.0 / 3.0;
  ret += (150.0 * Math.sin(x / 12.0 * PI) + 300.0 * Math.sin(x / 30.0 * PI)) * 2.0 / 3.0;
  return ret;
}

// ---- 工具 ----
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}
function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ---- 会话 ID（多轮记忆）----
const sessionId = localStorage.getItem('ugc_session') || ('s_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8));
localStorage.setItem('ugc_session', sessionId);

// ============================================================
// 功能大厅
// ============================================================
const FEATURES = [
  { icon: '💬', title: '智能对话助手', desc: '留言 → 分析 → 归口 → 回复', view: 'chat', color: '#3a7bd5' },
  { icon: '📊', title: '民情数据看板', desc: '33 万民情统计 · 领域 / 月份 / 省份', view: 'dashboard', color: '#16a34a' },
  { icon: '🗺️', title: '区县地图洞察', desc: '点击地图看区县常见诉求', view: 'map', color: '#d97706' },
  { icon: '⚠️', title: '风险预警', desc: '涉稳涉急留言识别', view: 'risk', color: '#dc2626' },
  { icon: '🔍', title: '相似案例检索', desc: '搜历史案例', view: 'search', color: '#7c3aed' },
  { icon: '⚡', title: '单条快速分析', desc: '一条留言快速归类', view: 'quick', color: '#0ea5e9' },
  { icon: '📤', title: '批量分析', desc: 'CSV 批量归口报告', view: 'batch', color: '#db2777' },
  { icon: '📋', title: '民情月报', desc: '自动生成治理报告', view: 'report', color: '#059669' },
  { icon: '📄', title: '文档分析', desc: '文本 / 报告结构化解读', view: 'doc', color: '#0891b2' },
];

function renderCards() {
  const grid = document.getElementById('cardGrid');
  grid.innerHTML = '';
  FEATURES.forEach(f => {
    const b = el('button', 'card' + (f.todo ? ' card-todo' : ''));
    const badge = f.todo
      ? '<span class="card-badge badge-todo">建设中</span>'
      : '<span class="card-badge badge-live">已上线</span>';
    b.innerHTML = `
      <div class="card-top" style="--card-accent:${f.color}">
        <div class="card-icon">${f.icon}</div>
        <div class="card-arrow">${f.todo ? '🔒' : '→'}</div>
      </div>
      <div class="card-title">${esc(f.title)}</div>
      <div class="card-desc">${esc(f.desc)}</div>
      <div class="card-foot">${badge}</div>`;
    b.addEventListener('click', () => {
      if (f.todo) showTodo(f.title);
      else showView('view-' + f.view);
    });
    grid.appendChild(b);
  });
}

function showView(viewId) {
  document.getElementById('home').hidden = true;
  document.querySelectorAll('.view').forEach(v => v.hidden = true);
  const view = document.getElementById(viewId);
  view.hidden = false;
  if (viewId === 'view-dashboard') loadDashboard();
  else if (viewId === 'view-map') loadBigMap();
  else if (viewId === 'view-risk') loadRisk();
  else if (viewId === 'view-review') loadReview();
  else if (viewId === 'view-chat') loadChatHistory();
}
function backHome() {
  document.querySelectorAll('.view').forEach(v => v.hidden = true);
  document.getElementById('home').hidden = false;
}

// ============================================================
// 民情数据看板
// ============================================================
let dashData = null;
async function loadDashboard() {
  const grid = document.getElementById('dashGrid');
  const stats = document.getElementById('dashStats');
  grid.innerHTML = '<div class="dash-empty">加载中…</div>';
  try {
    if (!dashData) {
      const resp = await fetch('/api/dashboard');
      if (!resp.ok) throw new Error('接口返回 ' + resp.status);
      dashData = await resp.json();
    }
  } catch (e) { grid.innerHTML = '<div class="dash-empty">加载失败：' + esc(e.message) + '</div>'; return; }
  const d = dashData || {};
  const fields = d.fields || [], provinces = d.provinces || [], months = d.months || [];
  const sat = d.satisfaction || {};
  stats.innerHTML = [
    statCard(d.total || 0, '留言总量'),
    statCard(fields.length, '问题领域'),
    statCard(provinces.length, '覆盖省份'),
    statCard(sat['不满意'] || 0, '不满意留言'),
  ].join('');
  grid.innerHTML = barCard('领域分布', fields, 'name', 'count', '--brand') +
    barCard('月份趋势', months, 'month', 'count', '--ok') +
    barCard('省份分布', provinces, 'name', 'count', '--warn') +
    topicCard('高发主题词', d.topics || []) + pieCard('满意度', sat);
}
function statCard(v, label) { return `<div class="stat-card"><div class="stat-num">${esc(v)}</div><div class="stat-label">${esc(label)}</div></div>`; }
function barCard(title, arr, key, val, color) {
  if (!arr) return '';
  const max = Math.max(...arr.map(x => x[val]), 1);
  const items = arr.slice(0, 12).map(x => {
    const pct = Math.round(x[val] / max * 100);
    return `<div class="bar-row"><span class="bar-label">${esc(x[key])}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:var(${color})"></div></div><span class="bar-val">${esc(x[val])}</span></div>`;
  }).join('');
  return `<div class="dash-card"><div class="panel-title">${esc(title)}</div><div class="dash-body">${items}</div></div>`;
}
function topicCard(title, arr) {
  if (!arr) return '';
  const tags = arr.slice(0, 24).map(x => `<span class="tag">${esc(x.word)} <em>${esc(x.count)}</em></span>`).join('');
  return `<div class="dash-card"><div class="panel-title">${esc(title)}</div><div class="dash-body">${tags}</div></div>`;
}
function pieCard(title, sat) {
  const ok = sat['满意'] || 0, bad = sat['不满意'] || 0, tot = ok + bad || 1;
  const okPct = Math.round(ok / tot * 100);
  return `<div class="dash-card"><div class="panel-title">${esc(title)}</div><div class="dash-body">
    <div class="donut" style="background:conic-gradient(var(--ok) 0 ${okPct}%, var(--err) ${okPct}% 100%)"></div>
    <div class="legend"><span style="color:var(--ok)">■ 满意 ${esc(ok)}</span><br/><span style="color:var(--err)">■ 不满意 ${esc(bad)}</span></div>
  </div></div>`;
}

// ============================================================
// 区县地图洞察
// ============================================================
let bigMap = null, bigLayer = null;
function initBigMap() {
  if (bigMap) { setTimeout(() => bigMap.invalidateSize(), 120); return; }
  bigMap = L.map('bigMap', { center: [35, 105], zoom: 5 });
  L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}', { subdomains: ['1','2','3','4'], attribution: '高德地图' }).addTo(bigMap);
  bigLayer = L.layerGroup().addTo(bigMap);
  setTimeout(() => bigMap.invalidateSize(), 250); // 容器可能刚显示，刷新尺寸
}
async function loadBigMap() {
  initBigMap();
  bigLayer.clearLayers();
  const empty = document.getElementById('bigMapEmpty');
  empty.style.display = 'block';
  empty.textContent = '加载民情地点…';
  try {
    if (!dashData) {
      const resp = await fetch('/api/dashboard');
      if (!resp.ok) throw new Error('接口返回 ' + resp.status);
      dashData = await resp.json();
    }
  } catch (e) { empty.textContent = '加载失败：' + e.message; return; }
  const ds = (dashData.districts || []).slice(0, 400);
  empty.style.display = 'none';
  ds.forEach(d => {
    if (d.lng == null) return;
    const [glng, glat] = wgs84ToGcj02(d.lng, d.lat);
    const size = Math.max(4, Math.min(14, Math.round(Math.log2(d.count + 1) * 2)));
    const mk = L.circleMarker([glat, glng], { radius: size, color: '#1f5fbf', fillColor: '#3a7bd5', fillOpacity: 0.5 }).addTo(bigLayer);
    mk.bindPopup(`<b>${esc(d.name)}</b><br/>留言 <b>${esc(d.count)}</b> 条<br/>常见诉求：${(d.top_fields || []).map(esc).join('、') || '—'}`);
    mk.on('click', () => bigMap.setView([glat, glng], 10));
  });
  const top = ds[0];
  if (top) { const [glng, glat] = wgs84ToGcj02(top.lng, top.lat); bigMap.setView([glat, glng], 5); }
}

// ============================================================
// 风险预警
// ============================================================
async function loadRisk() {
  const wrap = document.getElementById('riskList');
  wrap.innerHTML = '<div class="dash-empty">加载中…</div>';
  try {
    if (!dashData) {
      const resp = await fetch('/api/dashboard');
      if (!resp.ok) throw new Error('接口返回 ' + resp.status);
      dashData = await resp.json();
    }
  } catch (e) { wrap.innerHTML = '<div class="dash-empty">加载失败：' + esc(e.message) + '</div>'; return; }
  const risks = dashData.risk || [];
  if (!risks.length) { wrap.innerHTML = '<div class="dash-empty">暂无风险留言</div>'; return; }
  wrap.innerHTML = '';
  risks.forEach(r => {
    const c = el('div', 'risk-card');
    c.innerHTML = `<div class="risk-head"><span class="risk-badge">${esc(r.keyword)}</span><span class="risk-prov">${esc(r.province)}</span><span class="risk-time">${esc(r.time)}</span></div>
      <div class="risk-text">${esc(r.text)}…</div>`;
    wrap.appendChild(c);
  });
}

// ============================================================
// 建设中 / API 设置
// ============================================================
function showTodo(name) {
  document.getElementById('todoText').textContent = `「${name}」正在建设中，敬请期待。`;
  document.getElementById('todoModal').classList.add('show');
}
// 用元素存在性兜底（无需 API key 也能用本地 LLM）

// ============================================================
// 对话（SSE 流式）
// ============================================================
const chatbox = document.getElementById('chatbox');
let busy = false;
function setBusy(b) {
  busy = b;
  const btn = document.getElementById('sendBtn');
  if (btn) btn.disabled = b;
  document.getElementById('statusDot').classList.toggle('busy', b);
  document.getElementById('statusText').textContent = b ? '处理中…' : '就绪';
}
function addMsg(role, html) {
  const wrap = el('div', 'msg msg-' + (role === 'user' ? 'user' : 'bot'));
  const bubble = el('div', 'bubble', html);
  wrap.appendChild(bubble);
  chatbox.appendChild(wrap);
  chatbox.scrollTop = chatbox.scrollHeight;
  return bubble;
}

async function send(text) {
  if (busy || !text.trim()) return;
  document.querySelector('.welcome')?.remove();
  addMsg('user', esc(text));
  setBusy(true);
  const bubble = addMsg('bot', '<span class="spinner"></span> 正在规划执行…');
  const traceArr = [];
  try {
    const apiKey = localStorage.getItem('ds_api_key') || '';
    const resp = await fetch('/api/chat/stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, user_id: sessionId, api_key: apiKey })
    });
    if (!resp.ok || !resp.body) throw new Error('流式请求失败 ' + resp.status);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, idx); buffer = buffer.slice(idx + 2);
        const line = frame.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        try { handleStream(JSON.parse(line.slice(6)), bubble, traceArr); } catch (e) { /* 忽略坏帧 */ }
      }
    }
    setBusy(false);
  } catch (e) {
    bubble.innerHTML = '请求失败：' + esc(e.message);
    setBusy(false);
  }
}
function handleStream(payload, bubble, traceArr) {
  if (payload.type === 'plan') { bubble.innerHTML = ''; bubble.appendChild(renderPlanCard(payload.plan)); }
  else if (payload.type === 'step') { traceArr.push(payload); renderTrace(traceArr); bubble.innerHTML = '<span class="spinner"></span> ' + esc(actionCn(payload.action) || '处理') + ' 中…'; }
  else if (payload.type === 'result') { bubble.innerHTML = ''; bubble.appendChild(renderResult(payload.result)); bindCaseLinks(); }
  else if (payload.type === 'error') { bubble.innerHTML = '运行出错：' + esc(payload.message); }
}
// 引用案例可点击查看
async function bindCaseLinks() {
  document.querySelectorAll('.case-link').forEach(a => {
    a.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = a.dataset.rid;
      try {
        const r = await fetch('/api/case/' + encodeURIComponent(id));
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const c = await r.json();
        document.getElementById('caseContent').innerHTML = `<b>案例 ${esc(c.doc_id)}</b>${c.title ? ' · ' + esc(c.title) : ''}<hr style="border:none;border-top:1px solid #eee;margin:8px 0"/>` + esc(c.content);
        document.getElementById('caseModal').classList.add('show');
      } catch (err) { alert('查看案例失败：' + err.message); }
    });
  });
}
function renderPlanCard(plan) {
  const wrap = el('div', 'result-wrap');
  if (plan && plan.steps) {
    wrap.appendChild(card('处理步骤', plan.steps.map(s => `<div class="plan-step"><span class="plan-idx">${s.step_id}</span><span>${esc(actionCn(s.action_type))}</span><span style="color:#888">${esc(s.objective || '')}</span></div>`).join('')));
  }
  return wrap;
}

// 动作类型 → 中文（去掉专业术语，降低"AI 味"）
const ACTION_CN = {
  perceive: '感知分析', analyze: '问题分析', retrieve: '案例检索', retrieve_policy: '政策检索', stats: '数据统计',
  geo_query: '空间分析', decide: '生成处理建议', mcp_call: '模型计算',
};
function actionCn(a) { return ACTION_CN[a] || String(a || ''); }

// ---- 结果渲染 ----
let lastWO = null;   // 最近一次生成的工单（供复制/下载按钮使用）
function renderResult(res) {
  const wrap = el('div', 'result-wrap');
  if (!res) return wrap;

  // 处理工单（数字员工可交付物）：排在最前
  if (res.work_order) {
    lastWO = res.work_order;
    const wo = res.work_order;
    const m = wo._meta || {};
    const comp = m.completeness != null ? Math.round(m.completeness * 100) + '%' : '—';
    const basis = (wo.policy_basis || []).length ? wo.policy_basis.join('；') : '（暂无匹配条款）';
    const cases = (wo.reference_cases || []).length ? wo.reference_cases.map(c => `<span class="case-link" data-rid="${esc(c)}">案例 ${esc(c)}</span>`).join(' ') : '（无）';
    const body =
      `<div class="wo-grid">` +
        woCell('工单号', wo.order_id || '—') + woCell('类别/领域', `${wo.complaint_type || '—'} · ${wo.field || '—'}`) +
        woCell('事发区域', wo.region || '—') + woCell('紧急/风险', `${wo.urgency || '—'} · ${wo.risk_level || '—'}`) +
        woCell('归口部门', wo.responsible_department || '—') + woCell('承办', wo.handler || '—') +
        woCell('办理时限', wo.deadline || '—') + woCell('复核', wo.review_route || '—') +
      `</div>` +
      `<div class="wo-row"><span class="k">诉求摘要</span><span>${esc(wo.complaint_summary || '')}</span></div>` +
      `<div class="wo-row"><span class="k">处置措施</span><span>${esc(wo.measures || '')}</span></div>` +
      `<div class="wo-row"><span class="k">政策依据</span><span>${esc(basis)}</span></div>` +
      `<div class="wo-row"><span class="k">参考案例</span><span>${cases}</span></div>` +
      `<div class="wo-actions"><button class="wo-btn" data-act="copy">📋 复制工单</button><button class="wo-btn" data-act="dl">⬇ 下载 JSON</button><span class="wo-comp">字段完整率 ${comp}</span></div>`;
    wrap.appendChild(card('📋 处理工单', body));
  }

  // 核心结论（前置、醒目）
  if (res.analysis) {
    const a = res.analysis;
    const gateTxt = res.gate?.route === 'pass' ? '已审核通过' : res.gate?.route === 'escalate' ? '需人工复核' : res.gate?.route === 'retry' ? '建议重新分析' : '—';
    wrap.appendChild(card('🎯 核心结论',
      kv('诉求摘要', a.summary) +
      kv('紧急程度', (a.urgency || '') + (a.risk_level ? ' / ' + a.risk_level : '')) +
      kv('责任部门', (a.predicted_department || '')) +
      kv('审核', gateTxt)));
  }

  if (res.plan) {
    wrap.appendChild(card('处理步骤', res.plan.steps.map(s => {
      const cls = 'plan-step ' + (s.status === 'done' ? 'done' : s.status === 'failed' ? 'failed' : '');
      return `<div class="${cls}"><span class="plan-idx">${s.step_id}</span><span>${esc(actionCn(s.action_type))}</span><span style="color:#888">${esc(s.objective || '')}</span></div>`;
    }).join('')));
  }
  if (res.analysis) {
    const a = res.analysis;
    wrap.appendChild(card('问题分析',
      kv('类别', (res.perception?.category || a.category || '')) +
      kv('责任部门', a.predicted_department || '') +
      kv('摘要', a.summary) + kv('判断依据', a.reasoning_summary)));
  }
  if (res.gate) {
    const g = res.gate;
    const badge = g.route === 'pass' ? '<span class="trace-badge badge-pass">已通过</span>' : g.route === 'escalate' ? '<span class="trace-badge badge-escalate">转人工</span>' : '<span class="trace-badge badge-retry">建议重审</span>';
    let reviewTxt = '';
    if (g.votes) reviewTxt = Object.entries(g.votes).map(([k, v]) => `${v.winner}`).join('；');
    wrap.appendChild(card('结果复核', badge, reviewTxt ? kv('复核意见', reviewTxt) : ''));
  }
  if (res.decision) {
    const d = res.decision;
    // 增强的思维链展示（DeepSeek Harness 风格）
    const chain = (d.reasoning_chain || []).map((c, i) => {
      const stepClass = i === 0 ? 'chain-item chain-first' : i === (d.reasoning_chain.length - 1) ? 'chain-item chain-last' : 'chain-item';
      return `<div class="${stepClass}"><span class="chain-step">${i + 1}</span><span class="chain-content">${esc(c)}</span></div>`;
    }).join('');
    
    // 引用案例（带摘要）
    let casesHtml = '';
    if (d.related_cases && d.related_cases.length > 0 && res.retrieved && res.retrieved.length > 0) {
      casesHtml = '<div class="cases-container">';
      d.related_cases.forEach(id => {
        const found = res.retrieved.find(r => r.doc_id === id);
        if (found) {
          const meta = found.metadata || {};
          const dept = meta.department || '未知部门';
          const field = meta.field || '未知领域';
          const location = meta.location || meta.city || meta.province || '';
          // 只保留汉字
          const raw = (found.content || '').slice(0, 120);
          const summary = raw.replace(/[^\u4e00-\u9fa5]/g, '');
          casesHtml += `
            <div class="case-card">
              <div class="case-header">
                <a href="#" class="case-link case-chip" data-rid="${esc(id)}">📄 案例 ${esc(id)}</a>
                <span class="case-dept">${esc(dept)}</span>
              </div>
              <div class="case-meta">${esc(field)} · ${esc(location)}</div>
              <div class="case-summary">${esc(summary)}</div>
            </div>`;
        } else {
          casesHtml += `<a href="#" class="case-link case-chip" data-rid="${esc(id)}">📄 案例 ${esc(id)}</a> `;
        }
      });
      casesHtml += '</div>';
    } else if (d.related_cases) {
      casesHtml = d.related_cases.map(id => `<a href="#" class="case-link case-chip" data-rid="${esc(id)}">📄 案例 ${esc(id)}</a>`).join(' ');
    }
    
    // 政策依据（引用真实条款，从 res.policy 中匹配标题+条款号）
    let policyHtml = '';
    const pdocs = (res.policy || []);
    if (d.policy_references && d.policy_references.length > 0) {
      const items = d.policy_references.map(ref => {
        const norm = (ref || '').replace(/[《》\s]/g, '');
        const found = pdocs.find(p => {
          const t = ((p.metadata && p.metadata.title) || '').replace(/[《》\s]/g, '');
          const a = ((p.metadata && p.metadata.article_no) || '').replace(/[《》\s]/g, '');
          return norm && t && (norm === t || norm.includes(t)) && a && norm.includes(a);
        });
        const auth = found && found.metadata ? (found.metadata.authority || '') : '';
        const body = found ? (found.content || '').split(' | ').slice(-1)[0] : '';
        return '<div class="policy-item"><span class="policy-ref">' + esc(ref) + '</span>' +
          (auth ? ' <span class="policy-auth">' + esc(auth) + '</span>' : '') +
          (body ? '<div class="policy-body">' + esc(body.slice(0, 80)) + '…</div>' : '') + '</div>';
      }).join('');
      policyHtml = '<div class="policy-container">' + items + '</div>';
    }
    
    wrap.appendChild(card('处理建议', 
      kv('责任部门', d.responsible_department) + 
      kv('建议措施', d.recommended_action) + 
      kv('回复建议', d.generated_reply) + 
      (casesHtml ? kvRaw('参考依据', casesHtml) : '') + 
      (policyHtml ? kvRaw('政策依据', policyHtml) : '') + 
      (chain ? '<div class="chain-label">补充说明</div><div class="chain-container">' + chain + '</div>' : '')
    ));
  }
  if (res.geo && res.geo.query_location) {
    const g = res.geo;
    wrap.appendChild(card('空间分析',
      kv('地点', `${g.query_location.province || ''}${g.query_location.city || ''}${g.query_location.district || ''}`) +
      kv('覆盖范围', (g.radius_km || 0) + ' 公里') + kv('相关案例', g.nearby_count + ' 条') +
      (g.nearby_category_dist ? kv('类别分布', Object.entries(g.nearby_category_dist).map(([k, v]) => `${k}×${v}`).join('，')) : '')));
    renderMap(g);
  } else if (res.geo && res.geo.note) {
    clearMapState('本次留言未识别到可定位地点（' + res.geo.note + '）');
  } else {
    // 本次结果没有任何地点信息：清空旧地图，避免残留上一条/别处的位置
    clearMapState();
  }
  
  // 洪水风险可视化（如果有MCP调用结果）
  if (res.plan && res.plan.steps) {
    const mcpStep = res.plan.steps.find(s => s.action_type === 'mcp_call' && s.result?.flood_summary);
    if (mcpStep) {
      const flood = mcpStep.result.flood_summary;
      const riskColor = flood.high_risk_count > 5 ? '#dc2626' : flood.high_risk_count > 2 ? '#f59e0b' : '#10b981';
      wrap.appendChild(card('🌊 洪水风险评估',
        `<div style="border-left: 4px solid ${riskColor}; padding-left: 12px; margin-bottom: 10px;">` +
        kvRaw('高风险点', `<span style="color:#dc2626;font-weight:600">${flood.high_risk_count} 个</span>`) +
        kvRaw('中风险点', `<span style="color:#f59e0b;font-weight:600">${flood.medium_risk_count} 个</span>`) +
        kvRaw('低风险点', `<span style="color:#10b981;font-weight:600">${flood.low_risk_count} 个</span>`) +
        kv('管网总数', flood.total_pipes + ' 条') +
        kv('溢流管网比例', (flood.overflow_pipe_ratio * 100).toFixed(1) + '%') +
        kv('最大降雨强度', flood.max_rainfall_mmh + ' mm/h') +
        '</div>' +
        (flood.high_risk_points && flood.high_risk_points.length > 0 ? 
          '<div style="font-size:12px;color:#6b7280;margin-top:8px;"><b>高风险点详情：</b></div>' +
          flood.high_risk_points.map(p => 
            `<div style="font-size:12px;padding:4px 0;border-bottom:1px dashed #e5e7eb;">` +
            `${p.pipe_id}: ${p.risk_level}风险 | 溢流时间 ${p.overflow_hour}h | 溢流比例 ${(p.overflow_ratio*100).toFixed(1)}%</div>`
          ).join('')
        : '')
      ));
      // 在地图上显示洪水风险点
      renderFloodRiskOnMap(flood);
    }
    
    // 交通风险可视化
    const trafficStep = res.plan.steps.find(s => s.action_type === 'mcp_call' && s.result?.traffic_summary);
    if (trafficStep) {
      const traffic = trafficStep.result.traffic_summary;
      const trafficColor = traffic.high_risk_roads > 5 ? '#dc2626' : traffic.high_risk_roads > 2 ? '#f59e0b' : '#10b981';
      wrap.appendChild(card('🚗 交通流量预测',
        `<div style="border-left: 4px solid ${trafficColor}; padding-left: 12px; margin-bottom: 10px;">` +
        kv('监控路段', traffic.total_roads + ' 条') +
        kvRaw('高风险路段', `<span style="color:#dc2626;font-weight:600">${traffic.high_risk_roads} 条</span>`) +
        kvRaw('中风险路段', `<span style="color:#f59e0b;font-weight:600">${traffic.medium_risk_roads} 条</span>`) +
        kvRaw('低风险路段', `<span style="color:#10b981;font-weight:600">${traffic.low_risk_roads} 条</span>`) +
        kv('平均拥堵指数', traffic.avg_congestion?.toFixed(2)) +
        kvRaw('峰值拥堵指数', `<span style="color:#dc2626;font-weight:600">${traffic.peak_congestion?.toFixed(2)}</span>`) +
        '</div>'
      ));
    }
    
    // 生活圈分析可视化
    const livingStep = res.plan.steps.find(s => s.action_type === 'mcp_call' && s.result?.living_summary);
    if (livingStep) {
      const living = livingStep.result.living_summary;
      const livingColor = living.overall_coverage > 0.8 ? '#10b981' : living.overall_coverage > 0.5 ? '#f59e0b' : '#dc2626';
      wrap.appendChild(card('🏘️ 15分钟生活圈分析',
        `<div style="border-left: 4px solid ${livingColor}; padding-left: 12px; margin-bottom: 10px;">` +
        kv('社区总数', living.total_communities + ' 个') +
        kvRaw('整体覆盖率', `<span style="color:${livingColor};font-weight:600">${(living.overall_coverage * 100).toFixed(1)}%</span>`) +
        kv('平均可达性', living.avg_accessibility?.toFixed(2) + ' 分钟') +
        '</div>' +
        (living.facility_coverage ? 
          '<div style="font-size:12px;color:#6b7280;margin-top:8px;"><b>设施覆盖率：</b></div>' +
          Object.entries(living.facility_coverage).map(([k, v]) => 
            `<div style="font-size:12px;padding:4px 0;border-bottom:1px dashed #e5e7eb;">` +
            `${k}: ${(v * 100).toFixed(1)}%</div>`
          ).join('')
        : '')
      ));
    }
  }
  if (res.trace) renderTrace(res.trace);
  if (res.errors && res.errors.length) wrap.appendChild(card('错误', res.errors.map(e => `<div style="color:#dc2626">${esc(e)}</div>`).join('')));
  return wrap;
}
function card(title, body, extra = '') {
  const c = el('div', 'result-card');
  c.appendChild(el('div', 'rc-head', esc(title) + (extra || '')));
  c.appendChild(el('div', 'rc-body', body));
  return c;
}
function kv(k, v) { if (v == null || v === '') return ''; return `<div class="kv"><span class="k">${esc(k)}</span><span>${esc(v)}</span></div>`; }
// 与 kv 相同，但 v 视为**已构造好的安全 HTML**（不再转义）——用于引用案例/政策等富内容
function kvRaw(k, v) { if (v == null || v === '') return ''; return `<div class="kv"><span class="k">${esc(k)}</span><span>${v}</span></div>`; }
// 轻量 Markdown 渲染：先转义（防 XSS）再套格式，用于 VLM 识别结果等外部文本
function renderMdLite(text) {
  if (!text) return '';
  let s = esc(String(text)).replace(/\r\n/g, '\n');
  s = s.replace(/^\s*#{1,6}\s*(.+?)\s*$/gm, '<div class="md-h">$1</div>');
  s = s.replace(/^\s*-{3,}\s*$/gm, '<hr class="md-hr"/>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/^\s*[-*]\s+(.+)$/gm, '<div class="md-li">• $1</div>');
  const paras = s.split(/\n{2,}/).map(p => '<p>' + p.replace(/\n/g, '<br/>') + '</p>').join('');
  return '<div class="md-lite">' + paras + '</div>';
}
function woCell(k, v) { return `<div class="wo-cell"><div class="wo-k">${esc(k)}</div><div class="wo-v">${v == null || v === '' ? '—' : esc(v)}</div></div>`; }
function renderTrace(trace) {
  const NODE_CN = { planner: '规划', executor: '执行', replanner: '决策', quality_gate: '复核', human_review: '人工', start: '开始' };
  const list = document.getElementById('traceList');
  if (!list) return;
  list.innerHTML = '';
  trace.forEach((ev, idx) => {
    // 增强的思考轨迹展示
    const item = el('div', 'trace-item');
    
    // 步骤编号
    const stepNum = el('span', 'trace-step-num', `${idx + 1}`);
    item.appendChild(stepNum);
    
    // 节点和动作
    const nodeAction = el('span', 'trace-node-action');
    nodeAction.innerHTML = `<span class="trace-node">${esc(NODE_CN[ev.node] || ev.node)}</span><span class="trace-arrow">→</span><span class="trace-action">${esc(actionCn(ev.action))}</span>`;
    item.appendChild(nodeAction);
    
    // 延迟时间
    const ms = el('span', 'trace-ms', `${Math.round(ev.latency_ms || 0)}ms`);
    item.appendChild(ms);
    
    // 额外信息（如有）
    if (ev.extra && Object.keys(ev.extra).length > 0) {
      const extra = el('span', 'trace-extra', JSON.stringify(ev.extra));
      item.appendChild(extra);
    }
    
    list.appendChild(item);
  });
}

// ---- chat 小地图 ----
let map = null, markerLayer = null;
function initMap() {
  if (map) return;
  map = L.map('map', { center: [35, 105], zoom: 5 });
  L.tileLayer('https://wprd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&style=7&x={x}&y={y}&z={z}', { subdomains: ['1','2','3','4'], attribution: '高德地图' }).addTo(map);
  markerLayer = L.layerGroup().addTo(map);
}
function renderMap(geo) {
  initMap();
  markerLayer.clearLayers();
  document.getElementById('mapEmpty').style.display = 'none';
  const q = geo.query_location;
  if (q && q.lng != null) {
    const [glng, glat] = wgs84ToGcj02(q.lng, q.lat);
    L.marker([glat, glng], { title: '诉求地点' }).addTo(markerLayer).bindPopup(`<b>诉求地点</b><br/>${q.province || ''}${q.city || ''}${q.district || ''}`).openPopup();
    L.circle([glat, glng], { radius: (geo.radius_km || 50) * 1000, color: '#1f5fbf', fillOpacity: 0.05 }).addTo(markerLayer);
  }
  (geo.nearby_samples || []).forEach(s => {
    if (s.lng == null) return;
    const [nlng, nlat] = wgs84ToGcj02(s.lng, s.lat);
    L.circleMarker([nlat, nlng], { radius: 5, color: '#d97706', fillOpacity: 0.7 }).addTo(markerLayer).bindPopup(`${s.category || ''}<br/>${s.location || ''}<br/>距离 ${s.dist_km}km`);
  });
  if (q && q.lng != null) { const [clng, clat] = wgs84ToGcj02(q.lng, q.lat); map.setView([clat, clng], 9); } else { map.setView([35, 105], 5); }
}

// 清空地图并复位（用于"本次无地点/无空间分析"时，避免残留上一次的地点/标记，造成"问A显示B"的错觉）
function clearMapState(text) {
  if (markerLayer) markerLayer.clearLayers();
  const empty = document.getElementById('mapEmpty');
  if (empty) { empty.textContent = text || '执行含空间分析的诉求后，此处显示地点与邻近案例'; empty.style.display = 'block'; }
  if (map) map.setView([35, 105], 5);
}

// 洪水风险点地图渲染
function renderFloodRiskOnMap(flood) {
  initMap();
  document.getElementById('mapEmpty').style.display = 'none';
  
  (flood.high_risk_points || []).forEach(p => {
    if (p.lng == null || p.lat == null) return;
    const [flng, flat] = wgs84ToGcj02(p.lng, p.lat);
    const color = p.risk_level === '高' ? '#dc2626' : p.risk_level === '中' ? '#f59e0b' : '#10b981';
    L.circleMarker([flat, flng], { 
      radius: 8, 
      color: color, 
      fillColor: color,
      fillOpacity: 0.8 
    }).addTo(markerLayer).bindPopup(
      `<b>🌊 洪水风险点 ${p.pipe_id}</b><br/>` +
      `风险等级: <span style="color:${color}">${p.risk_level}</span><br/>` +
      `溢流时间: ${p.overflow_hour}h<br/>` +
      `溢流比例: ${(p.overflow_ratio * 100).toFixed(1)}%<br/>` +
      `管网直径: ${p.diameter_m}m<br/>` +
      `管网长度: ${p.length_m}m`
    );
  });
  
  // 设置地图视图到第一个风险点
  if (flood.high_risk_points && flood.high_risk_points.length > 0) {
    const first = flood.high_risk_points[0];
    if (first.lng && first.lat) {
      const [flng, flat] = wgs84ToGcj02(first.lng, first.lat);
      map.setView([flat, flng], 12);
    }
  }
}

// ============================================================
// 事件绑定
// ============================================================
renderCards();
document.querySelectorAll('[data-back]').forEach(b => b.addEventListener('click', backHome));

// 处理工单：复制 / 下载（全局委托，读取最近一次工单）
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-act="copy"], [data-act="dl"]');
  if (!btn) return;
  e.preventDefault();
  if (!lastWO) { alert('暂无工单可操作'); return; }
  if (btn.dataset.act === 'copy') {
    const txt = woToText(lastWO);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(() => alert('✅ 工单已复制到剪贴板'), () => alert('复制失败，请手动复制'));
    } else { prompt('复制下方工单内容：', txt); }
  } else if (btn.dataset.act === 'dl') {
    const blob = new Blob([JSON.stringify(lastWO, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (lastWO.order_id || 'workorder') + '.json';
    a.click();
  }
});
function woToText(wo) {
  const L = [];
  L.push('# 处理工单 ' + (wo.order_id || ''));
  L.push('类别/领域：' + (wo.complaint_type || '') + ' · ' + (wo.field || ''));
  L.push('事发区域：' + (wo.region || '') + '（紧急 ' + (wo.urgency || '') + ' / 风险 ' + (wo.risk_level || '') + '）');
  L.push('归口部门：' + (wo.responsible_department || ''));
  L.push('承办：' + (wo.handler || ''));
  L.push('办理时限：' + (wo.deadline || ''));
  L.push('处置措施：' + (wo.measures || ''));
  L.push('政策依据：' + ((wo.policy_basis || []).join('；') || '（暂无）'));
  L.push('参考案例：' + ((wo.reference_cases || []).join('、') || '（无）'));
  L.push('面向市民回复：' + (wo.reply_to_citizen || ''));
  L.push('复核：' + (wo.review_route || ''));
  return L.join('\n');
}

const form = document.getElementById('inputForm');
if (form) {
  form.addEventListener('submit', e => {
    e.preventDefault();
    const inp = document.getElementById('textInput');
    send(inp.value); inp.value = '';
  });
}
// 输入时智能推荐该走哪个功能
const textInput = document.getElementById('textInput');
if (textInput) {
  textInput.addEventListener('input', async () => {
    const v = textInput.value.trim();
    const hint = document.getElementById('routeHint');
    if (!v) { hint.innerHTML = '<span class="route-cap">我能帮你：</span><button class="route-chip" data-view="quick">快速分析</button><button class="route-chip" data-view="search">查案例</button><button class="route-chip" data-view="dashboard">看民情</button><button class="route-chip" data-view="map">地图</button>'; bindRouteChips(); return; }
    try {
      const r = await fetch('/api/route?q=' + encodeURIComponent(v));
      const d = await r.json();
      if (d.recommend) hint.innerHTML = '<span class="route-cap">建议用</span><button class="route-chip" data-view="' + d.recommend + '">' + esc(d.name) + '</button><span class="route-reason">' + esc(d.reason || '') + '</span>';
      bindRouteChips();
    } catch (e) { /* ignore */ }
  });
}
function bindRouteChips() {
  document.querySelectorAll('.route-chip').forEach(b => {
    b.addEventListener('click', () => { showView('view-' + b.dataset.view); });
  });
}
if (document.getElementById('routeHint')) {
  document.getElementById('routeHint').innerHTML = '<span class="route-cap">我能帮你：</span><button class="route-chip" data-view="quick">快速分析</button><button class="route-chip" data-view="search">查案例</button><button class="route-chip" data-view="dashboard">看民情</button><button class="route-chip" data-view="map">地图</button>';
  bindRouteChips();
}
document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
  document.getElementById('textInput').value = c.textContent; send(c.textContent);
}));

// ---- 建设中 / API 设置弹窗 ----
document.getElementById('closeTodo').addEventListener('click', () => document.getElementById('todoModal').classList.remove('show'));
document.getElementById('todoModal').addEventListener('click', e => { if (e.target.id === 'todoModal') document.getElementById('todoModal').classList.remove('show'); });

document.getElementById('closeCase').addEventListener('click', () => document.getElementById('caseModal').classList.remove('show'));
document.getElementById('caseModal').addEventListener('click', e => { if (e.target.id === 'caseModal') document.getElementById('caseModal').classList.remove('show'); });

document.getElementById('btnApi').addEventListener('click', () => {
  document.getElementById('apiKeyInput').value = localStorage.getItem('ds_api_key') || '';
  document.getElementById('apiModal').classList.add('show');
});
document.getElementById('closeApi').addEventListener('click', () => document.getElementById('apiModal').classList.remove('show'));
document.getElementById('apiModal').addEventListener('click', e => { if (e.target.id === 'apiModal') document.getElementById('apiModal').classList.remove('show'); });
document.getElementById('saveApi').addEventListener('click', () => {
  const v = document.getElementById('apiKeyInput').value.trim();
  if (v) localStorage.setItem('ds_api_key', v); else localStorage.removeItem('ds_api_key');
  document.getElementById('statusText').textContent = v ? '已设置自定义 API Key' : '已恢复默认';
  document.getElementById('apiModal').classList.remove('show');
});
document.getElementById('resetApi').addEventListener('click', () => {
  localStorage.removeItem('ds_api_key');
  document.getElementById('apiKeyInput').value = '';
  document.getElementById('statusText').textContent = '已恢复默认';
});

// ============================================================
// 相似案例检索 + 单条快速分析
// ============================================================
function caseResultCard(it) {
  const meta = it.metadata || {};
  const c = el('div', 'case-card');
  c.innerHTML = `<div class="case-card-head"><span class="case-id">#${esc(it.doc_id)}</span><span class="case-meta">${esc(meta.field || '')} · ${esc(meta.department || '')} · ${esc(meta.location || '')}</span></div>
    <div class="case-card-body">${esc((it.content || '').slice(0, 200))}…</div>`;
  return c;
}
async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  const box = document.getElementById('searchResults');
  if (!q) return;
  box.innerHTML = '<div class="dash-empty">检索中…</div>';
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q) + '&top_k=6');
    const d = await r.json();
    if (!d.results || !d.results.length) { box.innerHTML = '<div class="dash-empty">无匹配案例</div>'; return; }
    box.innerHTML = '';
    d.results.forEach(it => box.appendChild(caseResultCard(it)));
    bindCaseLinks();
  } catch (e) { box.innerHTML = '<div class="dash-empty">检索失败：' + esc(e.message) + '</div>'; }
}
async function doQuick() {
  const t = document.getElementById('quickInput').value.trim();
  const box = document.getElementById('quickResult');
  if (!t) return;
  box.innerHTML = '<div class="dash-empty">分析中…</div>';
  try {
    const r = await fetch('/api/quick', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t }) });
    const d = await r.json();
    box.innerHTML = '';
    const w = el('div', 'result-wrap');
    w.appendChild(card('⚡ 快速分析',
      kv('诉求', d.text) + kv('事件分类', d.category || d.field || '其他') + kv('紧急度', d.urgency) +
      kv('责任部门', d.responsible_department) + kv('相似案例数', d.nearby.length)));
    box.appendChild(w);
    const n = el('div', 'case-list');
    (d.nearby || []).forEach(it => n.appendChild(caseResultCard(it)));
    box.appendChild(n);
    bindCaseLinks();
  } catch (e) { box.innerHTML = '<div class="dash-empty">分析失败：' + esc(e.message) + '</div>'; }
}
const searchForm = document.getElementById('searchForm');
if (searchForm) searchForm.addEventListener('submit', e => { e.preventDefault(); doSearch(); });
const quickForm = document.getElementById('quickForm');
if (quickForm) quickForm.addEventListener('submit', e => { e.preventDefault(); doQuick(); });

// ============================================================
// 批量分析
// ============================================================
async function doBatch() {
  const fileInput = document.getElementById('batchFile');
  const box = document.getElementById('batchResult');
  if (!fileInput.files.length) { box.innerHTML = '<div class="dash-empty">请先选择 CSV/TXT 文件</div>'; return; }
  const text = await fileInput.files[0].text();
  box.innerHTML = '<div class="dash-empty">分析中…</div>';
  try {
    const r = await fetch('/api/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: text }) });
    const d = await r.json();
    if (!d.results || !d.results.length) { box.innerHTML = '<div class="dash-empty">解析不到留言</div>'; return; }
    let html = `<div class="dash-empty" style="padding:10px">共分析 ${d.total} 条</div><table class="batch-table"><thead><tr><th>#</th><th>留言</th><th>领域</th><th>归口部门</th><th>紧急度</th><th>满意度</th></tr></thead><tbody>`;
    d.results.forEach((x, i) => { html += `<tr><td>${i + 1}</td><td>${esc(x.text.slice(0, 28))}…</td><td>${esc(x.field)}</td><td>${esc(x.responsible_department)}</td><td>${esc(x.urgency)}</td><td>${esc(x.satisfaction)}</td></tr>`; });
    html += '</tbody></table>';
    box.innerHTML = html;
    const btn = el('button', 'primary-btn', '导出 CSV');
    btn.style.marginTop = '10px';
    btn.onclick = () => downloadBatch(d.results);
    box.appendChild(btn);
  } catch (e) { box.innerHTML = '<div class="dash-empty">分析失败：' + esc(e.message) + '</div>'; }
}
function downloadBatch(results) {
  let csv = '留言,领域,归口部门,紧急度,预期满意度\n';
  results.forEach(x => { csv += `"${(x.text || '').replace(/"/g, '""')}",${x.field},${x.responsible_department},${x.urgency},${x.satisfaction}\n`; });
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'batch_report.csv'; a.click();
}

// ============================================================
// 民情月报
// ============================================================
async function doReport() {
  const f = document.getElementById('repField').value.trim();
  const p = document.getElementById('repProvince').value.trim();
  const m = document.getElementById('repMonth').value.trim();
  const box = document.getElementById('reportResult');
  box.innerHTML = '<div class="dash-empty">生成中…</div>';
  const params = new URLSearchParams();
  if (f) params.set('field', f); if (p) params.set('province', p); if (m) params.set('month', m);
  try {
    const r = await fetch('/api/report?' + params.toString());
    const d = await r.json();
    box.innerHTML = '';
    const card = el('div', 'dash-card report-md');
    card.innerHTML = `<div class="panel-title">民情月报</div><div class="dash-body"><pre style="white-space:pre-wrap;font-family:inherit;line-height:1.8">${esc(d.report_md)}</pre></div>`;
    box.appendChild(card);
  } catch (e) { box.innerHTML = '<div class="dash-empty">生成失败：' + esc(e.message) + '</div>'; }
}

// ============================================================
// 决策复盘
// ============================================================
async function loadReview() {
  const box = document.getElementById('reviewList');
  box.innerHTML = '<div class="dash-empty">加载中…</div>';
  try {
    const r = await fetch('/api/history');
    const d = await r.json();
    if (!d.runs.length) { box.innerHTML = '<div class="dash-empty">暂无历史任务</div>'; return; }
    box.innerHTML = '';
    d.runs.forEach(run => {
      const text = (run.complaint_text || '').slice(0, 55) || run.run_id;
      const concl = run.conclusion || {};
      const updTag = run.has_updates
        ? `<span class="upd-tag${run.refreshed_at ? ' done' : ''}">${run.refreshed_at ? '已更新回答' : '有更新 ' + run.update_count}</span>`
        : '';
      const c = el('div', 'case-card review-item');
      c.innerHTML = `<div class="case-card-head"><span class="case-id">${esc(text)}</span><span class="case-meta">${esc(run.route || '')} ${updTag}</span></div>
        <div class="case-meta">${concl.department ? '归口：' + esc(concl.department) : ''}</div>`;
      const saveBtn = el('button', 'chain-btn', '保存为备注');
      saveBtn.style.marginTop = '6px';
      saveBtn.addEventListener('click', (e) => { e.stopPropagation(); saveTaskNote(run); });
      c.appendChild(saveBtn);
      c.addEventListener('click', () => showReviewDetail(run.run_id, c));
      box.appendChild(c);
    });
  } catch (e) { box.innerHTML = '<div class="dash-empty">加载失败：' + esc(e.message) + '</div>'; }
}
function saveTaskNote(run) {
  const note = `任务 ${run.run_id}：${(run.complaint_text || '').slice(0, 50)}；归口：${run.conclusion?.department || '未知'}；${(run.conclusion?.reply || '').slice(0, 40)}`;
  fetch('/api/memory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: note }) })
    .then(() => alert('已保存到任务记忆'))
    .catch(() => alert('保存失败'));
}
async function showReviewDetail(runId, cardEl) {
  try {
    const r = await fetch('/api/history/' + runId);
    const d = await r.json();
    let html = '';
    if (d.gate) html += `门控：${esc(d.gate.route)} / 一致性 ${d.gate.consistency}<br/>`;
    if (d.steps && d.steps.length) html += `步骤：${d.steps.map(s => `${s.node}/${s.action}`).join(' → ')}`;
    html += `<div><button class="chain-btn" data-chain="${esc(runId)}">🔍 关键证据链</button></div>`;
    if (d.updates && d.updates.length) {
      html += `<div class="upd-list"><div class="upd-title">留言更新（${d.updates.length}）</div>` +
        d.updates.map(u => `<div class="upd-item">${esc(u.content)}</div>`).join('');
      if (!d.run || !d.run.refreshed_at) {
        html += `<button class="refresh-btn" data-refresh="${esc(runId)}">结合更新重新分析</button>`;
      }
      html += `</div><div class="refresh-result" id="rr-${esc(runId)}"></div>`;
    }
    cardEl.querySelector('.case-card-body')?.remove();
    const body = el('div', 'case-card-body', html);
    cardEl.appendChild(body);
    body.querySelector('[data-chain]')?.addEventListener('click', ev => {
      ev.stopPropagation();
      toggleEvidenceChain(runId, cardEl);
    });
    cardEl.querySelector('[data-refresh]')?.addEventListener('click', ev => {
      ev.stopPropagation();
      refreshRun(runId, cardEl);
    });
  } catch (e) { /* ignore */ }
}

// ---- 关键证据链可视化（决策复盘点开后按需聚合，本地 BM25 零 LLM 成本）----
async function toggleEvidenceChain(runId, cardEl) {
  let box = cardEl.querySelector('.evc-box');
  if (box) { box.remove(); return; }  // 再点一次收起
  box = el('div', 'evc-box');
  box.innerHTML = '<div class="dash-empty">聚合证据链中…</div>';
  cardEl.querySelector('.case-card-body').appendChild(box);
  try {
    const r = await fetch('/api/history/' + encodeURIComponent(runId) + '/chain');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    renderEvidenceChain(runId, await r.json(), box);
  } catch (e) { box.innerHTML = '<div class="dash-empty">证据链加载失败：' + esc(e.message) + '</div>'; }
}

function evcNode(icon, title, innerHtml, tone) {
  return `<div class="evc-node ${tone || ''}"><div class="evc-dot">${icon}</div>` +
    `<div class="evc-body"><div class="evc-title">${esc(title)}</div>${innerHtml}</div></div>`;
}

function renderEvidenceChain(runId, d, box) {
  // 环1 诉求
  let html = evcNode('📣', '群众诉求', `<div class="evc-quote">${esc(d.complaint_text || '（未存原始留言）')}</div>`);
  // 环2 计划
  if (d.plan && d.plan.length) {
    html += evcNode('🗺️', '执行计划（' + d.plan.length + ' 步）',
      '<div class="evc-chips">' + d.plan.map(s =>
        `<span class="evc-chip act-${esc(s.action_type)}" title="${esc(s.objective)}">${esc(s.step_id)}. ${esc(s.action_type)}</span>`
      ).join('') + '</div>');
  }
  // 环3 执行轨迹
  if (d.execution && d.execution.length) {
    html += evcNode('⚙️', 'Agent 执行轨迹',
      d.execution.map(s => {
        const extra = s.extra ? Object.entries(s.extra).slice(0, 2).map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 40)}`).join(' ') : '';
        return `<div class="evc-step"><span class="trace-node">${esc(s.node)}</span><span class="trace-arrow">→</span><span class="trace-action">${esc(s.action)}</span>` +
          `<span class="trace-ms">${s.latency_ms}ms</span>${extra ? `<span class="evc-extra">${esc(extra)}</span>` : ''}${s.error ? '<span class="evc-err">失败</span>' : ''}</div>`;
      }).join(''));
  }
  // 环4 证据池
  if (d.evidence_pool && d.evidence_pool.length) {
    html += evcNode('📚', '检索证据池（BM25 本地重建 ' + d.evidence_pool.length + ' 条）',
      '<div class="evc-cases">' + d.evidence_pool.map(c =>
        `<a href="#" class="case-link evc-case ${c.cited ? 'cited' : ''}" data-rid="${esc(c.doc_id)}" title="${esc(c.snippet)}">` +
        `案例 ${esc(c.doc_id)} · ${esc(c.department || '未知部门')}${c.cited ? ' <b class="evc-cited-tag">被引用</b>' : ''}</a>`
      ).join('') + '</div>');
  }
  // 环5 引用校验
  if (d.citations && d.citations.length) {
    const dc = d.department_check || {};
    html += evcNode('🔎', '引用溯源校验',
      `<div class="evc-kv">责任部门：<b>${esc(dc.department || '-')}</b> ` +
      (dc.in_evidence ? '<span class="evc-ok">✓ 在证据案例中</span>' : (dc.department ? '<span class="evc-warn">⚠ 不在证据案例中</span>' : '')) + '</div>' +
      '<div class="evc-kv">' + d.citations.map(c => c.status === 'verified'
        ? `<span class="evc-ok">✓ 案例 ${esc(c.case_id)}</span>`
        : `<span class="evc-warn">⚠ 案例 ${esc(c.case_id)} 引用异常</span>`).join('　') + '</div>');
  }
  // 环6 推理链
  if (d.reasoning_chain && d.reasoning_chain.length) {
    html += evcNode('🧠', '推理链（' + d.reasoning_chain.length + ' 步）',
      d.reasoning_chain.map((c, i) => `<div class="chain-item"><span class="chain-step">${i + 1}</span><span class="chain-content">${esc(c)}</span></div>`).join(''));
  }
  // 环7 门控
  const g = d.gate || {};
  const gBadge = g.route === 'pass' ? '<span class="trace-badge badge-pass">通过</span>'
    : g.route === 'escalate' ? '<span class="trace-badge badge-escalate">转人工</span>'
    : g.route === 'retry' ? '<span class="trace-badge badge-retry">重写</span>' : '';
  html += evcNode('🚦', '质量门控（Self-Consistency）',
    gBadge + `<span class="evc-kv"> 一致性 <b>${g.consistency ?? '-'}</b></span>` +
    (g.votes ? '<div class="evc-kv">' + Object.entries(g.votes).map(([k, v]) => `${esc(k)}→${esc(v.winner)}(${v.consistency})`).join('；') + '</div>' : ''),
    g.route === 'escalate' ? 'tone-warn' : '');
  // 环8 回复 + 完整性结论
  const integ = d.integrity || {};
  const riskNote = d.decision?.risk_warning;
  html += evcNode('💬', '最终回复建议',
    `<div class="evc-quote">${esc(d.generated_reply || '-')}</div>` +
    `<div class="evc-kv">置信度 ${d.decision?.confidence ?? '-'} · 建议措施：${esc(d.decision?.recommended_action || '-')}</div>` +
    (riskNote ? `<div class="evc-warn">⚠ 风险提示：${esc(riskNote)}</div>` : ''));
  html += `<div class="evc-verdict ${integ.ok ? 'ok' : 'warn'}">` +
    (integ.ok ? '✓ 证据链完整，引用均可溯源' : '⚠ 审计提示：' + (integ.warnings || []).map(w => esc(w)).join('；')) + '</div>';
  box.innerHTML = `<div class="panel-title">🔗 关键证据链 · run ${esc(runId)}</div><div class="evc-list">${html}</div>`;
  bindCaseLinks();
}
async function refreshRun(runId, cardEl) {
  const box = document.getElementById('rr-' + runId);
  const btn = cardEl.querySelector('[data-refresh]');
  if (btn) { btn.disabled = true; btn.textContent = '正在结合更新重新分析…'; }
  try {
    const apiKey = localStorage.getItem('ds_api_key') || '';
    const r = await fetch('/api/history/' + runId + '/refresh', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: '', api_key: apiKey })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '刷新失败');
    if (!d.refreshed) { box.innerHTML = '<div class="dash-empty">' + esc(d.note || '无更新') + '</div>'; return; }
    const dec = d.decision || {};
    box.innerHTML =
      '<div class="upd-title">重新分析结果（结合 ' + d.updates_used + ' 条更新）</div>' +
      '<div class="upd-item"><b>归口：</b>' + esc(dec.responsible_department || '-') +
      '<br/><b>回复建议：</b>' + esc(dec.generated_reply || '-') +
      (dec.risk_warning ? '<br/><b>风险提示：</b>' + esc(dec.risk_warning) : '') + '</div>';
    const tag = cardEl.querySelector('.upd-tag');
    if (tag) { tag.textContent = '已更新回答'; tag.classList.add('done'); }
    if (btn) btn.remove();
  } catch (e) {
    if (box) box.innerHTML = '<div class="dash-empty">失败：' + esc(e.message) + '</div>';
    if (btn) { btn.disabled = false; btn.textContent = '结合更新重新分析'; }
  }
}
const batchBtn = document.getElementById('batchBtn');
if (batchBtn) batchBtn.addEventListener('click', doBatch);
const reportBtn = document.getElementById('reportBtn');
if (reportBtn) reportBtn.addEventListener('click', doReport);

// ============================================================
// 文档分析 / 表格分析（通用 skills 封装）
// ============================================================
async function doAnalyzeDoc() {
  const content = document.getElementById('docInput').value.trim();
  const box = document.getElementById('docResult');
  if (!content) { box.innerHTML = '<div class="dash-empty">请先粘贴文本</div>'; return; }
  box.innerHTML = '<div class="dash-empty">分析中…</div>';
  try {
    const r = await fetch('/api/analyze_document', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
    const d = await r.json();
    if (d.error) { box.innerHTML = '<div class="dash-empty">' + esc(d.error) + '</div>'; return; }
    box.innerHTML = '';
    const w = el('div', 'result-wrap');
    w.appendChild(card('📄 文本分析', kv('字数', d.n_chars) + kv('句子数', d.n_sents) + kv('高频词', (d.top_words || []).map(x => `${x[0]}×${x[1]}`).join('、') || '无') + kv('风险信号', d.risk?.join('、') || '无')));
    box.appendChild(w);
    const rp = el('div', 'dash-card report-md');
    rp.innerHTML = `<div class="panel-title">分析报告</div><div class="dash-body"><pre style="white-space:pre-wrap;font-family:inherit;line-height:1.8">${esc(d.report_md)}</pre></div>`;
    box.appendChild(rp);
  } catch (e) { box.innerHTML = '<div class="dash-empty">分析失败：' + esc(e.message) + '</div>'; }
}
async function doAnalyzeExcel() {
  const fileInput = document.getElementById('excelFile');
  const box = document.getElementById('excelResult');
  if (!fileInput.files.length) { box.innerHTML = '<div class="dash-empty">请先选择 CSV/TXT 文件</div>'; return; }
  const content = await fileInput.files[0].text();
  box.innerHTML = '<div class="dash-empty">分析中…</div>';
  try {
    const r = await fetch('/api/analyze_excel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
    const d = await r.json();
    if (d.error) { box.innerHTML = '<div class="dash-empty">' + esc(d.error) + '</div>'; return; }
    box.innerHTML = '';
    const w = el('div', 'result-wrap');
    w.appendChild(card('📋 数据分析', kv('行数', d.rows) + kv('列数', d.cols) + kv('数据质量', (d.quality * 100).toFixed(1) + '%') + kv('异常值列', d.outliers.length + ' 个')));
    box.appendChild(w);
    // 列字段表
    let ch = `<table class="batch-table"><thead><tr><th>列</th><th>类型</th><th>缺失</th></tr></thead><tbody>`;
    (d.columns || []).forEach(c => { ch += `<tr><td>${esc(c.name)}</td><td>${esc(c.dtype)}</td><td>${c.missing}</td></tr>`; });
    ch += '</tbody></table>';
    box.appendChild(el('div', '', ch));
    const rp = el('div', 'dash-card report-md');
    rp.innerHTML = `<div class="panel-title">分析报告</div><div class="dash-body"><pre style="white-space:pre-wrap;font-family:inherit;line-height:1.8">${esc(d.report_md)}</pre></div>`;
    box.appendChild(rp);
  } catch (e) { box.innerHTML = '<div class="dash-empty">分析失败：' + esc(e.message) + '</div>'; }
}
const docBtn = document.getElementById('docBtn');
if (docBtn) docBtn.addEventListener('click', doAnalyzeDoc);
const excelBtn = document.getElementById('excelBtn');
if (excelBtn) excelBtn.addEventListener('click', doAnalyzeExcel);

// ============================================================
// 对话页左侧：历史会话列表
// ============================================================
async function loadChatHistory() {
  const box = document.getElementById('historyList');
  if (!box) return;
  box.innerHTML = '<div class="dash-empty">加载中…</div>';
  try {
    const r = await fetch('/api/history');
    const d = await r.json();
    if (!d.runs.length) { box.innerHTML = '<div class="dash-empty">暂无记录</div>'; return; }
    box.innerHTML = '';
    d.runs.slice(0, 20).forEach(run => {
      const it = el('div', 'history-item');
      const txt = (run.complaint_text || '').slice(0, 18) || run.run_id;
      it.innerHTML = `<div class="t">${esc(txt)}</div><div class="d">${esc(run.conclusion?.department || '')}</div>`;
      it.addEventListener('click', () => showHistoryRun(run));
      box.appendChild(it);
    });
  } catch (e) { box.innerHTML = '<div class="dash-empty">加载失败</div>'; }
}
async function showHistoryRun(run) {
  // 复位中央对话 + 右侧地图/轨迹，只展示本 run 自己的数据（避免与上一次串位/残留）
  chatbox.innerHTML = '';
  clearMapState();
  document.querySelector('.welcome')?.remove();

  // 顶部返回按钮（样式化，避免"跑偏"）
  const backRow = el('div', 'history-back-row');
  const backBtn = el('button', 'back-btn', '← 新建对话');
  backBtn.addEventListener('click', () => { chatbox.innerHTML = ''; clearMapState(); renderWelcome(); });
  backRow.appendChild(backBtn);
  chatbox.appendChild(backRow);

  addMsg('user', run.complaint_text || '（历史诉求已归档，无原文）');
  const bubble = addMsg('bot', '<span class="spinner"></span> 正在读取历史结论…');
  try {
    const d = await (await fetch('/api/history/' + run.run_id)).json();
    bubble.innerHTML = '';
    const res = {};
    // 完整决策（不截断）
    if (d.gate) {
      res.gate = { route: d.gate.route, consistency: d.gate.consistency, votes: _safeParse(d.gate.votes_json) };
      if (d.gate.decision_json) res.decision = _safeParse(d.gate.decision_json);
    }
    // 本 run 自己的空间分析/计划（从 plan_json 重建，地图不再用残留的旧位置）
    const runRow = d.run || {};
    const plan = runRow.plan_json ? _safeParse(runRow.plan_json) : null;
    if (plan && plan.steps) {
      res.plan = plan;
      const gs = plan.steps.find(s => s.action_type === 'geo_query' && s.result && s.result.query_location);
      if (gs) { res.geo = gs.result; res.geo.nearby_samples = res.geo.nearby_samples || []; }
    }
    const wrap = el('div', 'result-wrap');
    wrap.appendChild(renderResult(res));
    bubble.appendChild(wrap);
    bindCaseLinks();
    // 右侧轨迹：重建为本 run 的步骤
    const tl = document.getElementById('traceList');
    if (tl) {
      const steps = d.steps || [];
      tl.innerHTML = '';
      if (steps.length) {
        steps.forEach((s, i) => {
          const it = el('div', 'trace-item');
          it.appendChild(el('span', 'trace-step-num', String(i + 1)));
          const na = el('span', 'trace-node-action');
          na.innerHTML = '<span class="trace-node">执行</span><span class="trace-arrow">→</span><span class="trace-action">' + esc(actionCn(s.action_type) || s.action_type) + '</span>';
          it.appendChild(na);
          it.appendChild(el('span', 'trace-ms', Math.round(s.latency_ms || 0) + 'ms'));
          tl.appendChild(it);
        });
      } else {
        tl.innerHTML = '<div class="dash-empty">该记录无过程步骤</div>';
      }
    }
  } catch (e) {
    bubble.innerHTML = '读取历史失败：' + esc(e.message);
  }
}
function _safeParse(s) { try { return JSON.parse(s); } catch (e) { return null; } }

// ============================================================
// 多模态：上传现场照片 → VLM 识图读字
// ============================================================
const chatImgInput = document.getElementById('chatImg');
if (chatImgInput) {
  chatImgInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (busy) return;
    busy = true;
    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = reader.result.split(',')[1];
      document.querySelector('.welcome')?.remove();
      addMsg('user', '📷 上传现场照片：' + file.name);
      const bubble = addMsg('bot', '<span class="spinner"></span> 正在识别图片…');
      try {
        const r = await fetch('/api/chat_image', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: b64 }) });
        const d = await r.json();
        if (d.error) { bubble.innerHTML = '识别失败：' + esc(d.error); }
        else if (d.llm_fallback) {
          // 无 LLM 余额：降级（归口 + 地图）
          bubble.innerHTML = '';
          const wrap = el('div', 'result-wrap');
          wrap.appendChild(card('📷 图片识别', renderMdLite(d.image_text || '')));
          if (d.quick) wrap.appendChild(card('🎯 快速结论', kv('类别', d.quick.category || d.quick.field || '其他') + kv('责任部门', d.quick.responsible_department || '') + kv('紧急度', d.quick.urgency || '')));
          if (d.geo && d.geo.query_location) { wrap.appendChild(card('📍 位置', kv('定位', `${d.geo.query_location.province || ''}${d.geo.query_location.city || ''}${d.geo.query_location.district || ''}`))); renderMap(d.geo); }
          bubble.appendChild(wrap);
        } else {
          // 完整管线结果（思维链/归口/决策/地图）
          bubble.innerHTML = '';
          const wrap = el('div', 'result-wrap');
          if (d.image_text) wrap.appendChild(card('📷 图片识别', renderMdLite(d.image_text || '')));
          const full = { ...d };
          // 去掉 image_text 避免重复，其余走完整渲染
          wrap.appendChild(renderResult(full));
          bubble.appendChild(wrap);
          bindCaseLinks();
        }
      } catch (err) { bubble.innerHTML = '识别失败：' + esc(err.message); }
      busy = false;
    };
    reader.readAsDataURL(file);
  });
}
function renderWelcome() {
  const w = el('div', 'welcome');
  w.innerHTML = '<h2>请输入一条群众留言</h2><p>系统将为您处理：感知 → 分析 → 检索 → 空间分析 → 决策 → 复核</p>' +
    '<div class="examples"><button class="chip">小区附近晚上施工噪音很大，希望有关部门处理</button>' +
    '<button class="chip">山西省太原市小店区南中环附近路灯长期不亮，影响夜间出行</button>' +
    '<button class="chip">我家暖气温度一直不达标，报修多次未解决</button></div>';
  chatbox.appendChild(w);
}
