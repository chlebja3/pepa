const $ = id => document.getElementById(id);
let origin, tabId, on = false, paused = false, engine = null, missing = false;
async function request(message) {
  const result = await chrome.runtime.sendMessage(message);
  if (result.error) throw new Error(result.error);
  return result;
}
function hero(state, headline, text) {
  $('hero').dataset.state = state;
  $('headline').textContent = headline;
  $('status').textContent = text;
}
function plural(n, one, few, many) { return n === 1 ? one : n >= 2 && n <= 4 ? few : many; }
async function health() {
  const result = await chrome.runtime.sendMessage({type: 'health'});
  missing = Boolean(result.missing);
  engine = result.error ? null : result;
  return result.error;
}
async function refresh(problem) {
  const {sites = {}, paused: globalPause = false} = await chrome.storage.local.get(['sites', 'paused']);
  paused = globalPause;
  on = sites[origin] !== false;
  $('controls').hidden = false;
  $('pause').checked = !paused; $('pause').disabled = false;
  $('toggle').checked = on && !paused; $('toggle').disabled = !origin || paused;
  if (missing) return hero('offline', 'Chybí pomocník s modely', problem);
  if (!engine) return hero('loading', 'Ochrana se spouští…', problem || 'Za chvíli bude připravená.');
  if (engine.screener === 'loading') return hero('loading', 'Ochrana se spouští…', 'Načítám model. Trvá to jen pár sekund.');
  if (engine.screener === 'error') return hero('offline', 'Ochranu se nepodařilo spustit', 'Zkuste restartovat prohlížeč. Pokud potíže trvají, rozšíření přeinstalujte.');
  if (paused) { $('scan-status').textContent = 'Ochrana je pozastavená všude.'; return hero('paused', 'Ochrana je pozastavená', 'Zapněte ji přepínačem níže.'); }
  if (!origin) { $('scan-status').textContent = 'Stránky prohlížeče a nastavení se nekontrolují.'; return hero('paused', 'Tato stránka se nekontroluje', 'Stránky prohlížeče se nekontrolují.'); }
  if (!on) { $('scan-status').textContent = 'Tuto stránku jste vyřadili z kontroly.'; return hero('paused', 'Tato stránka se nehlídá', 'Na ostatních webech ochrana dál běží.'); }
  const result = await request({type: 'inspect', tabId});
  const checked = result.checked || 0, found = result.warnings || 0;
  $('scan-status').textContent = result.active
    ? `Zkontrolováno ${checked} ${plural(checked, 'text', 'texty', 'textů')} a ${result.linksChecked || 0} odkazů.`
    : (result.status || 'Obnovte stránku, aby se kontrola spustila.');
  if (!result.active) return hero('offline', 'Kontrola stránky neběží', result.status || 'Obnovte stránku a zkontrolujte oprávnění rozšíření.');
  if (result.statusState === 'error') return hero('offline', 'Kontrola má potíže', result.status + (found ? ' Na stránce zůstávají také upozornění.' : ''));
  if (found) return hero('warning', found === 1 ? 'Podezřelý obsah na této stránce' : `${found} ${plural(found, '', 'podezřelé zprávy', 'podezřelých zpráv')} na této stránce`, 'Než cokoli zaplatíte nebo vyplníte, přečtěte si upozornění vpravo dole.');
  if (result.skipped) return hero('paused', 'Část obsahu se nekontrolovala', 'Některé texty nebo odkazy nebylo možné zkontrolovat. Neoznačený obsah nemusí být bezpečný.');
  if (engine.verifier === 'loading') return hero('on', 'Kontrola běží', `Připravuji podrobné ověření${engine.progress > 0 && engine.progress < 1 ? ` (${Math.round(engine.progress * 100)} %)` : ''}. Rychlá kontrola už funguje.`);
  hero('on', 'Kontrola běží', 'Vše běží v tomto počítači. Neoznačený obsah nemusí být bezpečný.');
}
async function start() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  try {
    const url = new URL(tab.url);
    if (!['http:', 'https:'].includes(url.protocol)) throw Error();
    origin = url.origin; tabId = tab.id;
    $('site').textContent = url.hostname;
  } catch { $('site').textContent = 'Stránka prohlížeče'; }
  await refresh(await health());
}
$('toggle').onchange = async () => {
  try { await request({type: 'configure', origin, on: $('toggle').checked}); await refresh(); }
  catch(error) { $('scan-status').textContent = error.message; }
};
$('pause').onchange = async () => {
  try { await request({type: 'pause', paused: !$('pause').checked}); await refresh(); }
  catch(error) { $('scan-status').textContent = error.message; }
};
start().catch(error => hero('offline', 'Něco se pokazilo', error.message));
setInterval(async () => { try { await refresh(await health()); } catch(error) { $('scan-status').textContent = error.message; } }, 2000);
