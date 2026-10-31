(() => {
  if (globalThis.__aiHlidac) return;
  globalThis.__aiHlidac = true;
  const selector = '#messageBody, [data-message], [data-message-id], [role="listitem"], p, li, blockquote, td';
  let currentStatus = 'Kontrola se spouští.', statusState = 'busy', fontsLoaded = false;
  const issues = new Map();
  let active = false, running = false, timer, heartbeat, observer, host, ui, generation = 0;
  let processed = new WeakMap(), warnings = new Map(), checked = 0, skipped = 0, previews = false;  // previews: the page lists message previews (see clippedLine)
  let imageProcessed = new WeakMap(), lastImageScan = 0, pageSignature = '', pageWarning = null;
  let attachmentSeen = new WeakMap(), attachmentSource = new WeakMap();  // warned element -> file name, -> the element that names it
  const dismissed = new WeakMap();
  const styles = new WeakMap();
  let linkProcessed = new WeakMap(), linkEvidence = new WeakMap(), linksChecked = 0, lastLinkRefresh = 0;
  const send = message => chrome.runtime.sendMessage(message);
  // The text the models read. Filler a reader does not see (runs of spaces, zero-width characters) is dropped, and the
  // screener reads up to 20 000 characters in chunks, so padding cannot push a scam out of the check. A longer text
  // keeps its beginning and its end.
  function clip(text) {
    const squeezed = text.replace(/[\u200b-\u200d\u2060\ufeff\u00ad]/g, '').replace(/[^\S\n]{2,}/g, ' ').replace(/\n\s*\n\s*/g, '\n\n');
    return squeezed.length <= 20000 ? squeezed : squeezed.slice(0, 10000) + '\n…\n' + squeezed.slice(-10000);
  }
  const LINK_TARGETS = false;  // only a verifier trained with "[odkaz: host]" marks reads them well
  // Two stages: the fast screener flags a text at once ("pending"), the verifier then confirms it or takes it back.
  const verifyQueue = [], quiet = new Map();  // quiet: weak screener flags, verified without a provisional card
  // Reasons are written only when nothing waits for a verdict: every warning on the page shows first, then the reasons.
  const explainQueue = [];
  const unitParts = new Map();  // merged unit (a chat, a feed) -> the single messages it was built from
  const splitUnits = new Map();  // confirmed unit split into posts -> its text, verified result and the posts
  const widened = new WeakSet();  // texts read again with their surrounding messages (widen)
  let verifying = false;
  const pendingCount = () => [...warnings.values()].filter(entry => entry.pending).length;
  const dangerCount = () => [...warnings.values()].filter(entry => entry.danger).length;
  const messages = n => n === 1 ? 'podezřelou zprávu' : n < 5 ? 'podezřelé zprávy' : 'podezřelých zpráv';
  function status(text, state) {
    currentStatus = text; statusState = state || 'busy';
    if (!ui) return;
    ui.getElementById('status').textContent = text;
    const pill = ui.getElementById('fold');
    pill.dataset.state = statusState;
  }
  function okStatus() {
    if (issues.size) { status([...issues.values()][0], 'error'); return; }
    // A near-certain scam turns the pill red even while other messages are still being checked.
    const danger = dangerCount();
    if (danger) { status(danger === 1 ? 'Nebezpečí: podvod · zobrazit' : `Nebezpečí: ${danger} ${danger < 5 ? 'podvody' : 'podvodů'} · zobrazit`, 'danger'); return; }
    const pending = pendingCount();
    if (pending) { status(`Ověřuji ${pending} ${messages(pending)}…`, 'warning'); return; }
    // Weak screener flags are verified quietly; they do not change the status either.
    if (warnings.size) status(warnings.size === 1 ? 'Pozor: 1 upozornění · zobrazit' : `Pozor: ${warnings.size} upozornění · zobrazit`, 'warning');
    else if (skipped) status(`Část obsahu vynechána · ${skipped}`, 'busy');
    else status((checked ? `Kontrola běží · zkontrolováno ${checked}` : 'Kontrola běží') + (previews ? ' · náhledy zpráv zkontroluji po otevření' : ''), 'ok');
  }
  function visible(el) {
    const box = el.getBoundingClientRect(), style = getComputedStyle(el);
    return box.width > 0 && box.height > 0 && box.bottom >= 0 && box.top <= innerHeight && style.visibility !== 'hidden' && style.display !== 'none';
  }
  function textOf(el) {
    // Webmail (e.g. Horde/IMP) renders HTML e-mails in a same-origin iframe; its text is not part of innerText.
    let raw = el.innerText || '';
    let root = el;
    if (el.tagName === 'IFRAME') { try { root = el.contentDocument?.body; raw = root?.innerText || ''; } catch { raw = ''; root = null; } }
    if (root && raw.length > 1000) raw = withoutHidden(raw, root);
    raw = unforged(raw);
    if (LINK_TARGETS && root) {
      raw = withLinkTargets(raw, root);
      const sender = senderDomain(el);
      if (sender && raw.trim().length >= 25) raw = `[odesílatel: ${sender}] ${raw}`;
    }
    return raw.trim().replace(/\s+/g, ' ');
  }
  // Text a reader cannot see (tiny, transparent, the colour of its background, off the page) is still in innerText.
  // A scammer can pad a message with it to dilute the scam, so it is left out. Only long texts are looked at, and a
  // text without such parts stays exactly as it was.
  const hiddenCache = new WeakMap();  // root -> [innerText, text without hidden parts]
  function withoutHidden(raw, root) {
    const cached = hiddenCache.get(root);
    if (cached && cached[0] === raw) return cached[1];
    const view = root.ownerDocument.defaultView, hidden = [];
    for (const el of root.querySelectorAll('*')) {
      if (hidden.some(h => h.contains(el)) || !el.textContent.trim()) continue;
      if (hiddenStyle(el, view)) hidden.push(el);
    }
    let text = raw;
    for (const el of hidden) { const part = el.innerText; if (part && part.trim()) text = text.replace(part, ' '); }
    hiddenCache.set(root, [raw, text]);
    return text;
  }
  function hiddenStyle(el, view) {
    const style = view.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;  // not in innerText anyway
    if (parseFloat(style.fontSize) < 4 || parseFloat(style.opacity) < 0.1) return true;
    const box = el.getBoundingClientRect();
    if ((box.width < 2 || box.height < 2) && style.overflow !== 'visible') return true;
    if (box.right + view.scrollX < 0 || box.bottom + view.scrollY < 0) return true;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;  // colour matters for own text only
    const transparent = c => c === 'transparent' || /rgba\(.*,\s*0\)$/.test(c);
    if (transparent(style.color)) return true;
    for (let up = el; up; up = up.parentElement) {
      const upStyle = view.getComputedStyle(up);
      if (upStyle.backgroundImage !== 'none') return false;  // text over a picture
      if (!transparent(upStyle.backgroundColor)) return upStyle.backgroundColor === style.color;
    }
    return style.color === 'rgb(255, 255, 255)';  // no background set anywhere: the page is white
  }
  // Our marks are facts from the page; the same words typed into the message by its author are not.
  function unforged(text) { return text.replace(/\[(odkaz|odes[ií]latel)\s*:/gi, '($1:'); }
  // Mail and social sites wrap links in their own redirect; the hostname that matters is the one inside. Only these
  // known wrappers are opened: an unknown "?u=https://kb.cz" could hide a scam host behind a real one.
  const WRAPPERS = [[/(^|\.)safelinks\.protection\.outlook\.com$/, '', 'url'], [/^(www\.)?google\.[a-z.]+$/, '/url', 'q'],
    [/^(l|lm)\.facebook\.com$/, '/l.php', 'u'], [/^l\.instagram\.com$/, '', 'u']];
  function realTarget(href) {
    let url = new URL(href);
    for (let depth = 0; depth < 3; depth++) {
      const wrap = WRAPPERS.find(([host, path]) => host.test(url.hostname) && (!path || url.pathname === path));
      const defense = /^urldefense\.(com|proofpoint\.com)$/.test(url.hostname) && url.pathname.match(/^\/v3\/__(.+?)__/);
      const inner = wrap ? url.searchParams.get(wrap[2]) : defense ? defense[1] : null;
      if (!inner) break;
      try { url = new URL(inner); } catch { break; }
      if (!/^https?:$/.test(url.protocol)) break;
    }
    return url;
  }
  // "Klikněte zde [odkaz: example.top]": the verifier sees where a link leads, not only its text. Only the hostname,
  // never the path or query (they can carry personal tokens).
  function withLinkTargets(raw, root) {
    let out = '', from = 0;
    for (const a of [...root.querySelectorAll('a[href]')].slice(0, 12)) {
      let target;
      try { target = realTarget(a.href); } catch { continue; }
      if (!/^https?:$/.test(target.protocol)) continue;
      const label = unforged((a.innerText || '').trim()), host = target.hostname.replace(/^www\./, '');
      if (!label || label.toLowerCase().includes(host)) continue;
      const at = raw.indexOf(label, from);
      if (at < 0) continue;
      out += raw.slice(from, at + label.length) + ` [odkaz: ${target.hostname}]`;
      from = at + label.length;
    }
    return out + raw.slice(from);
  }
  // The sender's address as the mail client shows it in the message header (an attribute the author cannot write),
  // the domain only. Addresses inside the message itself never count.
  function senderDomain(el) {
    let header = el.parentElement;
    for (let up = 0; header && up < 6; up++, header = header.parentElement) {
      const found = [...header.querySelectorAll('[email], [data-hovercard-id*="@"]')].find(n => !el.contains(n) && (n.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
      const address = found && (found.getAttribute('email') || found.getAttribute('data-hovercard-id'));
      const domain = address && address.trim().toLowerCase().match(/@([a-z0-9.-]+\.[a-z]{2,})$/);
      if (domain) return domain[1];
    }
    return '';
  }
  function hasMessageContext(el) {
    // Horde/IMP: the list and collapsed headers contain subjects, not messages.
    // A hidden/empty preview is not permission to classify the surrounding UI.
    // Detect the layout, not a trusted sender or a particular university domain.
    if (document.querySelector('#msgHeadersTable') && document.querySelector('#messageBody')) {
      return Boolean(el.closest('#messageBody'));
    }
    return true;
  }
  // Too little to judge (a sender line, a name and an address): leave it alone. Addresses and links are not words;
  // links are checked on their own. The shortest real scams we know have four words ("Ahoj mami, mám nové číslo").
  const ADDRESS=/\S+@\S+|(?:https?:\/\/|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:cz|com|sk|eu|net|org|info|io|me|app|ly)\b\S*/gi;
  function words(text) { return (text.replace(ADDRESS,' ').match(/\p{L}{2,}/gu) || []).length; }
  // A message shown only as one clipped line ("Toto je kopie bezpečnostního upozornění…") is a preview, as in the
  // message lists of webmail and chat apps: a cut-off piece of a message, too little to judge. The full message is
  // read once it is opened. Layout only, no site or sender rules. Applied to whole units (after neighbouring texts
  // are merged), and only when the unit really is one line high: a message styled the same way line by line, or
  // broken into lines inside one clipped box, is several lines high and is checked as usual.
  function clippedLine(el) {
    const style = getComputedStyle(el);
    if (!/^(nowrap|pre)$/.test(style.whiteSpace)) return false;  // inherited: the text itself does not wrap
    const line = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
    if (el.getBoundingClientRect().height >= 1.8 * line) return false;
    for (let e = el, up = 0; e && e !== document.body && up < 4; e = e.parentElement, up++) {
      if (/hidden|clip/.test(getComputedStyle(e).overflowX)) return true;
    }
    return false;
  }
  // A row of a message list (sender, subject and a cut-off piece of the message, as in Gmail or Outlook): a short row
  // (at most 90 px, about four lines) next to at least two other short rows of the same kind, with most of its text in
  // clipped single lines. A message laid out in no-wrap lines on its own (not in a list) is checked as usual.
  const ROW = 90;
  function previewRow(el) {
    const short = e => { const h = e.getBoundingClientRect().height; return h > 0 && h <= ROW; };
    const total = textOf(el).length;
    if (!total || !short(el) || !el.parentElement) return false;
    if ([...el.parentElement.children].filter(o => o !== el && o.tagName === el.tagName && short(o)).length < 2) return false;
    let clipped = 0;
    const counted = [];
    for (const part of el.querySelectorAll('*')) {
      if (counted.some(c => c.contains(part)) || !part.getBoundingClientRect().height || !clippedLine(part)) continue;
      counted.push(part);
      clipped += (part.innerText || '').length;
    }
    return clipped >= total / 2;
  }
  function eligible(el) {
    return el.isConnected && !el.closest('ai-hlidac-panel, input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], nav, script, style, [hidden]') && visible(el);
  }
  const ALERT_ICON = '<svg viewBox="0 0 44 44" aria-hidden="true"><path d="M22 3L42 39H2z" fill="#ffc629" stroke="#18212b" stroke-width="3.5" stroke-linejoin="round"/><path d="M22 16v11" stroke="#18212b" stroke-width="4" stroke-linecap="round"/><circle cx="22" cy="33" r="2.4" fill="#18212b"/></svg>';
  const DANGER_ICON = '<svg viewBox="0 0 44 44" aria-hidden="true"><path d="M22 3L42 39H2z" fill="#c8102e" stroke="#18212b" stroke-width="3.5" stroke-linejoin="round"/><path d="M22 16v11" stroke="#fff" stroke-width="4" stroke-linecap="round"/><circle cx="22" cy="33" r="2.4" fill="#fff"/></svg>';
  const SHIELD_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.2" fill="none" stroke="currentColor" stroke-width="2.6"/><path d="M14.6 14.6L20 20" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>';
  function loadFont() {
    if (fontsLoaded) return;
    fontsLoaded = true;
    // FontFace avoids inserting nodes into the page; the font file ships with the extension.
    for (const [weight, file] of [[400, 'ahn-latin-400'], [700, 'ahn-latin-700'], [400, 'ahn-latin-ext-400'], [700, 'ahn-latin-ext-700']]) {
      const face = new FontFace('Hlidac Sans', `url(${chrome.runtime.getURL(`fonts/${file}.woff2`)})`, {weight: String(weight), unicodeRange: file.includes('ext') ? 'U+0100-024F' : 'U+0000-00FF,U+2000-206F'});
      document.fonts.add(face); face.load().catch(() => {});
    }
  }
  // An orphaned copy (after an extension update) has no connection left; sendMessage would throw synchronously.
  function report() { if (chrome.runtime?.id) send({type: 'count', n: warnings.size, danger: dangerCount() > 0}).catch(() => {}); }
  function resetOutline(el) {
    const old = styles.get(el);
    if (old) { el.style.outline = old.outline; el.style.outlineOffset = old.offset; styles.delete(el); }
  }
  function removeWarning(el) {
    const entry = warnings.get(el);
    if (!entry) return;
    entry.card.remove(); entry.tag.remove(); warnings.delete(el); resetOutline(el); limitCards();
    if (!warnings.size && ui) { ui.getElementById('details').hidden = true; ui.getElementById('fold').setAttribute('aria-expanded', 'false'); okStatus(); }
    report();
  }
  function placeTags() {
    if (!ui) return;
    for (const [el, {tag}] of warnings) {
      const r = el.getBoundingClientRect();
      const shown = el.isConnected && r.bottom > 0 && r.top < innerHeight && r.width > 0;
      tag.hidden = !shown;
      if (shown) { tag.style.top = `${Math.max(4, r.top - 16)}px`; tag.style.left = `${Math.max(4, Math.min(r.left, innerWidth - 170))}px`; }
    }
  }
  let placing = false;
  function queuePlace() { if (placing || !warnings.size) return; placing = true; requestAnimationFrame(() => { placing = false; placeTags(); }); }
  function make(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text) node.textContent = text; return node; }
  // Cards start collapsed to their title; details open only for the card the user asks about.
  function expand(card, show) {
    for (const other of ui.querySelectorAll('#warnings .warning')) {
      const on = other === card && show;
      other.classList.toggle('open', on);
      other.querySelector('.summary').setAttribute('aria-expanded', String(on));
      other.querySelector('.body').hidden = !on;
    }
  }
  // Many warnings would fill the screen: the dock lists the newest few and folds the rest behind one button.
  const SHOWN = 3;
  let showAll = false;
  function limitCards() {
    if (!ui) return;
    const cards = [...ui.querySelectorAll('#warnings .warning')], more = ui.getElementById('more');
    cards.forEach((card, i) => { card.hidden = !showAll && i >= SHOWN && !card.classList.contains('open'); });
    const folded = cards.filter(card => card.hidden).length;
    more.hidden = !folded;
    more.textContent = folded === 1 ? '+ 1 další upozornění' : `+ ${folded} další upozornění`;
  }
  function reveal(card) {
    card.hidden = false;
    open(true); expand(card, true); card.scrollIntoView({block: 'nearest'}); card.querySelector('.primary').focus();
  }
  // Would an outline `d` px outside el be seen? Web apps put message bodies flush against scrolling panes (which clip it)
  // or under neighbouring blocks (which paint over it); then the outline is drawn inside the element instead.
  function outsideVisible(el, d) {
    const r = el.getBoundingClientRect(), x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
    const ring = [[r.left - d + 1, y], [r.right + d - 1, y], [x, r.top - d + 1], [x, r.bottom + d - 1]];
    const clips = [];
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (getComputedStyle(a).overflow !== 'visible') clips.push(a.getBoundingClientRect());
    }
    return ring.every(([px, py]) => {
      if (clips.some(c => px < c.left || px > c.right || py < c.top || py > c.bottom)) return false;
      if (px < 0 || py < 0 || px >= innerWidth || py >= innerHeight) return true;  // off screen: nothing to judge
      const hit = document.elementFromPoint(px, py);
      return !hit || hit.contains(el);
    });
  }
  function warning(el, text, result, quoted) {
    if (dismissed.get(el) === text) return;
    const replacing = warnings.has(el), wasOpen = replacing && warnings.get(el).card.classList.contains('open');
    // Replacing the only card empties the dock for a moment, which folds it: an open dock stays open.
    const dockOpen = replacing && !ui.getElementById('details').hidden;
    removeWarning(el);
    styles.set(el, {outline: el.style.outline, offset: el.style.outlineOffset});
    const pending = result.status === 'pending';
    // Red: the verifier is near-certain (verifier.py DANGER). Orange: a possible scam, or a link or page check.
    const danger = result.level === 'danger', icon = danger ? DANGER_ICON : ALERT_ICON;
    el.style.outline = `${danger ? 4 : 3}px ${pending ? 'dashed' : 'solid'} ${danger ? '#c8102e' : '#e0a100'}`;
    el.style.outlineOffset = outsideVisible(el, danger ? 8 : 7) ? '4px' : `-${danger ? 4 : 3}px`;
    const card = make('section', pending ? 'warning pending' : danger ? 'warning danger' : 'warning');
    if (replacing) card.style.animation = 'none';  // the verified card replaces the pending one in place
    const head = make('button', 'summary'); head.innerHTML = icon;
    // Collapsed rows quote the start of the message, so the user can tell which one on the page it is.
    // Red cards drop the hedge: "Možné vydírání" -> "Vydírání".
    const title = danger ? result.title.replace(/^Možn[ýáé] (\S)/, (_, c) => c.toUpperCase()) : result.title;
    const label = make('span', 'label'); label.append(make('h2', '', title), make('span', 'snippet', (quoted || text).slice(0, 70) + ((quoted || text).length > 70 ? '…' : '')));
    head.append(label, make('span', 'more', 'Podrobnosti'));
    head.onclick = () => expand(card, !card.classList.contains('open'));
    const body = make('div', 'body');
    // Links, login forms and images name what was checked; for message text the outline on the page shows it.
    const quote = quoted ? make('blockquote', '', quoted.slice(0, 160) + (quoted.length > 160 ? '…' : '')) : null;
    const why = make('p', 'why', result.message);
    const advice = make('div', 'advice'); advice.append(make('b', '', 'Co teď udělat'), make('p', '', result.advice));
    const actions = make('div', 'actions');
    const focus = make('button', 'primary', result.source==='local_link_check' ? 'Ukázat odkaz na stránce' : 'Ukázat zprávu na stránce');
    focus.onclick = () => el.scrollIntoView({behavior: 'smooth', block: 'center'});
    const close = make('button', 'secondary', 'Rozumím, skrýt');
    close.onclick = () => { dismissed.set(el, text); removeWarning(el); };
    actions.append(focus, close);
    if (result.source==='local_link_check') {
      const checkedHref=el.href;
      const proceed=make('button','secondary','Přesto otevřít odkaz');
      proceed.onclick=()=>{
        if(!active || !el.isConnected || el.href!==checkedHref){schedule();return;}
        const url=new URL(checkedHref);
        if(['http:','https:'].includes(url.protocol))window.open(url.href,'_blank','noopener,noreferrer');
      };
      actions.append(proceed);
      if(result.source_url==='https://coi.gov.cz/pro-spotrebitele/rizikove-e-shopy/') {
        const source=make('a','','Zdroj: Česká obchodní inspekce');source.href=result.source_url;source.target='_blank';source.rel='noopener noreferrer';advice.append(source);
      }
    }
    const level = danger ? [make('p', 'level', 'Téměř jistě podvod')] : [];
    body.append(...level, ...(quote ? [quote] : []), why);
    if (result.parts) {
      const list = make('div', 'parts'); list.append(make('b', '', 'Podezřelá místa ve zprávě'));
      for (const {part, partText} of result.parts) {
        const item = make('button', 'part', '„' + partText.slice(0, 120) + (partText.length > 120 ? '…“' : '“'));
        item.onclick = () => part.scrollIntoView({behavior: 'smooth', block: 'center'});
        list.append(item);
      }
      body.append(list);
    }
    if (pending || result.explaining) { const bar = make('div', 'progress'); bar.setAttribute('aria-hidden', 'true'); body.append(bar); }
    body.append(advice, actions);
    card.append(head, body);
    const tag = make('button', danger ? 'tag danger' : 'tag', result.source==='local_link_check' ? 'Ověřte odkaz' : pending ? 'Možný podvod · ověřuji' : danger ? 'Podvod! · proč?' : 'Možný podvod · proč?'); tag.insertAdjacentHTML('afterbegin', icon);
    tag.title = 'Zobrazit, proč je obsah označený a co dělat';
    tag.onclick = () => reveal(card);
    ui.getElementById('warnings').prepend(card); ui.getElementById('tags').append(tag);
    warnings.set(el, {card, tag, pending, danger});
    // Bound UI memory on long-lived feeds. Old text is never persisted.
    if (warnings.size > 5) removeWarning(warnings.keys().next().value);
    // Nothing opens by itself: the outline, the tag and the status pill point to the warning.
    if (dockOpen) open(true);
    if (wasOpen) expand(card, true);
    else { head.setAttribute('aria-expanded', 'false'); body.hidden = true; }
    limitCards();
    placeTags(); report();
    okStatus();
  }
  function open(show) {
    ui.getElementById('details').hidden = !show;
    ui.getElementById('fold').setAttribute('aria-expanded', String(show));
    if (!show) { showAll = false; limitCards(); }
  }
  function buildUI() {
    loadFont();
    host = document.createElement('ai-hlidac-panel');
    host.style.cssText = 'all:initial;position:fixed;top:0;left:0;width:1px;height:1px;z-index:2147483647;display:block;pointer-events:none';
    ui = host.attachShadow({mode: 'open'});
    ui.innerHTML = `<style>
      :host{color-scheme:light}
      *{box-sizing:border-box}
      .dock,.tag{pointer-events:auto}
      .dock{position:fixed;right:18px;bottom:18px;width:380px;max-width:calc(100vw - 36px);display:flex;flex-direction:column;align-items:flex-end;gap:10px;font:16px/1.45 'Hlidac Sans',system-ui,sans-serif;color:#18212b}
      button{font:700 15px 'Hlidac Sans',system-ui,sans-serif;cursor:pointer;border:0;border-radius:10px}
      button:focus-visible{outline:3px solid #1f56a8;outline-offset:2px}
      svg{display:block}
      #fold{display:flex;align-items:center;gap:8px;padding:8px 14px 8px 10px;border-radius:999px;background:#fff;color:#18212b;font-weight:700;font-size:14px;box-shadow:0 2px 10px #18212b2e,0 0 0 1px #18212b14;max-width:100%}
      #fold .dot{flex:none;display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:#1d7347;color:#fff}
      #fold .dot svg{width:15px;height:15px}
      #fold[data-state="busy"] .dot{background:#1f56a8}
      #fold[data-state="error"] .dot{background:#a8231b}
      #fold[data-state="warning"]{background:#ffc629}
      #fold[data-state="warning"] .dot{background:#18212b}
      #fold[data-state="danger"]{background:#c8102e;color:#fff}
      #fold[data-state="danger"] .dot{background:#fff;color:#c8102e}
      #status{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #details{width:calc(100% + 24px);margin:-12px -12px 0;max-height:calc(100vh - 76px);overflow:auto;display:flex;flex-direction:column;gap:10px;padding:12px 12px 16px}
      .warning{background:#fff;border-radius:14px;border-left:8px solid #ffc629;box-shadow:0 4px 12px #18212b33,0 0 0 1px #18212b26;padding:10px 14px;animation:in .28s ease-out}
      .warning.open{border-left-width:0;border-top:8px solid #ffc629;padding:14px 18px 18px}
      .warning.danger{border-color:#c8102e;box-shadow:0 4px 14px #c8102e55,0 0 0 2px #c8102e}
      .level{display:inline-block;margin:10px 0 0;padding:3px 10px;border-radius:999px;background:#c8102e;color:#fff;font-weight:700;font-size:14px}
      @keyframes in{from{transform:translateY(14px);opacity:0}}
      .summary{display:flex;gap:12px;align-items:center;width:100%;padding:2px 0;background:none;text-align:left;color:#18212b}
      .summary svg{flex:none;width:30px;height:30px}
      .open .summary svg{width:38px;height:38px}
      #warnings{display:flex;flex-direction:column;gap:8px}
      .label{display:flex;flex-direction:column;min-width:0}
      .snippet{font-size:13px;color:#566372;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .open .snippet{display:none}
      .more{flex:none;margin-left:auto;font-size:14px;color:#1f56a8;text-decoration:underline}
      .more::after{content:' ▾'}.open .more::after{content:' ▴'}
      h2{margin:0;font:700 17px/1.25 'Hlidac Sans',system-ui,sans-serif;color:#18212b}
      .open h2{font-size:19px}
      .parts{margin:12px 0 0}.parts b{display:block;margin-bottom:6px}
      .parts .part{display:block;width:100%;text-align:left;margin:0 0 6px;padding:8px 12px;border:0;border-radius:8px;background:#f3f5f8;color:#3d4955;font-family:inherit;font-size:14px;font-style:italic;line-height:1.4;cursor:pointer;overflow-wrap:anywhere}
      blockquote{margin:12px 0 0;padding:8px 12px;background:#f3f5f8;border-radius:8px;font-size:14px;color:#3d4955;overflow-wrap:anywhere;font-style:italic}
      .why{margin:10px 0 0;font-size:15px;color:#3d4955}
      .advice{margin-top:12px;padding:12px 14px;border-radius:10px;background:#e8eff9;border-left:4px solid #1f56a8}
      .advice b{font-size:14px;color:#1f56a8}
      .advice p{margin:2px 0 0;font-size:16px}
      .actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
      .primary{background:#1f56a8;color:#fff;padding:10px 16px}
      .primary:hover{background:#18478d}
      .secondary{background:#f3f5f8;color:#18212b;padding:10px 16px;box-shadow:inset 0 0 0 1px #c5cdd7}
      .secondary:hover{background:#e6eaef}
      #warnings:not(:empty)~.empty{display:none}
      #more{margin-top:8px;width:100%;padding:8px 14px}
      .stopped{margin-top:12px;padding:12px 14px;border-radius:10px;background:#fff4d1;border-left:4px solid #e0a100}
      .stopped b{font-size:14px}.stopped p{margin:2px 0 8px;font-size:15px}
      @media (max-height:600px),(max-width:480px){
        .dock{right:8px;bottom:8px;max-width:calc(100vw - 16px);font-size:15px}
        #details{max-height:calc(100vh - 44px)}
        .warning{padding:8px 12px}.warning.open{padding:10px 12px 0;border-top-width:6px}
        .summary svg,.open .summary svg{width:26px;height:26px}
        h2,.open h2{font-size:16px}
        .why,.advice{margin-top:8px}.advice{padding:8px 10px}.advice p{font-size:15px}
        /* Buttons stay in view while the rest of the card scrolls. */
        .actions{position:sticky;bottom:0;background:#fff;margin:8px -12px 0;padding:8px 12px 10px;box-shadow:0 -6px 10px -8px #18212b40}
      }
      .empty{background:#fff;border-radius:14px;padding:14px 16px;font-size:14px;color:#566372;box-shadow:0 6px 24px #18212b29}
      .tag{position:fixed;display:flex;align-items:center;gap:6px;padding:4px 10px 4px 6px;background:#ffc629;color:#18212b;font-size:13px;border-radius:999px;box-shadow:0 2px 8px #18212b40;font-family:'Hlidac Sans',system-ui,sans-serif}
      .tag svg{width:18px;height:18px}
      .tag.danger{background:#c8102e;color:#fff;font-weight:700;animation:pulse 1s ease-in-out 3}
      .tag.danger svg path:first-child{stroke:#fff}
      @keyframes pulse{50%{box-shadow:0 0 0 7px #c8102e40}}
      [hidden]{display:none!important}
      .progress{margin-top:12px;height:5px;border-radius:3px;background:#e8eff9;overflow:hidden}
      .progress::after{content:'';display:block;width:35%;height:100%;border-radius:3px;background:#1f56a8;animation:slide 1.3s ease-in-out infinite}
      @keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(290%)}}
      @media (prefers-reduced-motion:reduce){.warning,.progress::after,.tag.danger{animation:none}}
      </style>
      <div id="tags"></div>
      <div class="dock"><div id="details" hidden><div id="warnings" aria-live="polite"></div><button id="more" class="secondary" hidden></button><p class="empty">Ochrana čte texty na stránce jen ve vašem počítači. Když zpráva připomíná podvod, upozorní vás tady. Může se i splést, neoznačená zpráva nemusí být bezpečná.</p></div>
      <button id="fold" aria-expanded="false" data-state="busy" title="PEPA"><span class="dot">${SHIELD_ICON}</span><span id="status" role="status">Připojuji ochranu…</span></button></div>`;
    ui.getElementById('more').onclick = () => { showAll = true; limitCards(); };
    ui.getElementById('fold').onclick = () => {
      const show = ui.getElementById('details').hidden;
      open(show);
      // A single warning has nothing to choose from, so show its details straight away.
      if (show && warnings.size === 1) expand([...warnings.values()][0].card, true);
    };
    document.documentElement.append(host);
    addEventListener('resize', queuePlace, {passive: true});
  }
  function schedule() { clearTimeout(timer); if(active) timer=setTimeout(scan,600); }
  async function scanPage(version) {
    const fields=[...document.querySelectorAll('input[type="password"]')].filter(visible);
    if(!fields.length){ issues.delete('page'); if(pageWarning){removeWarning(pageWarning);pageWarning=null;} pageSignature=''; return; }
    const forms=[...new Set(fields.map(el=>el.form || el))].slice(0,12);
    const page={brand_text:[document.title,...[...document.querySelectorAll('h1,h2,img[alt]')].filter(visible).slice(0,12).map(el=>el.alt || el.innerText)].join(' ').slice(0,1200),forms:forms.map(el=>{
      const url=new URL(el.action || location.href,location.href);
      return {password:true,action_host:url.hostname,action_scheme:url.protocol};
    })};
    const signature=JSON.stringify(page)+location.href;
    if(signature===pageSignature)return;
    const result=await send({type:'page',page});
    if(!active || generation!==version)return;
    if(result.error){issues.set('page','Formuláře teď nejde zkontrolovat.');okStatus();return;}
    issues.delete('page');
    pageSignature=signature;
    if(pageWarning)removeWarning(pageWarning);
    if(result.status==='warning'){
      pageWarning=fields[0];
      warning(pageWarning,`${page.brand_text.slice(0,140)} · ${location.hostname}`,result,`Přihlašovací formulář na adrese ${location.hostname}`);
    } else pageWarning=null;
  }
  function shownHost(text) {
    const value=text.trim();
    if(!value || /\s/.test(value))return '';
    try {
      const url=new URL(/^https?:\/\//i.test(value) ? value : 'https://'+value);
      if(!['http:','https:'].includes(url.protocol) || url.username || !url.hostname.includes('.'))return '';
      return url.hostname;
    } catch {return '';}
  }
  function bankHost(value) {
    const host=shownHost(value);
    return /(^|\.)(csas\.cz|servis24\.cz|kb\.cz|mojebanka\.cz)$/i.test(host) ? host : '';
  }
  function linkInfo(el) {
    try {
      const url=realTarget(el.href);
      if(!['http:','https:'].includes(url.protocol))return null;
      const label=textOf(el);
      return {signature:el.href+'\n'+label, data:{hostname:url.hostname,display_hostname:bankHost(label),userinfo_hostname:bankHost(decodeURIComponent(url.username))}};
    } catch {return null;}
  }
  async function scanLinks(version) {
    if(Date.now()-lastLinkRefresh>15*60*1000){linkProcessed=new WeakMap();lastLinkRefresh=Date.now();}
    const pending=[];
    for(const el of document.querySelectorAll('a[href]')) {
      // Navigation links also matter; editable areas and our own UI never qualify.
      if(!el.isConnected || el.closest('ai-hlidac-panel,input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[hidden]') || !visible(el))continue;
      const info=linkInfo(el);
      if(!info || linkProcessed.get(el)===info.signature)continue;
      if(pending.length===30){schedule();break;}
      pending.push({el,...info});
    }
    if(!pending.length)return;
    const response=await send({type:'links',links:pending.map(item=>item.data)});
    if(!active || generation!==version)return;
    if(response.error || !Array.isArray(response.results) || response.results.length!==pending.length){issues.set('links','Odkazy teď nejde zkontrolovat.');okStatus();return;}
    issues.delete('links');issues.delete('links_changed');
    if(response.list_status!=='fresh')issues.set('link_list','Seznam rizikových obchodů chybí nebo je zastaralý. Kontrola adres dál běží.');
    else issues.delete('link_list');
    pending.forEach((item,i)=>{
      if(!item.el.isConnected || linkInfo(item.el)?.signature!==item.signature){schedule();return;}
      const result=response.results[i];linkProcessed.set(item.el,item.signature);
      if(result.status==='skipped')skipped++;else linksChecked++;
      linkEvidence.set(item.el,{signature:item.signature,result});
      if(result.status==='warning')warning(item.el,`Cíl odkazu: ${item.data.hostname}`,result,`Cíl odkazu: ${item.data.hostname}`);
      else removeWarning(item.el);
    });
    okStatus();
  }
  // Attachments are judged by their file type alone, never by the model: types that run a program or open a page
  // with a login form when opened, and documents with a second, hidden extension ("faktura.pdf.exe").
  const RISKY_FILE = /([^\s\\/:*?"<>|]{1,80}\.(html?|shtml|svg|iso|img|vhdx?|exe|scr|pif|bat|cmd|jse?|vbe|vbs|wsf|hta|lnk|msi|ps1|jar))(?![\w.-])/i;
  const HIDDEN_EXTENSION = /\.(pdf|docx?|xlsx?|jpe?g|png|txt)\.[a-z0-9]{2,4}$/i;
  function attachmentName(el) {
    // Only what the mail client marks as an attachment (a download link, an "attachment" label); file names written
    // in the message text are not attachments.
    const cue = [el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('href')].join(' ');
    if (!el.hasAttribute('download') && !el.hasAttribute('download_url') && !/příloh|priloh|attach|attid|download|stáhnout/i.test(cue)) return '';
    const name = [el.getAttribute('download'), el.getAttribute('download_url')?.split(':')[1], el.getAttribute('aria-label'), el.getAttribute('title'), el.innerText]
      .map(v => (v || '').trim().match(RISKY_FILE)?.[1]).find(Boolean);
    return name || '';
  }
  function scanAttachments() {
    for (const el of document.querySelectorAll('[download], [download_url], a[href], [role="button"][aria-label], [title]')) {
      const name = attachmentName(el), owner = el.matches('a[href]') ? el.parentElement : el;
      if (!name || !owner || attachmentSeen.get(owner) === name || el.parentElement?.closest('[download], [download_url]') || !eligible(el)) continue;  // webmail lists attachments in the header, outside the body
      attachmentSeen.set(owner, name); attachmentSource.set(owner, el);
      const hidden = HIDDEN_EXTENSION.test(name);
      warning(owner, name, {status: 'warning', level: 'caution', category: 'attachment', source: 'local_attachment', title: 'Riziková příloha',
        message: hidden ? `Příloha „${name}“ se tváří jako dokument, ale je to jiný typ souboru (podle poslední přípony). Po otevření může spustit program nebo ukázat falešnou přihlašovací stránku.`
          : `Příloha „${name}“ je typ souboru, který po otevření může spustit program nebo ukázat falešnou přihlašovací stránku. Podvodníci ho posílají místo faktur a dokumentů.`,
        advice: 'Přílohu neotevírejte. Pokud ji opravdu čekáte, ověřte si u odesílatele jinou cestou (na známém čísle), co posílal.'}, `Příloha: ${name}`);
    }
  }
  function guardLink(event) {
    if(!active || (event.type==='auxclick' && event.button!==1))return;
    const el=event.target instanceof Element ? event.target.closest('a[href]') : null;
    if(!el)return;
    const evidence=linkEvidence.get(el),info=linkInfo(el);
    if(evidence?.result.status!=='warning'){
      // A link inside a message flagged as a possible scam opens only after a second, deliberate click.
      const owner=[...warnings.keys()].find(m=>m!==el && m.contains(el) && !linkEvidence.has(m));
      if(owner && info){event.preventDefault();event.stopImmediatePropagation();stopLink(owner,el);}
      return;
    }
    if(evidence.signature!==info?.signature){
      if(info){event.preventDefault();event.stopImmediatePropagation();linkProcessed.delete(el);issues.set('links_changed','Odkaz se změnil. Počkejte na novou kontrolu.');okStatus();schedule();}
      return;
    }
    event.preventDefault();event.stopImmediatePropagation();
    dismissed.delete(el);warning(el,`Cíl odkazu: ${info.data.hostname}`,evidence.result,`Cíl odkazu: ${info.data.hostname}`);
    reveal(warnings.get(el).card);
  }
  function stopLink(owner, el) {
    const {card}=warnings.get(owner),href=el.href;
    card.querySelector('.stopped')?.remove();
    const box=make('div','stopped');
    box.append(make('b','','Odkaz jsme zatím neotevřeli'),make('p','',`Vede na ${new URL(href).hostname}. Zpráva vypadá jako podvod, proto ho raději neotvírejte.`));
    const proceed=make('button','secondary','Přesto otevřít odkaz');
    proceed.onclick=()=>{ if(el.isConnected && el.href===href) window.open(href,'_blank','noopener,noreferrer'); box.remove(); };
    box.append(proceed);
    card.querySelector('.advice').before(box);
    reveal(card);
  }
  addEventListener('click',guardLink,true);
  addEventListener('auxclick',guardLink,true);
  async function scanImages(version) {
    if(Date.now()-lastImageScan<10000)return;
    lastImageScan=Date.now();
    const images=[...document.querySelectorAll('img,canvas')].filter(el=>eligible(el) && hasMessageContext(el));
    let count=0;
    for(const el of images){
      if(!active || generation!==version || document.hidden || count>=2)break;
      const r=el.getBoundingClientRect();
      if(r.width<180 || r.height<70 || r.top<0 || r.left<0 || r.bottom>innerHeight || r.right>innerWidth)continue;
      // Never send pixels covering typed fields, including overlays over an image.
      const overlays=[...document.querySelectorAll('input,textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"]'),...ui.querySelectorAll('.dock,.tag')];
      const overlaps=overlays.some(field=>{
        const b=field.getBoundingClientRect();return b.width && b.height && b.left<r.right && b.right>r.left && b.top<r.bottom && b.bottom>r.top;
      });
      if(overlaps)continue;
      const key=el.currentSrc || el.src || 'canvas';
      if(imageProcessed.get(el)===key)continue;
      count++;
      const result=await send({type:'image',box:{x:r.left,y:r.top,width:r.width,height:r.height,viewportWidth:innerWidth,viewportHeight:innerHeight}});
      if(!active || generation!==version)break;
      if(!el.isConnected || !hasMessageContext(el)){schedule();continue;}
      if(result.error){issues.set('image','Obrázky teď nejde zkontrolovat.');okStatus();continue;}
      issues.delete('image');
      imageProcessed.set(el,key);
      if(result.status==='warning')warning(el,`Text přečtený z obrázku: ${result.transcript}`,result,`Text přečtený z obrázku: ${result.transcript}`);
      else removeWarning(el);
    }
  }
  async function verifyAll(version) {
    if (verifying) return;
    verifying = true;
    try {
      while (active && generation === version && (verifyQueue.length || explainQueue.length)) {
        if (!verifyQueue.length) { await explainNext(version); continue; }
        // Shown warnings the user can see go first, then other shown warnings, then the quiet checks.
        const rank = ({el}) => (warnings.get(el)?.pending ? 0 : 2) + (el.isConnected && visible(el) ? 0 : 1);
        const next = verifyQueue.reduce((best, item, i) => rank(item) < rank(verifyQueue[best]) ? i : best, 0);
        const {el, text} = verifyQueue.splice(next, 1)[0];
        // Dismissed, replaced or changed in the meantime: nothing to verify.
        const wanted = () => warnings.get(el)?.pending || quiet.get(el) === text;
        if (!wanted() || !el.isConnected || textOf(el) !== text) { quiet.delete(el); okStatus(); continue; }
        let result;
        for (let attempt = 0; attempt < 3; attempt++) {
          if (attempt) await new Promise(resolve => setTimeout(resolve, 3000));
          try { result = await send({type: 'analyze', text: clip(text), early: true}); } catch { result = {error: true}; }
          if (!result.error || !active || generation !== version) break;
        }
        if (!active || generation !== version) break;
        if (!wanted()) continue;
        quiet.delete(el);
        if (!el.isConnected || textOf(el) !== text) { removeWarning(el); schedule(); continue; }
        // Missing a scam is worse than a false alarm: an unverified flag stays, as a plain warning.
        if (result.error) warning(el, text, {title: 'Možný podvod', message: 'Podrobné ověření se teď nepodařilo. Rychlá kontrola tu ale našla znaky podvodu.', advice: 'Na nic neklikejte, nic neplaťte a nesdělujte žádné údaje. Když si nejste jistí, zavolejte odesílateli na číslo, které znáte odjinud.'});
        // A widened text around messages already confirmed as scams adds only a second frame around them.
        else if (result.status === 'warning' && widened.has(el) && [...warnings].some(([other, shown]) => other !== el && el.contains(other) && !shown.pending)) okStatus();
        else if (result.status === 'warning') {
          // The warning shows with the verdict; its reason follows later, in place, once all verdicts are in.
          warning(el, text, result);
          if (result.explaining) explainQueue.push({el, text, result});
          await splitWarning(el, text, result, version);
        }
        else removeWarning(el);
        if (result.status !== 'warning') recheckWhole(el);
        if (!result.error && result.status !== 'warning' && result.unclear) widen(el);
        okStatus();
      }
    } finally { verifying = false; }
  }
  // Writes the reason of one confirmed warning (visible ones first) into its card, or into a split unit kept aside.
  async function explainNext(version) {
    const next = explainQueue.reduce((best, item, i) => item.el.isConnected && visible(item.el) && !(explainQueue[best].el.isConnected && visible(explainQueue[best].el)) ? i : best, 0);
    const {el, text, result} = explainQueue.splice(next, 1)[0];
    const current = () => (warnings.has(el) || splitUnits.has(el)) && el.isConnected && textOf(el) === text;
    if (!current()) return;
    const parts = [];
    for (const {part, partText} of result.candidates || []) {
      let checked;
      try { checked = await send({type: 'analyze', text: clip(partText), early: true}); } catch { checked = {error: true}; }
      if (!active || generation !== version || !current()) return;
      if (checked.status === 'warning' && part.isConnected && textOf(part) === partText) parts.push({part, partText});
    }
    if (parts.length >= 2) { result.parts = parts; if (warnings.has(el)) warning(el, text, result); }
    let explained;
    try { explained = await send({type: 'explain', text: clip(text)}); } catch { explained = {error: true}; }
    if (!active || generation !== version || !current()) return;
    const done = {...result, ...(explained.error ? {message: 'Zpráva připomíná podvodnou výzvu.'} : explained), explaining: false};
    if (splitUnits.has(el)) splitUnits.get(el).result = done;
    if (warnings.has(el)) warning(el, text, done);
  }
  // The verifier could not tell ("nevím", e.g. a lone "Ahoj mami, mám nové číslo"): the text is read again with the
  // surrounding messages, one page level wider each time, until there is an answer or the text gets too long.
  function widen(el) {
    if (el.tagName === 'IFRAME') return;
    const text = textOf(el);
    for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) {
      if (!eligible(up) || !hasMessageContext(up) || up.querySelector('iframe, input, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]')) return;
      const wider = textOf(up);
      if (wider.length > 3000) return;
      if (wider.length <= text.length) continue;
      processed.set(up, wider); quiet.set(up, wider); widened.add(up); verifyQueue.push({el: up, text: wider});
      return;
    }
  }
  // A confirmed merged unit whose single messages are suspicious on their own (at least two of them):
  // - separate posts and chat bubbles, drawn as boxes of their own, get a warning each;
  // - paragraphs of one e-mail or article stay under one warning, which lists the paragraphs the verifier confirms
  //   (explainNext). The verdict on the whole text is never taken back by its paragraphs.
  async function splitWarning(unit, text, result, version) {
    // Preview rows of a message list are left out here too, as in scan().
    const parts = (unitParts.get(unit) || []).filter(part => part.isConnected && textOf(part).length >= 25 && !clippedLine(part) && !previewRow(part));
    unitParts.delete(unit);
    if (parts.length < 2) return;
    const flagged = [];
    for (const part of parts) {
      await new Promise(resolve => setTimeout(resolve, 180));  // the background worker rate-limits screening
      let partResult;
      try { partResult = await send({type: 'screen', text: clip(textOf(part))}); } catch { return; }
      if (!active || generation !== version) return;
      if (partResult.status === 'pending') flagged.push({part, partText: textOf(part), partResult});
    }
    if (flagged.length < 2 || !warnings.has(unit)) return;
    if (!flagged.every(({part}) => ownBox(part, unit, flagged.map(f => f.part)))) { result.candidates = flagged.slice(0, 3); return; }
    removeWarning(unit);
    splitUnits.set(unit, {text, result, parts: new Set(flagged.map(f => f.part))});
    for (const {part, partText, partResult} of flagged) {
      processed.set(part, partText);
      if (partResult.alarm) warning(part, partText, partResult); else quiet.set(part, partText);
      verifyQueue.push({el: part, text: partText});
    }
  }
  // The part, or a wrapper of it inside the unit, has its own background, border or shadow: a bubble or a post card.
  // A box shared with another flagged part (the reading pane of one e-mail around its paragraphs) is not its own.
  function ownBox(part, unit, others) {
    for (let e = part; e && e !== unit; e = e.parentElement) {
      if (others.some(o => o !== part && e.contains(o))) return false;
      const style = getComputedStyle(e);
      const background = style.backgroundColor.match(/[\d.]+/g) || [];
      if (background.length === 4 ? Number(background[3]) > 0 : background.length === 3) return true;
      if (style.boxShadow !== 'none' || style.backgroundImage !== 'none') return true;
      if (['Top', 'Bottom', 'Left', 'Right'].some(side => parseFloat(style[`border${side}Width`]) > 0 && style[`border${side}Style`] !== 'none')) return true;
    }
    return false;
  }
  // None of the split posts turned out to be a scam on its own: the confirmed warning returns to the whole unit.
  function recheckWhole(part) {
    for (const [unit, {text, result, parts}] of splitUnits) {
      if (!parts.has(part)) continue;
      if ([...parts].some(p => warnings.has(p) || quiet.has(p))) return;
      splitUnits.delete(unit);
      if (unit.isConnected && textOf(unit) === text) warning(unit, text, result);
      return;
    }
  }
  async function scan() {
    if (!active || running || document.hidden) return;
    running=true; const version=generation;
    try {
      for (const el of warnings.keys()) if (!el.isConnected || (attachmentSource.has(el) ? !attachmentSource.get(el).isConnected || attachmentName(attachmentSource.get(el))!==attachmentSeen.get(el) : linkEvidence.has(el) ? linkEvidence.get(el).signature!==linkInfo(el)?.signature : (el!==pageWarning && (!hasMessageContext(el) || (!imageProcessed.has(el) && processed.get(el)!==textOf(el)))))) removeWarning(el);
      await scanLinks(version);
      scanAttachments();
      await scanPage(version);
      const nodes=[...document.querySelectorAll(selector + ', div, span, iframe')].filter(el => {
        if (!eligible(el) || !hasMessageContext(el) || el.matches('a[href]') || el.closest('a[href]') || attachmentSource.has(el)) return false;
        // Plain div/span messages are common in webmail and chat. Only leaf-like text
        // containers qualify; never combine an entire page or editable descendants.
        if (el.matches(selector)) return !el.querySelector('input, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]');
        return !el.querySelector(selector + ', div, input, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]') && textOf(el).length >= 25;
      });
      // Neighbouring messages (chat bubbles, e-mail paragraphs) are read together: a scam often only shows across them.
      const counts=new Map();
      for (const el of nodes) for (let up=el.parentElement, depth=0; up && up!==document.body && depth<3; up=up.parentElement, depth++) counts.set(up,(counts.get(up)||0)+1);
      const unitOf=el => {
        if (el.tagName==='IFRAME') return el;
        let unit=el;
        for (let up=el.parentElement, depth=0; up && up!==document.body && depth<3; up=up.parentElement, depth++) {
          if (!eligible(up) || !hasMessageContext(up) || up.querySelector('iframe, input, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]') || textOf(up).length>3000) break;
          if (counts.get(up)>=2) unit=up;
        }
        return unit;
      };
      const units=[...new Set(nodes.map(unitOf))];
      // The single messages a merged unit was built from (outermost only: a post, not its paragraphs).
      const partsOf=unit => nodes.filter(n => n!==unit && unit.contains(n) && !nodes.some(o => o!==n && o!==unit && unit.contains(o) && o.contains(n)));
      const handle=(el,text,result) => {
        if (result.status==='pending') {
          if (result.alarm) warning(el,text,result); else { removeWarning(el); quiet.set(el,text); }
          if (warnings.get(el)?.pending || quiet.has(el)) { verifyQueue.push({el,text}); verifyAll(version); }
        }
        else if (result.status==='warning') warning(el,text,result);
        else { removeWarning(el); if(result.status==='skipped') skipped++; }
      };
      let count=0, foundPreviews=false;
      for (const el of units) {
        if (!active || generation!==version || document.hidden) break;
        // A parent message takes precedence over nested paragraphs, avoiding duplicate scans.
        if (el.tagName!=='IFRAME' && units.some(other => other!==el && other.contains(el) && textOf(other).length<=3000)) continue;
        const text=textOf(el);
        if (text.length<25 || words(text)<3 || processed.get(el)===text) continue;
        if (el.tagName!=='IFRAME' && (clippedLine(el) || previewRow(el))) { foundPreviews=true; continue; }
        if (++count>20) { schedule(); break; }
        let result;
        try { result=await send({type:'screen',text:clip(text)}); } catch { result={error:'Spojení s rozšířením bylo přerušeno.'}; }
        if (!active || generation!==version) break;
        if (result.error) { issues.set('text',result.missing?result.error:'Ochrana se ještě spouští nebo není dostupná.'); okStatus(); break; }
        issues.delete('text');
        if (!el.isConnected || !hasMessageContext(el) || textOf(el)!==text) { schedule(); continue; }
        processed.set(el,text); checked++;
        if (result.status==='pending') unitParts.set(el,partsOf(el));
        handle(el,text,result);
        okStatus();
        await new Promise(resolve=>setTimeout(resolve,180));
      }
      previews=foundPreviews || (count>20 && previews);  // a scan cut short has not seen every text
      if (checked===0 && currentStatus==='Kontrola se spouští.') okStatus();
      if(active && generation===version)await scanImages(version);
      issues.delete('scan'); okStatus();
    } catch { issues.set('scan','Část stránky nejde zkontrolovat.'); okStatus(); }
    finally { running=false; }
  }
  async function ping() {
    if (!active || document.hidden || running) return;
    try {
      const result=await send({type:'ping'});
      if (!active) return;
      if(result.error) issues.set('connection',result.missing?result.error:'Ochrana se ještě spouští nebo není dostupná.');
      else { issues.delete('connection'); schedule(); }
      okStatus();
    } catch {
      // After an update or reload of the extension this copy is orphaned (a new one runs): remove its panel and outlines.
      if (!chrome.runtime?.id) { toggle(false); return; }
      issues.set('connection','Ochrana není dostupná. Obnovte stránku.'); okStatus();
    }
  }
  function toggle(on) {
    if (active===on) return;
    active=on; generation++; verifyQueue.length=0; explainQueue.length=0; quiet.clear();
    if(on) {
      issues.clear(); currentStatus='Kontrola se spouští.'; statusState='busy'; report();
      linkProcessed=new WeakMap();linkEvidence=new WeakMap();linksChecked=0;
      processed=new WeakMap(); imageProcessed=new WeakMap(); attachmentSeen=new WeakMap(); attachmentSource=new WeakMap(); lastImageScan=0; pageSignature=''; pageWarning=null; checked=0; skipped=0; buildUI();
      observer=new MutationObserver(changes=>{
        if(changes.some(c=>!host.contains(c.target) && c.target!==host)) { schedule(); queuePlace(); }
      });
      observer.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['href','action','type','src']});
      heartbeat=setInterval(ping,15000); ping(); schedule();
    } else {
      observer?.disconnect(); clearTimeout(timer); clearInterval(heartbeat);
      for(const el of warnings.keys()) removeWarning(el);
      host?.remove(); ui=null;
    }
  }
  chrome.runtime.onMessage.addListener((message, sender, respond)=>{
    if(message.type==='toggle') { toggle(Boolean(message.on)); respond({ok:true}); }
    if(message.type==='diagnostics') respond({active, checked, linksChecked, skipped, warnings:warnings.size, status:currentStatus, statusState});
  });
  addEventListener('scroll',()=>{schedule();queuePlace();},{passive:true});
  document.addEventListener('load',event=>{ if(event.target.tagName==='IFRAME') schedule(); },true);
  document.addEventListener('visibilitychange',()=>{ if(!document.hidden){ping();schedule();} });
  send({type:'state'}).then(result=>toggle(result.on)).catch(()=>{});
})();
