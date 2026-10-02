// ═══════════════════════════════════════════════════════════
// RIFT COMPASS — MODERN ESPORTS FRONT-END
// Snappy GSAP Micro-interactions & Data Dragon Integration
// ═══════════════════════════════════════════════════════════

// ── Selectors & Constants ──
const $ = (selector) => document.querySelector(selector);
const roles = { ALL: 'Todas as Rotas', TOP: 'Topo', JUNGLE: 'Selva', MIDDLE: 'Meio', BOTTOM: 'Atirador', UTILITY: 'Suporte' };
const classes = { Mage: 'Mago', Assassin: 'Assassino', Fighter: 'Lutador', Tank: 'Tanque', Marksman: 'Atirador', Support: 'Suporte' };
const state = { analysis: null, recommendations: null, role: 'ALL', limit: 6, generation: 0, busy: false };

const number = (n, digits = 1) => Number(n).toLocaleString('pt-BR', { maximumFractionDigits: digits });

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// ── Data Dragon URLs ──
function getSplashUrl(championId) {
  return `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${championId}_0.jpg`;
}

function getCenteredSplashUrl(championId) {
  return `https://ddragon.leagueoflegends.com/cdn/img/champion/centered/${championId}_0.jpg`;
}

function portrait(champion, className = '') {
  const img = el('img', className);
  img.src = champion.image;
  img.alt = champion.name;
  img.loading = 'lazy';
  img.addEventListener('error', () => {
    img.src = '/static/favicon.svg';
  }, { once: true });
  return img;
}

// ── Notifications ──
function showError(message) {
  const err = $('#error');
  err.textContent = message;
  err.hidden = false;
  if (typeof gsap !== 'undefined') {
    gsap.fromTo(err, { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.25, ease: 'power2.out' });
  }
}

function clearError() {
  $('#error').hidden = true;
}

function loading(on, message = 'Consultando Summoner\'s Rift…') {
  state.busy = on;
  const statusEl = $('#status');
  statusEl.hidden = !on;
  statusEl.textContent = message;

  if (on && typeof gsap !== 'undefined') {
    gsap.fromTo(statusEl, { y: 15, opacity: 0 }, { y: 0, opacity: 1, duration: 0.25, ease: 'power2.out' });
  }

  $('#analyze-button').disabled = on;
  $('#demo-button').disabled = on;
  document.querySelectorAll('[data-role]').forEach(b => b.disabled = on);
  $('#dashboard').setAttribute('aria-busy', String(on));
}

// ── API ──
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  });

  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('Não foi possível ler a resposta do servidor.');
  }

  if (!response.ok) {
    if (response.status === 401) $('#login-dialog').showModal();
    const detail = Array.isArray(data.detail) ? 'Confira os campos da busca.' : data.detail;
    const wait = response.headers.get('Retry-After');
    throw new Error((detail || 'Não foi possível concluir a consulta.') + (wait ? ` Tente novamente em ${wait} segundos.` : ''));
  }
  return data;
}

// ── Tabs ──
function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach(b => {
    const active = b.dataset.tab === name;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });

  const dashboard = $('#dashboard');
  if (dashboard && dashboard.hidden && (name === 'catalog' || name === 'methodology')) {
    dashboard.hidden = false;
  }

  const panels = ['recommendations', 'history', 'catalog', 'methodology'];
  panels.forEach(tabName => {
    const panel = $(`#${tabName}-panel`);
    if (!panel) return;
    const isCurrent = tabName === name;
    panel.hidden = !isCurrent;

    if (isCurrent) {
      if (typeof gsap !== 'undefined') {
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!prefersReducedMotion) {
          gsap.fromTo(panel, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.25, ease: 'power2.out' });
        }
      }
      if (dashboard && !dashboard.hidden) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });
}

function setRole(role) {
  state.role = role;
  document.querySelectorAll('[data-role]').forEach(b => {
    const selected = b.dataset.role === role;
    b.classList.toggle('selected', selected);
    b.setAttribute('aria-pressed', String(selected));
  });
}

// ── Ambient Splash Backdrop ──
function updateBackdrop(championId) {
  const splash = $('#ambient-splash');
  if (!splash) return;
  splash.style.backgroundImage = `url('${getSplashUrl(championId)}')`;
}

