let chain = Promise.resolve();
let creating = null;
const lastCall = new Map();
chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
chrome.action.setBadgeBackgroundColor({color: '#FFC629'});
chrome.action.setBadgeTextColor({color: '#18212B'});

// The models run in the native helper (install.py, llama.cpp). Chrome starts it on connect and stops it on
// disconnect; this one port serves every window and tab.
const HELPER = 'cz.aihlidac.helper';
const MISSING = 'Chybí pomocník PEPA s modely. Nainstalujte ho podle návodu v README (install.sh, ve Windows install.cmd) a restartujte prohlížeč.';
let helper = null, nextId = 1;
const calls = new Map();

function connectHelper() {
  helper ||= new Promise(resolve => {
    let connected = false;
    const port = chrome.runtime.connectNative(HELPER);
    port.onMessage.addListener(message => {
      if (!connected) { connected = true; resolve(port); }
      const done = calls.get(message.id);
      calls.delete(message.id);
      done?.(message);
    });
    port.onDisconnect.addListener(() => {
      helper = null;  // never answered: not installed (or broken); the next request tries again
      for (const done of calls.values()) done({error: 'Ochrana se právě spouští. Zkuste to za chvíli znovu.'});
      calls.clear();
      resolve(null);
    });
    port.postMessage({id: 0, op: 'status'});
  });
  return helper;
}

function callHelper(port, op, payload) {
  const id = nextId++;
  return new Promise(resolve => { calls.set(id, resolve); port.postMessage({id, op, ...payload}); });
}

async function engine(op, payload = {}) {
  const port = await connectHelper();
  if (!port) throw Object.assign(new Error(MISSING), {missing: true});
  const {id, ...result} = await callHelper(port, op, payload);
  if (result.error) throw new Error(result.error);
  return result;
}

function queued(task) { const pending=chain.then(task); chain=pending.catch(()=>{}); return pending; }
async function cropImage(sender, box) {
  if (!box || !['x','y','width','height','viewportWidth','viewportHeight'].every(k=>Number.isFinite(box[k]))) throw new Error('Neplatná oblast obrázku.');
  if (box.x<0 || box.y<0 || box.width<80 || box.height<40 || box.x+box.width>box.viewportWidth+1 || box.y+box.height>box.viewportHeight+1) throw new Error('Obrázek není celý viditelný.');
  const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});
  // sender.url keeps the address the page loaded with; web mail and chat apps change it later (history.pushState).
  if (!tab || tab.id!==sender.tab.id || !tab.url || new URL(tab.url).origin!==sender.origin) throw new Error('Kontrola obrázku vyžaduje aktivní stránku.');
  const captured=await chrome.tabs.captureVisibleTab(tab.windowId,{format:'png'});
  const bytes=Uint8Array.from(atob(captured.split(',')[1]),c=>c.charCodeAt(0));
  const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
  const ratio=bitmap.width/box.viewportWidth;
  const width=Math.round(box.width*ratio),height=Math.round(box.height*ratio);
  if(width*height>3_000_000){bitmap.close();throw new Error('Obrázek je příliš velký.');}
  const canvas=new OffscreenCanvas(width,height);
  canvas.getContext('2d').drawImage(bitmap,box.x*ratio,box.y*ratio,width,height,0,0,width,height);bitmap.close();
  const data=new Uint8Array(await (await canvas.convertToBlob({type:'image/png'})).arrayBuffer());
  if(data.length>1_400_000)throw new Error('Obrázek je příliš velký.');
  let binary=''; for(let i=0;i<data.length;i+=8192)binary+=String.fromCharCode(...data.subarray(i,i+8192));
  return btoa(binary);
}

async function enabled(sender) {
  if (!sender.tab || sender.frameId !== 0) return false;
  const url = new URL(sender.url);
  const {sites = {}, paused = false} = await chrome.storage.local.get(['sites', 'paused']);
  return !paused && ['http:', 'https:'].includes(url.protocol) && sites[url.origin] !== false;
}

