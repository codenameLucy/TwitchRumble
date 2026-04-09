// ── TYPE COLOURS ──
const TYPE_COLORS = {
  Fire:'#ff6b35',Water:'#3a9bd5',Grass:'#5bba6f',Electric:'#f5c400',
  Ice:'#74d7ec',Fighting:'#c0392b',Poison:'#9b59b6',Ground:'#c8a96e',
  Flying:'#8ecae6',Psychic:'#ff6fa8',Bug:'#8bc34a',Rock:'#a0845c',
  Ghost:'#7c5cbf',Dragon:'#2980b9',Dark:'#34495e',Steel:'#90a4ae',
  Fairy:'#f48fb1',Normal:'#9e9e9e'
};
function typeColor(t) { return TYPE_COLORS[t] || '#888'; }
function contrastColor(hex) {
  const r=parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
  return (0.299*r+0.587*g+0.114*b) > 150 ? '#000' : '#fff';
}

// ── HELPERS ──
const $ = id => document.getElementById(id);
const circumference = 2 * Math.PI * 50; // r=50
$('timer-arc').style.strokeDasharray = circumference;

let timerInterval = null;
let currentTimer = 0;
let maxTimer = 20;

function setTimer(seconds) {
  clearInterval(timerInterval);
  currentTimer = seconds;
  maxTimer = seconds;
  updateTimerArc();
  timerInterval = setInterval(() => {
    currentTimer--;
    updateTimerArc();
    if (currentTimer <= 0) clearInterval(timerInterval);
  }, 1000);
}

function updateTimerArc() {
  const pct = Math.max(0, currentTimer / maxTimer);
  const offset = circumference * (1 - pct);
  $('timer-arc').style.strokeDashoffset = offset;
  $('timer-text').textContent = currentTimer > 0 ? currentTimer : '—';
  $('timer-arc').style.stroke = pct < 0.25 ? '#e63946' : '#f5c400';
}

function setHp(idx, hp, maxHp) {
  const pct = Math.max(0, hp / maxHp * 100);
  $(`hp${idx}-val`).textContent = hp;
  $(`hp${idx}-max`).textContent = maxHp;
  const bar = $(`hp${idx}-bar`);
  bar.style.width = pct + '%';
  if (pct < 10)      bar.style.background = '#e63946';
  else if (pct < 25) bar.style.background = '#f5c400';
  else               bar.style.background = idx === 1 ? '#e63946' : '#457bff';
}

function buildMoves(idx, moves) {
  const list = $(`moves${idx}`);
  list.innerHTML = '';
  moves.forEach((m, i) => {
    const row = document.createElement('div');
    row.className = 'move-row';
    row.id = `move${idx}-${i}`;
    const col = typeColor(m.type);
    row.innerHTML = `
      <span class="move-num">${i+1}</span>
      <span class="move-type-dot" style="background:${col}"></span>
      <span class="move-name">${m.name}</span>
      <span class="move-power">${m.power}pw</span>
    `;
    list.appendChild(row);
  });
}

function setType(idx, type) {
  const el = $(`type${idx}`);
  const col = typeColor(type);
  el.textContent = type.toUpperCase();
  el.style.background = col;
  el.style.color = contrastColor(col);
}

function highlightMove(idx, moveIdx) {
  for (let i = 0; i < 4; i++) {
    const el = $(`move${idx}-${i}`);
    if (el) el.classList.remove('selected');
  }
  const sel = $(`move${idx}-${moveIdx}`);
  if (sel) sel.classList.add('selected');
}