// ── Core Dashboard Rendering ──
function renderAnalysis() {
  const a = state.analysis;
  const dashboard = $('#dashboard');
  const wasHidden = dashboard.hidden;
  dashboard.hidden = false;

  // Profile Header
  const heading = $('#player-name');
  heading.replaceChildren(
    document.createTextNode(a.account.gameName),
    el('span', '', ` #${a.account.tagLine}`)
  );

  $('#demo-badge').hidden = !a.demo;
  const avatarEl = $('#avatar');
  const iconId = a.account.profileIconId || (a.matches && a.matches[0] && a.matches[0].profileIcon) || 29;
  const version = (a.catalog && a.catalog.version) || '16.19.1';
  const iconUrl = `https://ddragon.leagueoflegends.com/cdn/${version}/img/profileicon/${iconId}.png`;
  const initials = (a.account.gameName || 'RC').slice(0, 2).toUpperCase();
  avatarEl.innerHTML = `<img src="${iconUrl}" alt="${a.account.gameName}" class="player-avatar-img" onerror="this.onerror=null;this.parentElement.textContent='${initials}'">`;


  $('#sample-description').textContent = a.demo
    ? 'Dados fictícios de demonstração para exibição das recomendações.'
    : `${a.region.toUpperCase()} · ${a.stats.games} partidas ranqueadas válidas de ${a.fetched} analisadas${a.skipped ? ` (${a.skipped} remakes ignorados)` : ''}`;

  $('#analysis-date').textContent = `Atualizado em ${new Date(a.createdAt).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`;

  // Bento Stats
  $('#stat-queue').textContent = a.queue === 420 ? 'Solo / Duo' : 'Flex 5v5';
  $('#stat-wins').textContent = `${a.stats.wins}V - ${a.stats.games - a.stats.wins}D (${number(a.stats.winrate, 0)}%)`;
  $('#stat-role').textContent = roles[a.stats.preferredRole] || 'Variado';
  $('#sample-note').textContent = a.stats.games < 10
    ? 'Amostra inicial · Interprete com cautela'
    : `Baseado em ${a.stats.games} partidas recentes`;

  $('#patch').textContent = `v${a.catalog.version.split('.').slice(0, 2).join('.')}`;

  // Role Distribution
  const bars = $('#role-bars');
  bars.replaceChildren();
  Object.entries(a.stats.roles).sort((x, y) => y[1] - x[1]).forEach(([role, count]) => {
    const bar = el('i');
    bar.style.flexGrow = count;
    bar.title = `${roles[role] || role}: ${count} partidas`;
    bars.append(bar);
  });

  renderHistory();
  renderCatalog();

  // Reveal Dashboard
  if (wasHidden && typeof gsap !== 'undefined') {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!prefersReducedMotion) {
      gsap.fromTo(dashboard, { opacity: 0, y: 25 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' });
      dashboard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  animateStats();
}

// ── Recommendations ──
async function recommendations() {
  const generation = ++state.generation;
  state.limit = 6;
  $('#recommendation-grid').replaceChildren(el('p', 'empty-state-notice', 'Calculando compatibilidade de campeões…'));
  $('#more-button').hidden = true;
  state.recommendations = null;

  try {
    const result = await api(`/api/recommendations/${state.analysis.id}?role=${state.role}`);
    if (generation !== state.generation) return;
    state.recommendations = result;
    renderRecommendations();
  } catch (error) {
    if (generation !== state.generation) return;
    $('#recommendation-grid').replaceChildren(el('p', 'empty-state-notice', error.message));
  }
}

function renderRecommendations() {
  if (!state.recommendations) return;

  const filter = $('#kind-filter').value;
  const items = state.recommendations.items.filter(item => filter === 'all' || item.kind === filter);

  $('#recommendation-note').textContent = `${state.recommendations.sampleSize} partidas analisadas para esta seleção`;

  const grid = $('#recommendation-grid');
  grid.replaceChildren();

  if (!items.length) {
    grid.append(el('p', 'empty-state-notice', state.recommendations.sampleSize
      ? 'Nenhum campeão encontrado para este filtro. Experimente "Todos os Campeões".'
      : state.recommendations.explanation
    ));
    $('#more-button').hidden = true;
    return;
  }

  // Update ambient background with top champion splash art
  if (items[0] && items[0].champion) {
    updateBackdrop(items[0].champion.id);
  }

  items.slice(0, state.limit).forEach((item, index) => {
    const card = el('article', 'rec-champ-card');

    // ── Banner Header ──
    const banner = el('div', 'card-art-banner');
    
    const art = el('img', 'card-art-img');
    art.src = getCenteredSplashUrl(item.champion.id);
    art.alt = item.champion.name;
    art.loading = 'lazy';
    art.addEventListener('error', () => {
      art.src = getSplashUrl(item.champion.id);
    }, { once: true });

    const gradient = el('div', 'card-art-gradient');
    const rankBadge = el('span', 'card-rank-badge', `#${index + 1}`);
    const originBadge = el('span', 'card-origin-badge', item.kind === 'known' ? 'SEU POOL' : 'EXPANSÃO');

    const overlay = el('div', 'card-header-overlay');
    overlay.append(
      el('h4', 'champ-title-line', item.champion.name),
      el('div', 'champ-classes-line', item.champion.tags.map(t => classes[t] || t).join(' · '))
    );

    banner.append(art, gradient, rankBadge, originBadge, overlay);

    // ── Body ──
    const body = el('div', 'card-body-section');

    // Meter
    const meterRow = el('div', 'meter-row');
    const meterScore = el('span', 'meter-score', number(item.score));
    meterScore.append(el('small', '', ' / 100'));
    meterRow.append(el('span', 'meter-label', 'AFINIDADE TÁTICA'), meterScore);

    const progressTrack = el('div', 'slim-progress-track');
    const progressFill = el('div', 'slim-progress-fill');
    progressFill.style.width = '0%';
    progressTrack.append(progressFill);

    // Stats Grid
    const champCurve = item.champion.winrateCurve || item.champion.mastery || state.analysis?.catalog?.champions?.find(c => c.key === item.champion.key)?.winrateCurve;
    const statsGrid = el('div', 'stats-pill-grid');
    [
      ['PARTIDAS', item.games],
      ['WINRATE', item.winrate === null ? '—' : `${number(item.winrate, 0)}%`],
      ['KDA', item.kda === null ? '—' : number(item.kda, 2)],
      ['SUBIDA WR', champCurve ? `~${champCurve.inflectionGames}º j.` : '—']
    ].forEach(([lbl, val]) => {
      const pill = el('div', 'pill-item');
      pill.append(el('span', '', lbl), el('strong', '', String(val)));
      statsGrid.append(pill);
    });

    // Reason
    const reasonText = item.games ? `${item.reasons[0]} ${item.reasons[1] || ''}` : (item.reasons.at(-1) || '');
    const reason = el('p', 'card-reason-text', reasonText);

    // Footer Strip
    const footer = el('div', 'card-actions-strip');
    const detailBtn = el('button', 'card-details-btn', 'Ver análise detalhada →');
    detailBtn.addEventListener('click', () => showChampion(item.champion, item));
    footer.append(el('span', 'confidence-indicator', `Confiança: ${item.confidence}`), detailBtn);

    body.append(meterRow, progressTrack, statsGrid, reason, footer);

    card.append(banner, body);
    grid.append(card);

    // Smooth progress fill
    setTimeout(() => {
      progressFill.style.width = `${Math.min(100, Math.max(0, item.score))}%`;
    }, 40 + index * 50);
  });

  $('#more-button').hidden = items.length <= state.limit;
  animateRecommendations();
}

// ── Winrate Learning Curve & Inflection Point Builder ──
function renderWinrateLearningCurve(champion) {
  const curve = champion.winrateCurve || champion.mastery || state.analysis?.catalog?.champions?.find(c => c.key === champion.key)?.winrateCurve;
  if (!curve) return null;

  const card = el('div', 'winrate-curve-card');
  card.style.setProperty('--curve-accent', curve.tierColor || '#38bdf8');

  // Header row
  const headRow = el('div', 'winrate-head-row');
  const leftCol = el('div', '');
  const title = el('div', 'winrate-main-title');
  title.innerHTML = `Winrate começa a subir a partir do <strong>~${curve.inflectionGames}º jogo</strong>`;
  leftCol.append(
    el('span', 'winrate-card-kicker', 'Curva de Domínio & Taxa de Vitória'),
    title
  );

  const deltaBadge = el('span', 'winrate-delta-badge', `+${curve.winrateDelta}% de ganho de WR`);
  deltaBadge.style.color = curve.tierColor || '#38bdf8';
  deltaBadge.style.borderColor = curve.tierColor || '#38bdf8';
  headRow.append(leftCol, deltaBadge);

  // Description
  const desc = el('p', 'disclaimer-inline',
    `Em média, jogadores com ${champion.name} começam a registrar virada positiva e aumento sustentável na taxa de vitória após ${curve.inflectionGames} partidas.`
  );

  // 4-Stat Summary Grid
  const statsRow = el('div', 'winrate-three-stats');
  const s1 = el('div', 'winrate-stat-box');
  s1.append(
    el('span', 'stat-box-lbl', 'Estreia (1-5 j.)'),
    el('span', 'stat-box-num', `${number(curve.initialWinrate, 1)}%`),
    el('span', 'stat-box-hint', 'Adaptação inicial')
  );

  const s2 = el('div', 'winrate-stat-box highlight-box');
  s2.append(
    el('span', 'stat-box-lbl', `Início da Subida (~${curve.inflectionGames} j.)`),
    el('span', 'stat-box-num', `${number(curve.inflectionWinrate, 1)}%`),
    el('span', 'stat-box-hint', 'Ponto de inflexão')
  );

  const s3 = el('div', 'winrate-stat-box');
  s3.append(
    el('span', 'stat-box-lbl', 'Domínio Tático'),
    el('span', 'stat-box-num', `${number(curve.tacticalWinrate || 55.0, 1)}%`),
    el('span', 'stat-box-hint', 'Consistência tática')
  );

  const s4 = el('div', 'winrate-stat-box');
  s4.append(
    el('span', 'stat-box-lbl', `Teto Especialista (${curve.stabilizationGames}+ j.)`),
    el('span', 'stat-box-num', `${number(curve.masteryWinrate, 1)}%`),
    el('span', 'stat-box-hint', 'Teto 60%+')
  );
  statsRow.append(s1, s2, s3, s4);

  // Trajectory Breakdown Table
  const trajBlock = el('div', 'winrate-trajectory-block');
  trajBlock.append(el('span', 'trajectory-section-title', 'Progressão de Winrate por Faixa de Partidas'));

  const trajTable = el('div', 'trajectory-table');
  (curve.trajectory || []).forEach((step, idx) => {
    const isInflection = idx === 1;
    const row = el('div', `trajectory-row ${isInflection ? 'active-inflection' : ''}`);

    const range = el('span', 'trajectory-range', `${step.range} j.`);
    const info = el('div', 'trajectory-info');
    info.append(
      el('span', 'trajectory-phase-title', `${step.label}${isInflection ? ' ★' : ''}`),
      el('span', 'trajectory-desc', step.desc)
    );
    const wr = el('span', 'trajectory-wr-pill', `${number(step.winrate, 1)}%`);

    row.append(range, info, wr);
    trajTable.append(row);
  });
  trajBlock.append(trajTable);

  // Personal Comparison Box
  const userMatches = (state.analysis?.matches || []).filter(m => m.championId === champion.key);
  const userGames = userMatches.length;
  const userWins = userMatches.filter(m => m.win).length;
  const userWinrate = userGames > 0 ? Math.round((userWins / userGames) * 100) : null;

  const personalBox = el('div', 'personal-winrate-box');
  if (userGames === 0) {
    personalBox.innerHTML = `💡 <strong>Seu histórico:</strong> Nenhuma partida com ${champion.name} na amostra recente. O primeiro salto consistente de vitórias costuma iniciar a partir da <strong>${curve.inflectionGames}ª partida</strong>.`;
  } else if (userGames < curve.inflectionGames) {
    const remaining = curve.inflectionGames - userGames;
    personalBox.innerHTML = `📊 <strong>Seu histórico:</strong> Você jogou <strong>${userGames} partida(s)</strong> (${userWinrate}% WR). Você ainda está na fase de adaptação mecânica inicial. Faltam cerca de <strong>~${remaining} partida(s)</strong> para atingir a subida esperada de taxa de vitória.`;
  } else {
    personalBox.innerHTML = `🔥 <strong>Seu histórico:</strong> Você já jogou <strong>${userGames} partida(s)</strong> (${userWinrate}% WR) com ${champion.name}! Você já superou o ponto de inflexão inicial (${curve.inflectionGames} jogos) e está na fase avançada de domínio.`;
  }

  card.append(headRow, desc, statsRow, trajBlock, personalBox);
  return card;
}
const renderMasterySection = renderWinrateLearningCurve;


// ── Champion Detail Modal ──
function showChampion(champion, item) {
  const body = $('#champion-detail');
  body.replaceChildren();

  // Splash Banner
  const banner = el('div', 'champ-banner-header');
  const splash = el('img', 'champ-banner-img');
  splash.src = getSplashUrl(champion.id);
  splash.alt = champion.name;

  const overlay = el('div', 'champ-banner-overlay');

  const info = el('div', 'champ-banner-info');
  info.append(
    el('h2', 'champ-banner-name', champion.name),
    el('p', 'champ-banner-subtitle', `${champion.title} · ${champion.tags.map(t => classes[t] || t).join(' / ')}`)
  );

  banner.append(splash, overlay, info);
  body.append(banner);

  const mainSection = el('div', 'champ-modal-content');

  if (item) {
    mainSection.append(
      el('p', '', `Rotas no Rift: ${champion.roles.map(r => roles[r]).join(' · ') || 'Sem rota fixa'}`),
      el('p', 'timestamp-text', `Dificuldade oficial Data Dragon: ${champion.difficulty}/10`)
    );
    mainSection.append(el('p', 'meter-score', `${number(item.score)} / 100 de Afinidade`));

    const list = el('ul', 'modal-reasons-list');
    item.reasons.forEach(r => list.append(el('li', '', r)));
    mainSection.append(list);

    const breakdown = el('div', 'score-breakdown-row');
    [
      ['Rota / Posição', item.components.role],
      ['Classes & Estilo', item.components.style],
      ['Desempenho', item.components.performance]
    ].forEach(([lbl, val]) => {
      const box = el('div', 'breakdown-box');
      box.append(el('strong', '', number(val)), el('span', '', lbl));
      breakdown.append(box);
    });
    mainSection.append(breakdown, el('p', 'disclaimer-inline', 'Valores somados na pontuação de afinidade. Não representam garantia de vitória.'));
  } else {
    // Detailed Catalog Information
    const catalogInfo = el('div', 'champ-catalog-details');

    const rolePills = el('div', 'champ-meta-pills');
    champion.roles.forEach(r => {
      rolePills.append(el('span', 'meta-pill', `Rota: ${roles[r] || r}`));
    });
    champion.tags.forEach(t => {
      rolePills.append(el('span', 'meta-pill', `Classe: ${classes[t] || t}`));
    });

    const diffMeter = el('div', 'difficulty-meter');
    const diffTrack = el('div', 'diff-track');
    const diffFill = el('div', 'diff-fill');
    diffFill.style.width = `${Math.min(100, Math.max(10, champion.difficulty * 10))}%`;
    diffTrack.append(diffFill);
    diffMeter.append(
      el('span', 'diff-label', 'Dificuldade Mecânica'),
      diffTrack,
      el('span', 'diff-val', `${champion.difficulty} / 10`)
    );

    const hint = el('p', 'champ-cta-hint', '💡 Para calcular sua pontuação de afinidade tática personalizada com este campeão, faça uma busca com o seu Riot ID acima.');

    catalogInfo.append(rolePills, diffMeter, hint);
    mainSection.append(catalogInfo);
  }

  // Winrate Learning Curve & Inflection Point Card
  const winrateCurveCard = renderWinrateLearningCurve(champion);
  if (winrateCurveCard) {
    mainSection.append(winrateCurveCard);
  }

  body.append(mainSection);

  const dialog = $('#champion-dialog');
  dialog.showModal();

  if (typeof gsap !== 'undefined') {
    const box = dialog.querySelector('.modal-box');
    if (box) {
      gsap.fromTo(box, { scale: 0.94, opacity: 0, y: 15 }, { scale: 1, opacity: 1, y: 0, duration: 0.22, ease: 'power2.out' });
    }
  }
}

// ── Match History ──
function renderHistory() {
  const a = state.analysis;
  if (!a) return;

  const filter = $('#history-filter').value;
  const rows = a.matches.filter(m => filter === 'all' || m.win === (filter === 'win'));
  const body = $('#history-body');
  body.replaceChildren();

  for (const m of rows) {
    const champion = a.catalog.champions.find(c => c.key === m.championId);
    const tr = el('tr');

    const nameTd = el('td', 'table-champ-col');
    if (champion) {
      nameTd.append(portrait(champion, ''));
    }
    nameTd.append(document.createTextNode(champion?.name || m.championName));

    const outcomePill = el('span', `outcome-pill ${m.win ? 'win-outcome' : 'loss-outcome'}`, m.win ? 'VITÓRIA' : 'DERROTA');
    const resTd = el('td');
    resTd.append(outcomePill);

    tr.append(
      nameTd,
      resTd,
      el('td', '', roles[m.role] || 'Indefinida'),
      el('td', '', `${m.kills} / ${m.deaths} / ${m.assists}`),
      el('td', '', number(m.cs / (m.duration / 60))),
      el('td', '', `${Math.floor(m.duration / 60)}m ${m.duration % 60}s`),
      el('td', '', new Date(m.timestamp).toLocaleDateString('pt-BR'))
    );
    body.append(tr);
  }
  $('#history-empty').hidden = rows.length > 0;
}

// ── Champion Catalog ──
function renderCatalog() {
  if (!state.analysis) return;

  const query = $('#champion-search').value.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const grid = $('#catalog-grid');
  grid.replaceChildren();

  const filtered = state.analysis.catalog.champions
    .filter(c => c.name.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '').includes(query))
    .sort((a, b) => a.name.localeCompare(b.name));

  filtered.forEach(c => {
    const card = el('button', 'catalog-item-card');
    card.append(
      portrait(c, ''),
      el('strong', '', c.name),
      el('span', '', c.tags.map(t => classes[t] || t).join(' / '))
    );
    const curve = c.winrateCurve || c.mastery;
    if (curve) {
      const tag = el('span', 'catalog-mastery-tag', `WR sobe no ~${curve.inflectionGames}º jogo (+${curve.winrateDelta}%)`);
      tag.style.color = curve.tierColor || '#38bdf8';
      card.append(tag);
    }
    card.addEventListener('click', () => showChampion(c));
    grid.append(card);
  });

  if (!filtered.length) {
    grid.append(el('p', 'empty-state-notice', 'Nenhum campeão encontrado para essa busca.'));
  } else {
    animateCatalog();
  }
}

// ── Load Analysis Pipeline ──
async function loadAnalysis(demo = false, body = null) {
  clearError();
  loading(true, demo ? 'Carregando dados da demonstração…' : undefined);

  try {
    const analysis = await api(
      demo ? '/api/analyses/demo' : '/api/analyses',
      demo ? {} : { method: 'POST', body: JSON.stringify(body) }
    );
    state.analysis = analysis;
    setRole('ALL');
    $('#kind-filter').value = 'all';
    $('#history-filter').value = 'all';
    showTab('recommendations');
    renderAnalysis();
    await recommendations();
  } catch (error) {
    showError(error.message + (state.analysis ? ' (A análise anterior continua visível abaixo).' : ''));
  } finally {
    loading(false);
  }
}

// ═══════════════════════════════════════════════════════════
// REFINED GSAP ANIMATIONS
// ═══════════════════════════════════════════════════════════

function initHeroAnimations() {
  if (typeof gsap === 'undefined') return;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;

  gsap.fromTo(['#hero-title', '#hero-desc', '#search-card'],
    { opacity: 0, y: 15 },
    { opacity: 1, y: 0, duration: 0.45, stagger: 0.08, ease: 'power2.out' }
  );
}

function animateStats() {
  if (typeof gsap === 'undefined') return;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;

  const a = state.analysis;
  if (!a || !a.stats) return;

  gsap.fromTo('.bento-card',
    { opacity: 0, y: 12 },
    { opacity: 1, y: 0, stagger: 0.06, duration: 0.4, ease: 'power2.out' }
  );

  const statsToCount = [
    { selector: '#stat-games', end: a.stats.games, format: v => String(Math.round(v)) },
    { selector: '#stat-winrate', end: a.stats.winrate, format: v => `${number(v, 1)}%` },
    { selector: '#stat-kda', end: a.stats.kda, format: v => number(v, 2) }
  ];

  statsToCount.forEach(item => {
    const elNode = $(item.selector);
    if (!elNode || typeof item.end !== 'number') return;

    const proxy = { val: 0 };
    gsap.to(proxy, {
      val: item.end,
      duration: 0.9,
      ease: 'power2.out',
      onUpdate: () => {
        elNode.textContent = item.format(proxy.val);
      }
    });
  });
}

function animateRecommendations() {
  if (typeof gsap === 'undefined') return;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;

  gsap.fromTo('.rec-champ-card',
    { opacity: 0, y: 15 },
    { opacity: 1, y: 0, stagger: 0.05, duration: 0.35, ease: 'power2.out' }
  );
}

function animateCatalog() {
  if (typeof gsap === 'undefined') return;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReducedMotion) return;

  gsap.fromTo('.catalog-item-card',
    { opacity: 0, scale: 0.96 },
    { opacity: 1, scale: 1, stagger: 0.015, duration: 0.25, ease: 'power1.out' }
  );
}

// ═══════════════════════════════════════════════════════════
// LISTENERS & BOOT
// ═══════════════════════════════════════════════════════════

$('#search-form').addEventListener('submit', event => {
  event.preventDefault();
  if (state.busy) return;
  const body = {
    gameName: $('#game-name').value.trim(),
    tagLine: $('#tag-line').value.trim().replace(/^#/, ''),
    region: $('#region').value,
    queue: Number($('#queue').value),
    count: Number($('#count').value)
  };
  if (!body.gameName || !body.tagLine) {
    showError('Preencha o Riot ID e a Tag do invocador.');
    return;
  }
  loadAnalysis(false, body);
});

$('#demo-button').addEventListener('click', () => loadAnalysis(true));

document.querySelectorAll('[data-tab]').forEach(b => {
  b.addEventListener('click', () => showTab(b.dataset.tab));
});

document.querySelectorAll('[data-role]').forEach(b => {
  b.addEventListener('click', () => {
    setRole(b.dataset.role);
    recommendations();
  });
});

$('#kind-filter').addEventListener('change', () => {
  state.limit = 6;
  renderRecommendations();
});

$('#more-button').addEventListener('click', () => {
  state.limit += 6;
  renderRecommendations();
});

$('#history-filter').addEventListener('change', renderHistory);
$('#champion-search').addEventListener('input', renderCatalog);

for (const id of ['method-button', 'method-detail-button']) {
  const btn = $(`#${id}`);
  if (btn) {
    btn.addEventListener('click', () => {
      showTab('methodology');
      const panel = $('#methodology-panel');
      if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
}

document.querySelectorAll('[data-close]').forEach(b => {
  b.addEventListener('click', () => {
    const dialog = $(`#${b.dataset.close}`);
    if (dialog) dialog.close();
  });
});

document.querySelectorAll('dialog:not(#login-dialog)').forEach(d => {
  d.addEventListener('click', e => {
    if (e.target === d) {
      const rect = d.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
        d.close();
      }
    }
  });
});

$('#login-dialog').addEventListener('cancel', e => e.preventDefault());

$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({
        username: $('#username').value,
        password: $('#password').value
      })
    });
    $('#password').value = '';
    $('#login-error').textContent = '';
    $('#login-dialog').close();
    $('#logout').hidden = false;
    await loadAnalysis(true);
  } catch (error) {
    $('#login-error').textContent = error.message;
  }
});

$('#logout').addEventListener('click', async () => {
  try {
    await api('/api/logout', { method: 'POST' });
    state.analysis = null;
    state.recommendations = null;
    state.generation++;
    $('#dashboard').hidden = true;
    $('#logout').hidden = true;
    $('#login-dialog').showModal();
  } catch (error) {
    showError(error.message);
  }
});

// Boot entrypoint
(async () => {
  updateBackdrop('Jinx');
  initHeroAnimations();

  try {
    const session = await api('/api/session');
    $('#logout').hidden = !session.authEnabled || !session.authenticated;
    if (!session.authenticated) {
      $('#login-dialog').showModal();
      return;
    }
    // Auto-load demo on initial view for instant preview
    await loadAnalysis(true);
  } catch (error) {
    showError(error.message);
  }
})();