async function refreshTabs() {
  const tabs = await chrome.tabs.query({url: ['http://*/*', 'https://*/*']});
  return await Promise.all(tabs.map(async tab => {
    const on = await enabled({tab, frameId: 0, url: tab.url});
    try {
      await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['content.js']});
      await chrome.tabs.sendMessage(tab.id, {type: 'toggle', on});
      return {tabId: tab.id, ok: true};
    } catch {
      return {tabId: tab.id, error: 'Prohlížeč nepovolil kontrolu této stránky. Zkuste ji obnovit a zkontrolujte přístup rozšíření k webům.'};
    }
  }));
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  (async () => {
    const fromUI = typeof sender.url === 'string' && sender.url.startsWith(chrome.runtime.getURL(''));
    if (message.type === 'health' && fromUI) return await engine('status');
    if (message.type === 'pause' && fromUI) {
      await chrome.storage.local.set({paused: Boolean(message.paused)});
      await refreshTabs();
      return {ok: true};
    }
    if (message.type === 'inspect' && fromUI) {
      const tab = await chrome.tabs.get(message.tabId);
      const on = await enabled({tab, frameId: 0, url: tab.url});
      if (!on) return {on: false};
      try {
        const state = await chrome.tabs.sendMessage(tab.id, {type: 'diagnostics'});
        return {on, ...state};
      } catch {
        return {on, status: 'Na této stránce kontrola neběží. Obnovte stránku; u rozšíření povolte přístup ke všem webům. Interní stránky prohlížeče kontrolovat nelze.'};
      }
    }
    if (message.type === 'configure' && fromUI) {
      const {origin, on} = message;
      const url = new URL(origin);
      if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin) throw new Error('Nepodporovaný web.');
      const {sites = {}} = await chrome.storage.local.get('sites');
      sites[origin] = Boolean(on);
      await chrome.storage.local.set({sites});
      return {ok: true, tabs: await refreshTabs()};
    }
    if (message.type === 'count' && sender.tab) {
      const n = Math.max(0, Math.min(99, Number(message.n) || 0));
      await chrome.action.setBadgeText({tabId: sender.tab.id, text: n ? String(n) : ''});
      await chrome.action.setBadgeBackgroundColor({tabId: sender.tab.id, color: message.danger ? '#C8102E' : '#FFC629'});
      await chrome.action.setBadgeTextColor({tabId: sender.tab.id, color: message.danger ? '#FFFFFF' : '#18212B'});
      return {ok: true};
    }
    if (message.type === 'state') return {on: await enabled(sender)};
    if (!(await enabled(sender))) throw new Error('Ochrana na tomto webu není zapnuta.');
    if (message.type === 'links') return await engine('links', {links: message.links});
    if (message.type === 'ping') return await engine('status');
    if (message.type === 'page') return await queued(async()=>{
      if(!(await enabled(sender)))throw new Error('Ochrana byla vypnuta.');
      const url=new URL(sender.url);
      return engine('page', {page: {...message.page, hostname: url.hostname, scheme: url.protocol}});
    });
    if (message.type === 'image') return await queued(async()=>{
      if(!(await enabled(sender)))throw new Error('Ochrana byla vypnuta.');
      const image=await cropImage(sender,message.box);
      return engine('image', {image});
    });
    if (!['screen', 'analyze', 'explain'].includes(message.type) || typeof message.text !== 'string' || message.text.length > 20000) throw new Error('Neplatný požadavek.');
    // Screening is fast and answers at once, even while the verifier is busy; only screening is rate limited.
    if (message.type === 'screen') {
      const now = Date.now();
      if (now - (lastCall.get(sender.tab.id) || 0) < 150) throw new Error('Vyčkejte na dokončení kontroly.');
      lastCall.set(sender.tab.id, now);
      return await engine('screen', {text: message.text});
    }
    return await queued(async () => {
      if (!(await enabled(sender))) throw new Error('Ochrana byla vypnuta.');
      // "early": a warning comes back with the verdict alone; "explain" then writes its reason.
      return engine(message.type, {text: message.text, early: Boolean(message.early)});
    });
  })().then(respond).catch(error => respond({error: error.message || 'Lokální model není dostupný.', missing: Boolean(error.missing)}));
  return true;
});
chrome.tabs.onRemoved.addListener(id => lastCall.delete(id));

async function upgrade() {
  // Remove the old per-site registration; version 0.2 uses static content scripts.
  await chrome.scripting.unregisterContentScripts();
  await refreshTabs();
}
chrome.runtime.onInstalled.addListener(async () => {
  await upgrade();
  await engine('status');  // starts the helper and loads the models before the first message
});
chrome.runtime.onStartup.addListener(async () => { await engine('status'); await refreshTabs(); });
