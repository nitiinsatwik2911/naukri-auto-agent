"""Screening-question chatbot: DOM inspection and form filling (Selenium DOM work lives here)."""
import logging
import os
from datetime import datetime

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from . import config
from .answers import match_option

logger = logging.getLogger(__name__)

DEBUG_DIR = config.data_path("debug_pages")


JS_COLLECT = r"""
document.querySelectorAll('[data-qa-idx]').forEach(e => e.removeAttribute('data-qa-idx'));
const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const skip = e => e.closest('header,nav,footer,[class*="nI-gNb"],[id*="gnb"]');
let n = 0;
const tag = e => { e.setAttribute('data-qa-idx', n); return n++; };
const bots = [...document.querySelectorAll('.chatbot_MessageContainer .botMsg')]
  .map(b => (b.innerText || '').trim()).filter(Boolean);
function questionOf(el, strip) {
  // Naukri chatbot: the question is the most recent bot message
  if (bots.length && el.closest('[class*="chatbot"], .singleselect-radiobutton, .footerWrapper'))
    return bots[bots.length - 1].slice(0, 300);
  const aria = el.getAttribute('aria-label');
  if (aria && aria.length > 5) return aria;
  let node = el.parentElement;
  for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
    let t = node.innerText || '';
    strip.forEach(s => { if (s) t = t.split(s).join(' '); });
    const lines = t.split('\n').map(x => x.trim()).filter(x => x.length > 2);
    if (lines.length) {
      const q = lines.filter(l => l.includes('?'));
      return (q.length ? q[q.length - 1] : lines[lines.length - 1]).slice(0, 300);
    }
  }
  return el.getAttribute('placeholder') || '';
}
function labelOf(el) {
  if (el.id) { const l = document.querySelector('label[for="' + el.id + '"]'); if (l) return l.innerText.trim(); }
  const l = el.closest('label'); if (l) return l.innerText.trim();
  return (el.parentElement ? el.parentElement.innerText : '').trim();
}
const out = [], groups = {};
document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach(el => {
  if (skip(el)) return;
  const type = (el.getAttribute('type') || '').toLowerCase();
  if (['hidden', 'file', 'submit', 'button', 'image', 'search'].includes(type)) return;
  if (/search/i.test(el.getAttribute('placeholder') || '')) return;
  if (type === 'radio' || type === 'checkbox') {
    const host = el.closest('label') || el.parentElement;
    if (!vis(el) && !(host && vis(host))) return;
    const key = type + ':' + (el.name || (el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.className : ''));
    (groups[key] = groups[key] || {kind: type, els: []}).els.push(el);
    return;
  }
  if (!vis(el) || el.disabled || el.readOnly) return;
  let kind = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.isContentEditable ? 'text' : (type === 'number' ? 'number' : 'text'));
  const options = kind === 'select' ? [...el.options].map(o => o.text.trim()).filter(t => t && !/^select/i.test(t)) : [];
  out.push({idx: tag(el), kind, question: questionOf(el, []), options, value: el.value || el.innerText || ''});
});
Object.values(groups).forEach(g => {
  const labels = g.els.map(labelOf);
  out.push({idx: g.els.map(tag), kind: g.kind, question: questionOf(g.els[0], labels), options: labels,
            value: g.els.some(e => e.checked) ? 'checked' : ''});
});
return out;
"""


JS_CLICK_SUBMIT = r"""
const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const re = /^(save|submit|submit and apply|next|send|continue|proceed|done|apply|apply now|confirm)\b/i;
const sendCls = /send|submit|save/i;
const c = [...document.querySelectorAll('button, [role="button"], input[type="submit"], [class*="sendMsg"], [class*="SendBtn"], [class*="sendBtn"]')]
  .filter(b => vis(b) && !b.disabled && !b.closest('header,nav,footer,[class*="nI-gNb"]')
               && (re.test((b.innerText || b.value || '').trim())
                   || (b.closest('[class*="chatbot"]') && sendCls.test(b.className || ''))));
const inBot = c.filter(b => b.closest('[class*="chatbot"]'));
const pick = inBot.length ? inBot : c;
if (!pick.length) return '';
const b = pick[pick.length - 1]; b.click(); return (b.innerText || b.value || b.className || '').trim();
"""


def collect_fields(driver):
    try:
        return driver.execute_script(JS_COLLECT) or []
    except WebDriverException as e:
        logger.debug(f"collect fields failed: {e}")
        return []


def _el(driver, idx):
    return driver.find_element(By.CSS_SELECTOR, f'[data-qa-idx="{idx}"]')


def fill_field(driver, field, answer):
    """Fill one field/group. Returns True if the answer could be applied."""
    kind, idx = field["kind"], field["idx"]
    if kind in ("text", "number", "textarea"):
        el = _el(driver, idx)
        el.click()
        try:
            el.clear()
        except WebDriverException:
            driver.execute_script("arguments[0].innerText='';", el)
        el.send_keys(answer)
        if kind == "text" and el.get_attribute("contenteditable") == "true":
            el.send_keys(Keys.ENTER)  # chatbot input sends on Enter
        return True
    if kind == "select":
        sel = Select(_el(driver, idx))
        i = match_option(answer, field["options"])
        if i < 0:
            return False
        sel.select_by_visible_text(field["options"][i])
        return True
    # radio / checkbox group: idx is a list; several checkbox answers separated by '|'
    wanted = [a for a in answer.split("|")] if kind == "checkbox" else [answer]
    picked = [match_option(a, field["options"]) for a in wanted]
    picked = sorted({i for i in picked if i >= 0})
    if not picked:
        return False
    for i in picked:
        el = _el(driver, idx[i])
        driver.execute_script(
            "const e=arguments[0]; const l=e.closest('label')||(e.id&&document.querySelector('label[for=\"'+e.id+'\"]'));"
            "(l||e).click(); if(!e.checked) e.click();", el)
    return True


def dump_debug(driver, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    try:
        with open(os.path.join(DEBUG_DIR, f"{name}_{stamp}.html"), "w", encoding="utf-8") as f:
            f.write(driver.execute_script("return document.documentElement.outerHTML"))
        driver.save_screenshot(os.path.join(DEBUG_DIR, f"{name}_{stamp}.png"))
    except WebDriverException:
        pass


def chat_open(driver):
    """True while Naukri's screening-question chatbot drawer is visible."""
    try:
        return bool(driver.execute_script(
            "return [...document.querySelectorAll('.chatbot_DrawerContentWrapper, .chatbot_MessageContainer')]"
            ".some(e => e.getBoundingClientRect().width > 0)"))
    except WebDriverException:
        return False


def chatbot_done(driver):
    try:
        return bool(driver.execute_script(
            "return [...document.querySelectorAll('.botMsg')].some("
            "b => /thank you for your responses|successfully applied|application (has been )?submitted/i.test(b.innerText))"))
    except WebDriverException:
        return False


def click_submit(driver):
    """Click the chatbot's Save/Submit/Send button; returns its label ('' if none found)."""
    return driver.execute_script(JS_CLICK_SUBMIT)
