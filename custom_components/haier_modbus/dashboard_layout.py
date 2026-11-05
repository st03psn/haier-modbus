"""Layout des mitgelieferten Dashboards (ab v2.0.0, eine Seite, zweisprachig).

Aufbau in drei Spalten (Sections-Ansicht):
  1. Speicher   – Speicher-Grafik (button-card) mit Status- und Diagnose-Leiste
  2. Betrieb    – Schalter, Soll + Modus, PV-Regelung (nur mit PV), Regelverlauf,
                  Effizienz (JAZ/COP-Karte, button-card)
  3. Verlauf    – Temperaturen + Laufzeiten (7 Tage), Energie pro Tag/Monat

Die Vorlage arbeitet mit Platzhaltern, die ``build_layout`` ersetzt:
  ``@E:<domain>.<key>@``  -> real aufgelöste entity_id (Registry, unique_id
                             ``<entry_id>_<key>``); nicht auffindbar -> ""
  ``§<name>§``            -> Text in der HA-Sprache (``_TEXT``, de/en)
Karten, deren Entität fehlt (z. B. deaktiviert), werden danach entfernt.
Texte dürfen weder ``'`` noch ``"`` oder ``\\`` enthalten (sie landen in
JS-Strings bzw. JSON).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

# --- Texte -------------------------------------------------------------------
_TEXT: dict[str, dict[str, str]] = {
    "de": {
        "view": "Brauchwasser", "tank": "Speicher", "operation": "Betrieb",
        "hot_water": "Warmwasser", "active": "Betrieb", "boost": "Boost",
        "mute": "Leise", "sterilize": "Sterilisation", "pv_control": "PV-Regelung",
        "pv": "PV", "control_log": "Regelverlauf", "efficiency": "Effizienz",
        "cop_card": "Jahresarbeitszahl & COP", "history": "Verlauf (7 Tage)",
        "energy_day": "Energie pro Tag (30 Tage)", "energy_month": "Energie pro Monat",
        "water": "Wasser", "tank_top": "Tank oben", "tank_bottom": "Tank unten",
        "setpoint": "Soll", "heat_pump": "Wärmepumpe", "heater": "Heizstab",
        "mode": "Modus", "heat": "Wärme", "elec": "Strom",
        # JS-Texte
        "top": "oben", "bottom": "unten", "running": "läuft", "off": "aus",
        "on": "an", "is_active": "aktiv", "unit_off": "Gerät aus",
        "solar": "Solar", "ext_source": "Externe Wärmequelle", "control": "Regelung",
        "emergency": "Notheizung", "legionella_run": "Legionellen-Lauf",
        "unit": "Gerät", "legionella": "Legionellen", "next": "nächste",
        "ambient": "Umgebung", "modbus": "Modbus", "fault": "Fehler",
        "clock": "Geräteuhr", "ready": "bereit", "jaz": "JAZ", "ytd": "lfd.",
        "cop_month": "COP Monat", "cop_per_month": "COP pro Monat",
        "jaz_per_year": "JAZ pro Jahr",
        "dash_update": "Dashboard-Update verfügbar",
        "ok": "OK", "emergency_short": "Notheizung", "pv_program": "PV-Programm",
        "confirm_active": "Betrieb der Wärmepumpe wirklich umschalten?",
        "confirm_boost": "Boost (Wärmepumpe + Heizstab) wirklich umschalten?",
        "confirm_mute": "Leise-Modus wirklich umschalten?",
        "confirm_sterilize": "Sterilisation wirklich umschalten?",
        "dash_compare": "Neu zum Vergleich anlegen", "dash_promote": "Vergleich übernehmen",
        "dash_promote_confirm": "Das Vergleichs-Dashboard (inkl. deiner Änderungen daran) ersetzt das Haier-Dashboard. Fortfahren?",
        "cop_note": "COP/JAZ vermutlich zu hoch (Geräteregister) – Korrektur folgt",
    },
    "en": {
        "view": "Hot water", "tank": "Tank", "operation": "Operation",
        "hot_water": "Hot water", "active": "Operation", "boost": "Boost",
        "mute": "Quiet", "sterilize": "Sterilisation", "pv_control": "PV control",
        "pv": "PV", "control_log": "Control log", "efficiency": "Efficiency",
        "cop_card": "Seasonal & monthly COP", "history": "History (7 days)",
        "energy_day": "Energy per day (30 days)", "energy_month": "Energy per month",
        "water": "Water", "tank_top": "Tank top", "tank_bottom": "Tank bottom",
        "setpoint": "Setpoint", "heat_pump": "Heat pump", "heater": "Heater",
        "mode": "Mode", "heat": "Heat", "elec": "Electricity",
        "top": "top", "bottom": "bottom", "running": "running", "off": "off",
        "on": "on", "is_active": "active", "unit_off": "Unit off",
        "solar": "Solar", "ext_source": "External heat source", "control": "Control",
        "emergency": "Emergency heating", "legionella_run": "Legionella run",
        "unit": "Unit", "legionella": "Legionella", "next": "next",
        "ambient": "Ambient", "modbus": "Modbus", "fault": "Fault",
        "clock": "Device clock", "ready": "ready", "jaz": "SCOP", "ytd": "YTD",
        "cop_month": "COP month", "cop_per_month": "COP per month",
        "jaz_per_year": "SCOP per year",
        "dash_update": "Dashboard update available",
        "ok": "OK", "emergency_short": "Emergency", "pv_program": "PV program",
        "confirm_active": "Really switch heat pump operation?",
        "confirm_boost": "Really switch boost (heat pump + heater)?",
        "confirm_mute": "Really switch quiet mode?",
        "confirm_sterilize": "Really switch sterilisation?",
        "dash_compare": "Create new for comparison", "dash_promote": "Adopt comparison",
        "dash_promote_confirm": "The comparison dashboard (incl. your changes to it) replaces the Haier dashboard. Continue?",
        "cop_note": "COP/SCOP likely too high (device register) – fix planned",
    },
}

# --- JS-Bausteine (button-card) --------------------------------------------
_JS_TANK = (
    "[[[ const n = (id) => parseFloat(states[id] ? states[id].state : NaN); "
    "const top = n('@E:sensor.tank_top@'); const bot = n('@E:sensor.tank_bottom@'); "
    "const water = n('@E:sensor.water_temp@'); let pct = n('@E:sensor.hotwater_pct@'); "
    "if (isNaN(pct)) pct = 0; pct = Math.max(0, Math.min(100, pct)); "
    "const crit = n('@E:number.emergency_critical@'); const soll = n('@E:number.set_temp@'); "
    "const lo = isNaN(crit) ? 38 : crit; const hi = (isNaN(soll) || soll <= lo) ? lo + 12 : soll; "
    "const col = (t) => { if (isNaN(t)) return '#9e9e9e'; "
    "const x = Math.max(0, Math.min(1, (t - lo) / (hi - lo))); "
    "return `hsl(${Math.round(120 * x)},70%,42%)`; }; "
    "const fmt = (t) => isNaN(t) ? '–' : Math.round(t) + '°'; "
    "const X = 20, Y = 10, W = 110, H = 260, R = 36; const fy = Y + H * (1 - pct / 100); "
    "const lab = `style='fill:#fff;paint-order:stroke;stroke:rgba(0,0,0,.45);stroke-width:3px' text-anchor='middle'`; "
    "return `<svg viewBox='0 0 150 280' width='100%' height='100%' preserveAspectRatio='xMidYMid meet'>"
    "<defs><linearGradient id='hwhpG' x1='0' y1='1' x2='0' y2='0'>"
    "<stop offset='0%' stop-color='${col(bot)}'/><stop offset='100%' stop-color='${col(top)}'/>"
    "</linearGradient><clipPath id='hwhpC'><rect x='${X}' y='${Y}' width='${W}' height='${H}' rx='${R}'/>"
    "</clipPath></defs><rect x='${X}' y='${Y}' width='${W}' height='${H}' rx='${R}' "
    "style='fill:var(--secondary-background-color)'/><g clip-path='url(#hwhpC)'>"
    "<rect x='${X}' y='${fy}' width='${W}' height='${Y + H - fy}' fill='url(#hwhpG)'/></g>"
    "<rect x='${X}' y='${Y}' width='${W}' height='${H}' rx='${R}' "
    "style='fill:none;stroke:var(--divider-color);stroke-width:3'/>"
    "<text x='${X + W / 2}' y='${Y + 36}' font-size='15' ${lab}>§top§ ${fmt(top)}</text>"
    "<text x='${X + W / 2}' y='${Y + H / 2 + 6}' font-size='36' font-weight='600' ${lab}>${fmt(water)}</text>"
    "<text x='${X + W / 2}' y='${Y + H / 2 + 30}' font-size='15' ${lab}>${Math.round(pct)} %</text>"
    "<text x='${X + W / 2}' y='${Y + H - 20}' font-size='15' ${lab}>§bottom§ ${fmt(bot)}</text></svg>`; ]]]"
)

_JS_INFO = (
    "[[[ const st = (id) => states[id]; const s = (id) => st(id) ? st(id).state : ''; "
    "const on = (id) => s(id) === 'on'; "
    "const fmt = (id) => { const o = st(id); if (!o) return '–'; "
    "try { return hass.formatEntityState(o); } catch (e) { return o.state; } }; "
    "const wp = on('@E:binary_sensor.status_wp@'); const el = on('@E:binary_sensor.status_heater@'); "
    "const sol = on('@E:binary_sensor.status_solar@'); const boiler = on('@E:binary_sensor.status_boiler@'); "
    "const active = s('@E:switch.active@'); const boost = on('@E:switch.boost@'); "
    "const mute = on('@E:switch.mute@'); const steril = on('@E:switch.sterilize@'); "
    "const em = s('@E:sensor.emergency_status@') === 'forced'; "
    "const leg = ['due', 'running', 'holding'].includes(s('@E:sensor.legionella_status@')); "
    "const pv = s('@E:sensor.pv_status@'); "
    "let reg, regIcon = 'mdi:tune-variant', regCol = 'var(--primary-color)'; "
    "if (em) { reg = '§emergency§'; regIcon = 'mdi:fire-alert'; regCol = 'var(--deep-orange-color, #ff5722)'; } "
    "else if (leg) { reg = '§legionella_run§'; regIcon = 'mdi:bacteria'; regCol = 'var(--purple-color, #9c27b0)'; } "
    "else if (pv && pv !== 'off') { const p = st('@E:sensor.pv_status@'); "
    "const sw = p ? parseFloat(p.attributes.surplus_w) : NaN; "
    "reg = '§pv§: ' + fmt('@E:sensor.pv_status@') + (isNaN(sw) ? '' : ' · ' + Math.round(sw) + ' W'); "
    "regIcon = 'mdi:solar-power-variant'; regCol = 'var(--amber-color)'; } "
    "else { reg = '§unit§ (' + s('@E:select.mode@') + ')'; } "
    "const icon = (i, act, color, anim) => `<div style='width:34px;flex:0 0 34px;display:flex;justify-content:center'>"
    "<ha-icon icon='${i}' style='display:inline-flex;--mdc-icon-size:24px;"
    "color:${act ? color : 'var(--secondary-text-color)'};opacity:${act ? 1 : 0.55};"
    "${act && anim ? 'animation:' + anim : ''}'></ha-icon></div>`; "
    "const row = (ic, label, val, vcol) => `<div style='display:flex;align-items:center;gap:8px;margin:6px 0'>"
    "${ic}<div style='min-width:0;text-align:left'><div style='font-size:12px;line-height:14px;color:var(--secondary-text-color)'>"
    "${label}</div><div style='font-size:14px;line-height:18px;font-weight:500;white-space:normal;overflow-wrap:anywhere;"
    "${vcol ? 'color:' + vcol : ''}'>${val}</div></div></div>`; "
    "let out = ''; "
    "if (active === 'off') out += row(icon('mdi:power', true, 'var(--error-color)', ''), '§active§', '§unit_off§', 'var(--error-color)'); "
    "out += row(icon('mdi:fan', wp, 'var(--green-color)', 'hwhp-spin 2s linear infinite'), '§heat_pump§', wp ? '§running§' : '§off§') "
    "+ row(icon('mdi:lightning-bolt', el, 'var(--orange-color)', 'hwhp-pulse 1s ease-in-out infinite'), '§heater§', el ? '§on§' : '§off§'); "
    "if (sol) out += row(icon('mdi:solar-power', true, 'var(--amber-color)', ''), '§solar§', '§is_active§'); "
    "if (boiler) out += row(icon('mdi:water-boiler', true, 'var(--red-color)', ''), '§ext_source§', '§is_active§'); "
    "if (boost) out += row(icon('mdi:rocket-launch', true, 'var(--orange-color)', ''), '§boost§', '§is_active§'); "
    "if (mute) out += row(icon('mdi:volume-off', true, 'var(--blue-color, #2196f3)', ''), '§mute§', '§is_active§'); "
    "if (steril) out += row(icon('mdi:bacteria', true, 'var(--purple-color, #9c27b0)', ''), '§sterilize§', '§is_active§'); "
    "out += row(icon(regIcon, true, regCol, ''), '§control§', reg); "
    "const lo = st('@E:sensor.legionella_status@'); "
    "if (lo && lo.state !== 'off' && lo.attributes.next_due) { const nd = new Date(lo.attributes.next_due); "
    "if (!isNaN(nd)) out += row(icon('mdi:bacteria-outline', true, 'var(--purple-color, #9c27b0)', ''), '§legionella§', "
    "'§next§ ' + nd.toLocaleDateString(hass.language || 'en', {day: '2-digit', month: '2-digit'})); } "
    "out += row(icon('mdi:home-thermometer-outline', true, 'var(--primary-color)', ''), '§ambient§', fmt('@E:sensor.ambient@')); "
    "return out; ]]]"
)

_JS_DIAG = (
    "[[[ const st = (id) => states[id]; const s = (id) => st(id) ? st(id).state : ''; "
    "const fmt = (id) => { const o = st(id); if (!o) return '\u2013'; "
    "try { return hass.formatEntityState(o); } catch (e) { return o.state; } }; "
    "const ok = 'var(--success-color, #43a047)', warn = 'var(--warning-color, #ff9800)', err = 'var(--error-color, #db4437)'; "
    "const chip = (i, label, val, col) => `<div style='display:flex;align-items:center;gap:4px;min-width:0'>"
    "<ha-icon icon='${i}' style='display:inline-flex;--mdc-icon-size:16px;color:${col};flex:0 0 16px'></ha-icon>"
    "<div style='min-width:0;text-align:left'><div style='font-size:10px;line-height:12px;color:var(--secondary-text-color);"
    "white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>${label}</div>"
    "<div style='font-size:12px;line-height:15px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
    "${val}</div></div></div>`; "
    "const link = s('@E:sensor.link_status@'); const fo = st('@E:sensor.fault@'); "
    "const fraw = fo ? Number(fo.attributes.raw || 0) : 0; "
    "const fval = !fo ? '\u2013' : (fraw > 0 ? (fo.attributes.code || String(fraw)) : '§ok§'); "
    "const dr = parseFloat(s('@E:sensor.clock_drift@')); "
    "const clockBad = s('@E:binary_sensor.clock_drift_problem@') === 'on'; let drTxt = '\u2013'; "
    "if (!isNaN(dr)) { const a = Math.abs(dr); const sign = dr > 0 ? '+' : (dr < 0 ? '\u2212' : '\u00b1'); "
    "drTxt = a >= 60 ? sign + Math.round(a / 60) + ' min' : sign + Math.round(a) + ' s'; } "
    "const em = s('@E:sensor.emergency_status@'); "
    "const crit = Math.round(parseFloat(s('@E:number.emergency_critical@'))); "
    "return `<div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px 8px'>` "
    "+ chip(link === 'ok' ? 'mdi:lan-connect' : 'mdi:lan-disconnect', '§modbus§', link === 'ok' ? '§ok§' : fmt('@E:sensor.link_status@'), link === 'ok' ? ok : err) "
    "+ chip(fraw > 0 ? 'mdi:alert-circle' : 'mdi:check-circle-outline', '§fault§', fval, fraw > 0 ? err : ok) "
    "+ chip(clockBad ? 'mdi:clock-alert-outline' : 'mdi:clock-check-outline', '§clock§', drTxt, clockBad ? warn : ok) "
    "+ chip('mdi:fire-alert', '§emergency_short§', em === 'idle' && !isNaN(crit) ? '§ready§ <' + crit + '\u00b0' "
    ": fmt('@E:sensor.emergency_status@'), em === 'forced' ? warn : (em === 'disabled' ? 'var(--disabled-color)' : ok)) "
    "+ `</div>`; ]]]"
)

_JS_KPI = (
    "[[[ const y = states['@E:sensor.cop_year@']; const m = states['@E:sensor.cop_month@']; "
    "const lang = hass.language || 'en'; "
    "const num = (v, d) => { const f = parseFloat(v); return isNaN(f) ? '–' "
    ": f.toLocaleString(lang, {minimumFractionDigits: d, maximumFractionDigits: d}); }; "
    "const cy = new Date().getFullYear(); "
    "const k = (label, val, col) => `<div style='min-width:0'><div style='font-size:11px;line-height:14px;"
    "color:var(--secondary-text-color);white-space:nowrap'>${label}</div><div style='font-size:18px;line-height:24px;"
    "font-weight:600;white-space:nowrap;${col ? 'color:' + col : ''}'>${val}</div></div>`; "
    "return `<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:8px'>` "
    "+ k('§jaz§ ' + cy + ' (§ytd§)', num(y && y.state, 2), 'var(--green-color)') "
    "+ k('§cop_month§', num(m && m.state, 2), 'var(--light-green-color, #8bc34a)') "
    "+ k('§heat§ ' + cy, num(y && y.attributes.heat_kwh, 0) + ' kWh') "
    "+ k('§elec§ ' + cy, num(y && y.attributes.electricity_kwh, 0) + ' kWh') "
    "+ (y && y.attributes.heat_source === 'modbus' ? `<div style='grid-column:1/-1;display:flex;gap:6px;justify-content:flex-start;"
    "align-items:flex-start;font-size:11px;line-height:14px;color:var(--warning-color, #ff9800);text-align:left;white-space:normal'>"
    "<ha-icon icon='mdi:alert-outline' style='--mdc-icon-size:14px;flex:0 0 14px'></ha-icon><span style='flex:1 1 auto;min-width:0;text-align:left'>§cop_note§</span></div>` : '') "
    "+ `</div>`; ]]]"
)

# Säulengrafik (Monate bzw. Jahre); ``{SRC}``/``{TITLE}``/``{MIN}``/``{DIGITS}``
# werden in Python gesetzt, damit beide Grafiken denselben Zeichencode teilen.
_JS_BARS_TAIL = (
    "if (ks.length < {MIN}) return ''; "
    "const max = Math.max(5, Math.ceil(Math.max(...ks.map((k) => d[k])))); "
    "const W = 300, H = 130, L = 18, B = 20, T = 18; const cw = (W - L - 4) / ks.length; "
    "const bw = Math.min({BW}, cw * 0.55); let g = ''; "
    "for (let i = 0; i <= max; i++) { const yy = H - B - (H - B - T) * i / max; "
    "g += `<line x1='${L}' x2='${W - 2}' y1='${yy}' y2='${yy}' style='stroke:var(--divider-color);stroke-width:0.5'/>"
    "<text x='${L - 5}' y='${yy + 3}' font-size='8' text-anchor='end' style='fill:var(--secondary-text-color)'>${i}</text>`; } "
    "let b = ''; ks.forEach((k, i) => { const v = d[k]; const x = L + 2 + cw * i + (cw - bw) / 2; "
    "const bh = (H - B - T) * v / max; const yy = H - B - bh; const cur = k === ck; "
    "b += `<rect x='${x}' y='${yy}' width='${bw}' height='${bh}' rx='3' "
    "style='fill:${cur ? 'var(--light-green-color, #8bc34a)' : 'var(--green-color, #4caf50)'}'/>"
    "<text x='${x + bw / 2}' y='${yy - 4}' font-size='9' font-weight='600' text-anchor='middle' "
    "style='fill:var(--primary-text-color)'>${v.toLocaleString(lang, {minimumFractionDigits: {DIGITS}, "
    "maximumFractionDigits: {DIGITS}})}</text><text x='${x + bw / 2}' y='${H - 6}' font-size='9' "
    "text-anchor='middle' style='fill:var(--secondary-text-color)'>${lbl(k, cur)}</text>`; }); "
    "return `<div style='font-size:12px;color:var(--secondary-text-color);margin:6px 0 2px'>{TITLE}</div>"
    "<svg viewBox='0 0 ${W} ${H}' width='100%' preserveAspectRatio='xMidYMid meet'>${g}${b}</svg>`; ]]]"
)

_JS_MONTHS = (
    "[[[ const m = states['@E:sensor.cop_month@']; if (!m) return ''; const lang = hass.language || 'en'; "
    "const h = m.attributes.cop_per_month || {}; const d = {}; "
    "Object.keys(h).forEach((k) => { const v = parseFloat(h[k] && h[k].cop); if (!isNaN(v)) d[k] = v; }); "
    "const now = new Date(); const ck = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0'); "
    "const cv = parseFloat(m.state); if (!isNaN(cv)) d[ck] = cv; const ks = Object.keys(d).sort().slice(-12); "
    "const lbl = (k, cur) => new Date(Number(k.slice(0, 4)), Number(k.slice(5, 7)) - 1, 1)"
    ".toLocaleDateString(lang, {month: 'short'}); "
    + _JS_BARS_TAIL.replace("{MIN}", "1").replace("{BW}", "26").replace("{DIGITS}", "1")
    .replace("{TITLE}", "§cop_per_month§")
)

_JS_YEARS = (
    "[[[ const e = states['@E:sensor.cop_year@']; if (!e) return ''; const lang = hass.language || 'en'; "
    "const h = e.attributes.jaz_per_year || {}; const d = {}; "
    "Object.keys(h).forEach((y) => { const v = parseFloat(h[y] && h[y].cop); if (!isNaN(v)) d[y] = v; }); "
    "const ck = String(new Date().getFullYear()); const cv = parseFloat(e.state); if (!isNaN(cv)) d[ck] = cv; "
    "const ks = Object.keys(d).sort(); const lbl = (k, cur) => k + (cur ? ' (§ytd§)' : ''); "
    + _JS_BARS_TAIL.replace("{MIN}", "2").replace("{BW}", "34").replace("{DIGITS}", "2")
    .replace("{TITLE}", "§jaz_per_year§")
)

_KEYFRAMES = (
    "@keyframes hwhp-pulse {0%,100% {opacity:1; transform:scale(1);} 50% {opacity:.45; transform:scale(.88);}} "
    "@keyframes hwhp-spin {from {transform:rotate(0deg);} to {transform:rotate(360deg);}}"
)


def _tile(entity: str, name: str, **extra) -> dict:
    card = {"type": "tile", "entity": entity, "name": name}
    card.update(extra)
    return card


def _template(with_pv: bool, executor: bool, settings_path: str) -> dict:
    """Dashboard mit Platzhaltern (siehe Modul-Docstring)."""
    pv_vis = [{"condition": "state", "entity": "@E:sensor.pv_status@", "state_not": "off"}]
    def toggle(confirm_key: str) -> dict:
        # Schalten nur nach Rückfrage – ein versehentlicher Tipp soll das Gerät
        # nicht ausschalten oder Boost/Sterilisation auslösen.
        action = {"action": "toggle", "confirmation": {"text": f"§{confirm_key}§"}}
        return {"tap_action": action, "icon_tap_action": dict(action),
                "grid_options": {"columns": 6}}

    tank_card = {
        "type": "custom:button-card",
        "entity": "@E:sensor.water_temp@",
        "show_name": False, "show_icon": False, "show_state": False,
        "tap_action": {"action": "more-info", "entity": "@E:water_heater.water_heater@"},
        "triggers_update": [
            "@E:sensor.tank_top@", "@E:sensor.tank_bottom@", "@E:sensor.hotwater_pct@",
            "@E:binary_sensor.status_wp@", "@E:binary_sensor.status_heater@",
            "@E:binary_sensor.status_solar@", "@E:binary_sensor.status_boiler@",
            "@E:sensor.ambient@", "@E:select.mode@", "@E:sensor.pv_status@",
            "@E:sensor.legionella_status@", "@E:sensor.emergency_status@",
            "@E:switch.active@", "@E:switch.boost@", "@E:switch.mute@", "@E:switch.sterilize@",
            "@E:sensor.fault@", "@E:sensor.link_status@", "@E:sensor.clock_drift@",
            "@E:binary_sensor.clock_drift_problem@", "@E:number.emergency_critical@",
            "@E:number.set_temp@",
        ],
        "extra_styles": _KEYFRAMES,
        "styles": {
            "card": [{"padding": "8px 12px"}, {"min-height": "340px"}],
            "grid": [{"grid-template-areas": '"tank info" "diag diag"'},
                     {"grid-template-columns": "52% 48%"}, {"grid-template-rows": "auto auto"}],
            "custom_fields": {
                "tank": [{"height": "324px"}, {"width": "100%"}],
                "info": [{"justify-self": "stretch"}, {"align-self": "center"},
                         {"text-align": "left"}, {"padding-left": "4px"}, {"overflow": "hidden"}],
                "diag": [{"justify-self": "stretch"}, {"padding-top": "8px"}, {"margin-top": "4px"},
                         {"border-top": "1px solid var(--divider-color)"}],
            },
        },
        "custom_fields": {"tank": _JS_TANK, "info": _JS_INFO, "diag": _JS_DIAG},
    }

    cop_card = {
        "type": "custom:button-card",
        "entity": "@E:sensor.cop_year@",
        "name": "§cop_card§",
        "show_icon": False, "show_state": False, "show_name": True,
        "tap_action": {"action": "more-info"},
        "triggers_update": ["@E:sensor.cop_month@"],
        "styles": {
            "card": [{"padding": "12px"}],
            "grid": [{"grid-template-areas": '"n" "kpi" "months" "years"'},
                     {"grid-template-columns": "100%"},
                     {"grid-template-rows": "min-content min-content auto auto"}],
            "name": [{"justify-self": "start"}, {"font-size": "14px"}, {"font-weight": "500"},
                     {"padding-bottom": "6px"}],
            "custom_fields": {"kpi": [{"width": "100%"}, {"padding-bottom": "8px"}],
                              "months": [{"width": "100%"}], "years": [{"width": "100%"}]},
        },
        "custom_fields": {"kpi": _JS_KPI, "months": _JS_MONTHS, "years": _JS_YEARS},
        "grid_options": {"columns": "full"},
    }

    operation = [
        {"type": "heading", "heading": "§operation§", "icon": "mdi:state-machine",
         "badges": ([{"type": "entity", "entity": "@E:sensor.pv_status@", "name": "§pv§",
                      "show_name": True, "color": "amber", "visibility": pv_vis}]
                    if with_pv else [])},
        _tile("@E:switch.active@", "§active§", **toggle("confirm_active")),
        _tile("@E:switch.boost@", "§boost§", icon="mdi:rocket-launch", color="orange",
              **toggle("confirm_boost")),
        _tile("@E:switch.mute@", "§mute§", icon="mdi:volume-off", **toggle("confirm_mute")),
        _tile("@E:switch.sterilize@", "§sterilize§", icon="mdi:bacteria",
              **toggle("confirm_sterilize")),
        # Bedienung klein im selben 2er-Raster wie die Schalter
        _tile("@E:water_heater.water_heater@", "§setpoint§", icon="mdi:thermometer-water",
              hide_state=True, features_position="bottom", grid_options={"columns": 6},
              features=[{"type": "target-temperature"}]),
        _tile("@E:select.mode@", "§mode§", hide_state=True, features_position="bottom",
              grid_options={"columns": 6}, features=[{"type": "select-options"}]),
    ]
    if executor:
        # Executor (HEMS, z. B. evcc): das Programm-Select ist das zentrale Bedienelement.
        operation.append(_tile("@E:select.pv_program@", "§pv_program§", icon="mdi:solar-power-variant",
                               hide_state=True, features_position="bottom",
                               features=[{"type": "select-options"}], grid_options={"columns": 12}))
    if with_pv and not executor:
        operation.append(_tile("@E:sensor.pv_status@", "§pv_control§", icon="mdi:solar-power-variant",
                               color="amber", state_content="state", visibility=pv_vis,
                               grid_options={"columns": 12}))
    log_entities = ["@E:number.set_temp@", "@E:select.mode@", "@E:switch.boost@",
                    "@E:sensor.legionella_status@", "@E:sensor.emergency_status@"]
    if with_pv:
        log_entities.append("@E:sensor.pv_status@")
    operation += [
        {"type": "logbook", "title": "§control_log§", "hours_to_show": 48,
         "entities": log_entities, "grid_options": {"columns": 12}},
        {"type": "heading", "heading": "§efficiency§", "icon": "mdi:gauge"},
        cop_card,
    ]

    energy_series = [
        {"entity": "@E:sensor.total_heat@", "name": "§heat§", "color": "#f4511e"},
        {"entity": "@E:sensor.total_elec@", "name": "§elec§", "color": "#1e88e5"},
    ]
    history = [
        {"type": "heading", "heading": "§history§", "icon": "mdi:chart-line"},
        {"type": "history-graph", "hours_to_show": 168, "grid_options": {"columns": "full"},
         "entities": [
             {"entity": "@E:sensor.water_temp@", "name": "§water§", "color": "#e53935"},
             {"entity": "@E:sensor.tank_top@", "name": "§tank_top§", "color": "#fb8c00"},
             {"entity": "@E:sensor.tank_bottom@", "name": "§tank_bottom§", "color": "#1e88e5"},
             {"entity": "@E:number.set_temp@", "name": "§setpoint§", "color": "#9e9e9e"},
         ]},
        # Laufzeiten bewusst als eigene Karte: in einer gemeinsamen Karte richtet
        # HA die Temperaturkurve an der breitesten Leisten-Beschriftung aus und
        # verschenkt links Platz.
        {"type": "history-graph", "hours_to_show": 168, "grid_options": {"columns": "full"},
         "entities": [
             {"entity": "@E:binary_sensor.status_wp@", "name": "§heat_pump§"},
             {"entity": "@E:binary_sensor.status_heater@", "name": "§heater§"},
             {"entity": "@E:select.mode@", "name": "§mode§"},
         ]},
        {"type": "heading", "heading": "§energy_day§", "icon": "mdi:chart-bar"},
        {"type": "statistics-graph", "chart_type": "bar", "days_to_show": 30, "period": "day",
         "stat_types": ["change"], "entities": energy_series,
         "grid_options": {"columns": "full", "rows": 5}},
        {"type": "heading", "heading": "§energy_month§", "icon": "mdi:calendar-month"},
        {"type": "statistics-graph", "chart_type": "bar", "days_to_show": 365, "period": "month",
         "stat_types": ["change"], "entities": [dict(s) for s in energy_series],
         "grid_options": {"columns": "full", "rows": 4}},
    ]

    tank_section = [
        {"type": "heading", "heading": "§tank§", "icon": "mdi:water-boiler",
         "badges": [{"type": "button", "icon": "mdi:cog",
                     "tap_action": {"action": "navigate", "navigation_path": settings_path}}]},
        # Nur sichtbar, wenn ein neueres Layout bereitsteht (angepasstes Dashboard,
        # das nicht automatisch erneuert werden durfte) – direkt hier installierbar.
        _tile("@E:update.dashboard@", "§dash_update§", icon="mdi:view-dashboard-edit-outline",
              color="amber", features=[{"type": "update-actions"}], features_position="bottom",
              visibility=[{"condition": "state", "entity": "@E:update.dashboard@", "state": "on"}],
              grid_options={"columns": 12}),
        _tile("@E:button.dashboard_compare@", "§dash_compare§", icon="mdi:view-dashboard-variant-outline",
              tap_action={"action": "perform-action", "perform_action": "button.press",
                          "target": {"entity_id": "@E:button.dashboard_compare@"}},
              visibility=[{"condition": "state", "entity": "@E:update.dashboard@", "state": "on"}],
              grid_options={"columns": 6}),
        _tile("@E:button.dashboard_promote@", "§dash_promote§", icon="mdi:check-decagram-outline",
              tap_action={"action": "perform-action", "perform_action": "button.press",
                          "target": {"entity_id": "@E:button.dashboard_promote@"},
                          "confirmation": {"text": "§dash_promote_confirm§"}},
              visibility=[{"condition": "state", "entity": "@E:button.dashboard_promote@",
                           "state_not": "unavailable"}],
              grid_options={"columns": 6}),
        tank_card,
    ]

    return {"views": [{
        "title": "§view§", "path": "home", "icon": "mdi:water-boiler",
        "type": "sections", "max_columns": 3,
        "sections": [
            {"type": "grid", "cards": tank_section},
            {"type": "grid", "cards": operation},
            {"type": "grid", "cards": history},
        ],
    }]}


_ENTITY_TOKEN = re.compile(r"@E:([a-z_]+)\.([a-z0-9_]+)@")
_TEXT_TOKEN = re.compile(r"§([a-z_]+)§")


def _prune(node):
    """Karten/Einträge ohne aufgelöste Entität (leerer String) entfernen."""
    if isinstance(node, dict):
        out = {}
        for key, val in node.items():
            if isinstance(val, list):
                pruned = [_prune(v) for v in val]
                pruned = [v for v in pruned if v is not None]
                # Fehlt eine Entität einer Sichtbarkeitsbedingung, wäre die Karte sonst
                # immer sichtbar -> dann die Karte selbst entfernen.
                if key == "visibility" and len(pruned) != len(val):
                    return None
                val = pruned
            elif isinstance(val, dict):
                val = _prune(val)
                if val is None:
                    continue  # z. B. tap_action ohne Entität: Schlüssel weglassen
            out[key] = val
        if out.get("entity") == "" and out.get("type") in (None, "tile", "entity", "custom:button-card"):
            return None
        if out.get("type") in ("logbook",) and not out.get("entities"):
            return None
        return out
    if isinstance(node, str):
        return None if node == "" else node
    return node


def text_for(language: str | None) -> dict[str, str]:
    lang = (language or "en").split("-")[0].lower()
    return _TEXT["de"] if lang == "de" else _TEXT["en"]


def build_layout(
    resolve: Callable[[str, str], str | None],
    language: str | None,
    with_pv: bool,
    settings_path: str,
    executor: bool = False,
) -> dict:
    """Fertige Dashboard-Konfiguration bauen.

    ``resolve(domain, key)`` liefert die entity_id zu ``<entry_id>_<key>`` oder None.
    """
    text = text_for(language)
    raw = json.dumps(_template(with_pv, executor, settings_path), ensure_ascii=False)
    raw = _ENTITY_TOKEN.sub(lambda m: resolve(m.group(1), m.group(2)) or "", raw)
    raw = _TEXT_TOKEN.sub(lambda m: text[m.group(1)], raw)
    return _prune(json.loads(raw))