function showAnnouncement(text, duration = 3000) {
  const el = $('announcement');
  el.textContent = text;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

function showEffectiveness(text, color, duration = 2000) {
  const el = $('eff-flash');
  el.textContent = text;
  el.style.color = color;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

function updateIdleQueue(queue) {
  if (queue.length === 0) {
    $('idle-queue').innerHTML = 'Waiting for fighters…';
  } else if (queue.length === 1) {
    $('idle-queue').innerHTML = `<span>${queue[0]}</span> is in the ring — waiting for opponent…`;
  } else {
    $('idle-queue').innerHTML = `<span>${queue[0]}</span> vs <span>${queue[1]}</span> — GET READY!`;
  }
}

function showScreen(name) {
  $('idle').style.display = 'none';
  $('fight').style.display = 'none';
  if (name === 'idle') $('idle').style.display = 'flex';
  if (name === 'fight') $('fight').style.display = 'block';
}

// ── WEBSOCKET ──
function connect() {
  const ws = new WebSocket('ws://localhost:8765');

  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    console.log('[WS]', msg.event, msg);
    handleEvent(msg);
  };

  ws.onclose = () => {
    console.warn('WS closed, reconnecting…');
    setTimeout(connect, 2000);
  };
}

function handleEvent(msg) {
  switch (msg.event) {

    case 'queue_update':
      updateIdleQueue(msg.queue);
      break;

    case 'fight_start': {
      const f1 = msg.fighter1, f2 = msg.fighter2;

      $('name1').textContent = f1.name;
      $('name2').textContent = f2.name;
      setType(1, f1.type);
      setType(2, f2.type);
      setHp(1, f1.hp, f1.max_hp);
      setHp(2, f2.hp, f2.max_hp);
      buildMoves(1, f1.moves);
      buildMoves(2, f2.moves);

      // Avatars — fall back to a placeholder silhouette if no URL
      const PLACEHOLDER = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="35" r="22" fill="%23555"/><ellipse cx="50" cy="85" rx="32" ry="22" fill="%23555"/></svg>';
      $('avatar1').src = f1.avatar || PLACEHOLDER;
      $('avatar2').src = f2.avatar || PLACEHOLDER;
      $('avatar1').classList.remove('ko');
      $('avatar2').classList.remove('ko');

      // Type-coloured glow rings
      const col1 = typeColor(f1.type), col2 = typeColor(f2.type);
      $('avatar-ring1').style.borderColor = col1;
      $('avatar-ring1').style.boxShadow = `0 0 24px 6px ${col1}66, inset 0 0 16px ${col1}33`;
      $('avatar-ring2').style.borderColor = col2;
      $('avatar-ring2').style.boxShadow = `0 0 24px 6px ${col2}66, inset 0 0 16px ${col2}33`;

      // Re-trigger entrance animations
      ['avatar-wrap1', 'avatar-wrap2'].forEach(id => {
        const el = $(id);
        el.style.animation = 'none';
        el.offsetHeight; // force reflow
        el.style.animation = '';
      });

      $('vs-splash').style.display = 'none';
      $('winner-splash').style.display = 'none';
      showScreen('fight');

      const vs = $('vs-splash');
      vs.style.display = 'flex';
      setTimeout(() => vs.style.display = 'none', 2500);
      break;
    }

    case 'round_start':
      $('round-label').textContent = `ROUND ${msg.round}`;
      setTimer(msg.timer);
      for (let i = 0; i < 4; i++) {
        const a = $(`move1-${i}`), b = $(`move2-${i}`);
        if (a) a.classList.remove('selected');
        if (b) b.classList.remove('selected');
      }
      showAnnouncement(`⚔️  ROUND ${msg.round} — Choose your move! (1–4)`, 3000);
      break;

    case 'round_result': {
      clearInterval(timerInterval);
      const f1 = msg.fighter1, f2 = msg.fighter2;

      highlightMove(1, f1.move_used);
      highlightMove(2, f2.move_used);
      setHp(1, f1.hp, f1.max_hp);
      setHp(2, f2.hp, f2.max_hp);

      const eff1 = f1.effectiveness, eff2 = f2.effectiveness;
      let effText = '', effColor = '#f5c400';
      if (eff1 === 0 || eff2 === 0) {
        effText = "It had no effect!"; effColor = '#6b6b7e';
      } else if (eff1 === 2.0 && eff2 === 2.0) {
        effText = "🔥 Both super effective!"; effColor = '#ff6b35';
      } else if (eff1 === 2.0) {
        effText = `⚡ ${f1.name}'s move is SUPER EFFECTIVE!`; effColor = '#ff6b35';
      } else if (eff2 === 2.0) {
        effText = `⚡ ${f2.name}'s move is SUPER EFFECTIVE!`; effColor = '#ff6b35';
      } else if (eff1 === 0.5 || eff2 === 0.5) {
        effText = "Not very effective…"; effColor = '#9e9e9e';
      }

      if (effText) showEffectiveness(effText, effColor, 3000);

      const m1 = f1.moves[f1.move_used], m2 = f2.moves[f2.move_used];
      setTimeout(() => {
        showAnnouncement(
          `${f1.name} used ${m1.name} (−${f1.damage_dealt}) | ${f2.name} used ${m2.name} (−${f2.damage_dealt})`,
          3500
        );
      }, 400);
      break;
    }

    case 'fight_end': {
      clearInterval(timerInterval);
      $('timer-text').textContent = '—';

      // Greyscale the loser's portrait
      if (msg.winner === msg.fighter1.name) {
        $('avatar2').classList.add('ko');
      } else if (msg.winner === msg.fighter2.name) {
        $('avatar1').classList.add('ko');
      } else {
        $('avatar1').classList.add('ko');
        $('avatar2').classList.add('ko');
      }

      const ws = $('winner-splash');
      if (msg.winner) {
        $('winner-name').textContent = msg.winner;
      } else {
        $('winner-name').textContent = 'DRAW';
        ws.querySelector('.ko-text').textContent = 'DRAW!';
        ws.querySelector('.winner-sub').textContent = 'Nobody wins!';
      }
      ws.style.display = 'flex';

      setTimeout(() => {
        ws.style.display = 'none';
        showScreen('idle');
        updateIdleQueue([]);
      }, 8000);
      break;
    }
  }
}

showScreen('idle');
connect();