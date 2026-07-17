"""
EPDK on-lisans scraper -- insan-destekli (human-in-the-loop).

Akis:
  1. Headed tarayici ac, Lisans Durumu=ONAYLANDI sec, rpp=50 ayarla.
  2. Kullanicinin captcha'yi cozup Sorgula'ya basmasini bekle (poll).
  3. Tum sayfalari gez; her lisans + tesis alanlarini oku.
  4. Artimli: yalnizca yeni/degisen tesis icin koordinat popup'ini ac (callback ile kontrol).
  5. Koordinat popup'i: dialog settle + retry (bilinen 'context destroyed' yarisini asar),
     tum poligon noktalarini (popup ici sayfalama dahil) oku.

Bu modul DB bilmiyor; ham dict uretir/callback'lerle konusur. Orkestrasyon sync_manager'da.
"""
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .config import settings
from .coords import tr_num

DURUM_TRIGGER = "#elektrikUretimOzetForm\\:lisansDurumu_INPUT"
DURUM_ONAYLANDI = "#elektrikUretimOzetForm\\:lisansDurumu_INPUT_3"  # Yururlukte
DURUM_LABEL = "#elektrikUretimOzetForm\\:lisansDurumu_INPUT_label"
SORGULA = "#elektrikUretimOzetForm\\:j_idt61"
RESULT_TABLE = "#elektrikUretimOzetSorguSonucu\\:list"
PAGINATOR_CURRENT = ".ui-paginator-current"
PAGINATOR_NEXT = "#elektrikUretimOzetSorguSonucu\\:list_paginator_bottom .ui-paginator-next"
RPP_SELECT = "select[name='elektrikUretimOzetSorguSonucu:list_rppDD']"
DIALOG = "#elektrikKoordinatViewDialog"
DIALOG_CONTENT = "#elektrikKoordinatViewDialog_content"
COORD_ROWS = "#elektrikKoordinatViewDataTable_data > tr"
COORD_NEXT = "#elektrikKoordinatViewDataTable_paginator_bottom .ui-paginator-next"
COORD_RPP = "#elektrikKoordinatViewDataTable_paginator_bottom select.ui-paginator-rpp-options"
COORD_CLOSE = DIALOG + " .ui-dialog-titlebar-close"


# JS: gorunur sonuc sayfasindaki lisans+tesis satirlarini yapili cikar
PARSE_PAGE_JS = r"""
() => {
  const rows = Array.from(document.querySelectorAll(
    "#elektrikUretimOzetSorguSonucu\\:list_data > tr, "
    + "#elektrikUretimOzetSorguSonucu\\:list > .ui-datatable-tablewrapper > table > tbody > tr"));
  const out = [];
  for (const tr of rows) {
    if (/Kay.t Bulunamad/i.test(tr.innerText)) continue;
    const tds = Array.from(tr.children);
    if (tds.length < 10) continue;
    const lic = {
      unvan: tds[0].innerText.trim(),
      iletisim_adresi: tds[1].innerText.trim(),
      telefon: tds[2].innerText.trim(),
      lisans_durumu: tds[3].innerText.trim(),
      iptal_tarihi: tds[4].innerText.trim(),
      iptal_aciklama: tds[5].innerText.trim(),
      lisans_no: tds[6].innerText.trim(),
      baslangic_tarihi: tds[7].innerText.trim(),
      bitis_tarihi: tds[8].innerText.trim(),
      facilities: []
    };
    const facRows = tds[9].querySelectorAll("[id*='TesisBilgileriDataTable_data'] > tr");
    for (const fr of facRows) {
      if (/Kay.t Bulunamad/i.test(fr.innerText)) continue;
      const c = Array.from(fr.children);
      if (c.length < 14) continue;
      // Koordinat butonlarini TUM tesis satirinda ara. DIKKAT: bazi tesislerde
      // (ozellikle DEPOLAMALI RES/DRES) BIRDEN COK koordinat butonu var (orn.
      // RES sahasi + depolama alani -> ayri 'U' ve 'K' serileri). HEPSINI topla,
      // yoksa ikinci set eksik kalir.
      const btnEls = Array.from(fr.querySelectorAll("button[id*='j_idt']"));
      if (!btnEls.length) {
        const b2 = (c[13] && c[13].querySelector("button")) || fr.querySelector("button");
        if (b2) btnEls.push(b2);
      }
      const btnIds = btnEls.map(b => b.id).filter(Boolean);
      lic.facilities.push({
        tesis_adi: c[0].innerText.trim(),
        il: c[1].innerText.trim(),
        ilce: c[2].innerText.trim(),
        tesis_turu: c[3].innerText.trim(),
        kaynak_turu: c[4].innerText.trim(),
        kurulu_guc_mwm: c[5].innerText.trim(),
        kurulu_guc_mwe: c[6].innerText.trim(),
        isletme_kapasite_mwm: c[7].innerText.trim(),
        isletme_kapasite_mwe: c[8].innerText.trim(),
        depolama_kapasite_mwh: c[9].innerText.trim(),
        depolama_kurulu_guc_mwe: c[10].innerText.trim(),
        isletme_depolama_kapasite_mwh: c[11].innerText.trim(),
        isletme_depolama_kurulu_guc_mwe: c[12].innerText.trim(),
        coord_btn_id: btnIds.length ? btnIds[0] : null,  // geriye uyumluluk
        coord_btn_ids: btnIds                            // TUM butonlar (cok-setli)
      });
    }
    out.push(lic);
  }
  return out;
}
"""


class BlockedError(Exception):
    """WAF/guvenlik-duvari IP engellemesi. Sunucu CEVAP verir ama koordinat
    yerine 'Your Access To This Page Has Been Blocked!' sayfasi doner. Oturum
    /ViewState saglam; cozum captcha degil, blogun gecmesini BEKLEMEK."""


class BlockPersists(Exception):
    """WAF engellemesi tum geri-cekilme beklemelerine ragmen gecmedi; calismayi
    'partial' bitir, IP blogu tamamen gecince (sonraki tur) kaldigi yerden devam."""


class CaptchaInvalid(Exception):
    """Sunucu istegi reCAPTCHA validasyonuna taktı ('Ben robot degilim' +
    validationFailed:true). Dialog BOS doner ama bu 'koordinat yok' DEGILDIR;
    oturum tazelenmeli (re-auth). Asla bos sonuc olarak kaydedilmemeli."""


def _is_validation_failed(text: str) -> bool:
    """PrimeFaces partial-response'ta form validasyonu patladi mi? (captcha vb.)
    Yanit gelir ama action calismaz -> dialog bos kalir. HTML-entity'li
    (&#34;validationFailed&#34;:true) ve duz JSON hallerini birlikte yakalar."""
    if not text:
        return False
    return bool(re.search(r'validationFailed[^:]{0,12}:\s*true', text)
                or re.search(r'robot\s*de[gğ]ilim', text, re.IGNORECASE))


def _is_block(text: str) -> bool:
    if not text:
        return False
    t = text[:1500]
    return ("Access To This Page Has Been Blocked" in t
            or "Your Access To This Page" in t
            or "Request ID:" in t and "IP Address:" in t)


@dataclass
class ScrapeCallbacks:
    log: Callable[[str], None] = lambda m: None
    on_status: Callable[[str], None] = lambda s: None          # durum degisimi
    # tesis icin koordinat cekilsin mi? (artimli karar) -> bool
    want_coords: Callable[[dict], bool] = lambda fac: True
    # bir sayfa parse edilince cagirilir (lisans listesi) -> kalici yaz
    on_page: Callable[[List[dict], int], None] = lambda lics, page: None
    should_stop: Callable[[], bool] = lambda: False
    start_page: int = 1


class EpdkScraper:
    def __init__(self, cb: ScrapeCallbacks, lisans_tipi: str = "onlisan"):
        self.cb = cb
        self.lisans_tipi = lisans_tipi
        self.url = settings.url_for(lisans_tipi)
        self._pw = None
        self._browser = None
        self.page = None
        self._buf = []          # yakalanan POST Response objeleri (koordinat AJAX)
        self._cap_on = False    # yakalama aktif mi
        self._form_params = None  # koordinat POST'u icin canli formdan serialize
        self._cur_page = 1      # dis tablo sayfa no (Python'da takip -> bozuk paginator'a guvenme)
        self._total_pages = 1

    # ---- yasam dongusu ----
    def start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=settings.headless)
        ctx = self._browser.new_context(locale="tr-TR")
        self.page = ctx.new_page()
        self.page.on("dialog", lambda d: d.dismiss())
        # POST yanit objelerini biriktir (text() BURADA cagirilmaz - handler'da tuketme sorunu)
        self.page.on("response", self._on_post)
        self.cb.log(f"Tarayici acildi ({self.lisans_tipi}), sayfaya gidiliyor...")
        self.page.goto(self.url, wait_until="networkidle", timeout=60000)

    def close(self):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ---- adimlar ----
    def select_filters(self) -> bool:
        """Lisans Durumu = Yururlukte (ONAYLANDI). force-click + dogrulama + retry.
        Basarisizsa kullaniciyi ELLE secmeye yonlendirir (buyuk uyari)."""
        for attempt in range(3):
            try:
                self.page.wait_for_selector(DURUM_TRIGGER, timeout=8000)
                time.sleep(0.3)
                self.page.click(DURUM_TRIGGER, force=True, timeout=6000)
                time.sleep(0.5)
                self.page.click(DURUM_ONAYLANDI, force=True, timeout=5000)
                time.sleep(0.3)
                lbl = self.page.eval_on_selector(DURUM_LABEL, "e => e ? e.innerText : ''") or ""
                if "rürlükte" in lbl or "rurlukte" in lbl.lower():
                    self.cb.log(f"Lisans Durumu -> {lbl}")
                    return True
            except Exception as e:
                self.cb.log(f"[!] Durum secme deneme {attempt+1}: {str(e)[:60]}")
            time.sleep(1.0)
        self.cb.log("[!!] Yururlukte OTOMATIK secilemedi -> LUTFEN acilan pencerede "
                    "acilir menuden ELLE 'Yururlukte' sec, SONRA Sorgula'ya bas.")
        return False

    def reauth_navigate(self):
        """Oturum dususunde: sayfayi yeniden ac + Yururlukte sec (captcha bekleme
        cagirani wait_for_captcha_and_results ile yapilir)."""
        self.page.goto(self.url, wait_until="networkidle", timeout=60000)
        self.select_filters()

    def _data_row_count(self) -> int:
        return self.page.eval_on_selector_all(
            RESULT_TABLE + " tbody tr",
            "els => els.filter(t => t.querySelectorAll('td').length>1 "
            "&& !/Kay.t Bulunamad/i.test(t.innerText)).length")

    def wait_for_captcha_and_results(self) -> bool:
        """Kullanici captcha cozup Sorgula'ya basana kadar bekle. True=sonuc geldi."""
        self.cb.on_status("waiting_captcha")
        self.cb.log(">>> Captcha'yi coz + Sorgula'ya bas. Bekleniyor...")
        deadline = settings.captcha_wait_timeout_s
        for _ in range(deadline):
            if self.cb.should_stop():
                return False
            try:
                if self._data_row_count() > 0:
                    self.cb.log("Sonuc tablosu doldu.")
                    self.capture_form_params()  # koordinat POST'u icin canli form
                    return True
            except Exception:
                pass
            time.sleep(1)
        self.cb.log("[!] Captcha zaman asimi (sonuc gelmedi).")
        return False

    def set_rows_per_page(self):
        try:
            self.page.select_option(RPP_SELECT, str(settings.rows_per_page), timeout=5000)
            self.page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(settings.request_delay_ms / 1000)
            self.cb.log(f"Sayfa basina kayit = {settings.rows_per_page}")
        except Exception as e:
            self.cb.log(f"[!] rpp ayarlanamadi: {e}")

    def total_pages(self) -> int:
        # Dis tablonun KENDI paginator'undan (scoped) oku; global .ui-paginator-current
        # baska bir bileseni yakalayip yanlis (orn. 198) verebiliyor.
        st = self._pag_state()
        tp = 1
        if st.get("ok") and st.get("totP"):
            tp = st["totP"]
        else:
            txt = self.page.eval_on_selector(
                PAGINATOR_CURRENT, "e => e ? e.innerText : ''") or ""
            m = re.search(r"Sayfa:\s*\d+\s*/\s*(\d+)", txt)
            tp = int(m.group(1)) if m else 1
        # Python sayacini ilklendir (sayfalama artik buna gore ilerler)
        self._total_pages = tp
        self._cur_page = st.get("curP", 1) or 1
        return tp

    def total_records(self) -> int:
        txt = self.page.eval_on_selector(
            PAGINATOR_CURRENT, "e => e ? e.innerText : ''") or ""
        m = re.search(r"Toplam Kay.t Say.s.:\s*(\d+)", txt)
        return int(m.group(1)) if m else 0

    # Dis tablonun PrimeFaces widget'ini bulup dogrudan hedef sayfaya atla
    # (tek AJAX; tik-tik tirmanmadan). Bulunamazsa/basarisizsa False.
    _JUMP_JS = r"""
    (target) => {
      const P = window.PrimeFaces;
      if (!P || !P.widgets) return false;
      const idx = target - 1;
      for (const k in P.widgets) {
        const w = P.widgets[k];
        if (!w) continue;
        const jid = String(w.jqId || w.id || k || '');
        if (jid.indexOf('elektrikUretimOzetSorguSonucu') < 0) continue;
        try {
          if (w.paginator && typeof w.paginator.setPage === 'function') {
            w.paginator.setPage(idx); return true;
          }
          if (typeof w.getPaginator === 'function') {
            const pg = w.getPaginator();
            if (pg && typeof pg.setPage === 'function') { pg.setPage(idx); return true; }
          }
          if (typeof w.paginate === 'function' && w.paginator && w.paginator.cfg) {
            const rows = w.paginator.cfg.rows || 50;
            w.paginate({ first: idx * rows, rows: rows, page: idx }); return true;
          }
        } catch (e) {}
      }
      return false;
    }
    """

    def _jump_to_page_fire(self, target: int) -> bool:
        """Widget setPage'i TETIKLE (bekleme yok; dogrulama next_page'de yapilir)."""
        try:
            return bool(self.page.evaluate(self._JUMP_JS, target))
        except Exception:
            return False

    def _jump_to_page(self, target: int) -> bool:
        try:
            if not self.page.evaluate(self._JUMP_JS, target):
                return False
            for _ in range(80):  # ~16s: uzak sayfa AJAX'i
                self.page.wait_for_timeout(200)
                if self._pag_state().get("curP") == target:
                    time.sleep(settings.request_delay_ms / 1000)
                    self.cb.log(f"Sayfa {target}'e dogrudan atlandi (tek istek).")
                    return True
            return False
        except Exception:
            return False

    def goto_page(self, target: int):
        """1-tabanli hedef sayfaya git. Once DOGRUDAN atla (tek istek); olmazsa
        tik-tik ilerle."""
        if target <= 1:
            return
        if self._jump_to_page(target):
            return
        self.cb.log(f"Dogrudan atlama olmadi, {target}. sayfaya tiklayarak gidiliyor...")
        for _ in range(target - 1):
            if not self.next_page():
                break

    def parse_current_page(self) -> List[dict]:
        return self.page.evaluate(PARSE_PAGE_JS)

    # Dis tablo paginator durumunu (scoped) oku: mevcut/toplam sayfa + next hali.
    # 'ui-state-disabled' class'ina GUVENME (rpp degisimi sonrasi gecici disabled
    # yaris hatasi olabilir); karari cur/tot sayfa no ile ver.
    _PAG_STATE_JS = r"""
    () => {
      const root = document.querySelector("#elektrikUretimOzetSorguSonucu\\:list_paginator_bottom")
                || document.querySelector("#elektrikUretimOzetSorguSonucu\\:list_paginator_top");
      if (!root) return {ok:false, reason:'paginator-yok'};
      let curP=0, totP=0;
      const cur = root.querySelector('.ui-paginator-current');
      if (cur) { const m = cur.innerText.match(/Sayfa:\s*(\d+)\s*\/\s*(\d+)/); if(m){curP=+m[1]; totP=+m[2];} }
      const nx = root.querySelector('.ui-paginator-next');
      return {ok:true, curP, totP,
              nextFound: !!nx,
              nextDisabled: nx ? nx.classList.contains('ui-state-disabled') : true,
              nextCls: nx ? nx.className : ''};
    }
    """

    def _pag_state(self) -> dict:
        try:
            return self.page.evaluate(self._PAG_STATE_JS) or {"ok": False}
        except Exception as e:
            return {"ok": False, "reason": str(e)[:80]}

    _WIDGET_DIAG_JS = r"""
    () => {
      const P = window.PrimeFaces;
      if (!P || !P.widgets) return 'PF/widgets yok';
      const out = [];
      for (const k in P.widgets) {
        const w = P.widgets[k]; if (!w) continue;
        const jid = String(w.jqId || w.id || k || '');
        if (jid.indexOf('elektrikUretimOzetSorguSonucu') >= 0)
          out.push(k+':'+jid+':pag='+(!!w.paginator)+':getPag='+(typeof w.getPaginator)+':paginate='+(typeof w.paginate));
      }
      return out.length ? out.join(' || ') : ('eslesme yok; ilk widgetlar: '+Object.keys(P.widgets).slice(0,12).join(','));
    }
    """

    def _widget_diag(self) -> str:
        try:
            return str(self.page.evaluate(self._WIDGET_DIAG_JS))[:400]
        except Exception as e:
            return f"hata: {str(e)[:60]}"

    # Bottom paginator'da hedef sayfa-numarasi linkine tikla (next butonundan
    # daha guvenilir; PF handler'i dogrudan calisir).
    _CLICK_PAGELINK_JS = r"""
    (t) => {
      const root = document.querySelector("#elektrikUretimOzetSorguSonucu\\:list_paginator_bottom")
                || document.querySelector("#elektrikUretimOzetSorguSonucu\\:list_paginator_top");
      if (!root) return false;
      const links = root.querySelectorAll('.ui-paginator-page');
      for (const a of links) { if (a.textContent.trim() === String(t)) { a.click(); return true; } }
      return false;
    }
    """

    def _click_next(self) -> bool:
        # Once gercek fare olayi (actionability); olmazsa JS click.
        try:
            self.page.click(PAGINATOR_NEXT, timeout=2000, no_wait_after=True)
            return True
        except Exception:
            try:
                self.page.eval_on_selector(PAGINATOR_NEXT, "e => { if(e) e.click(); }")
                return True
            except Exception:
                return False

    def _click_pagelink(self, target: int) -> bool:
        if not target:
            return False
        try:
            return bool(self.page.evaluate(self._CLICK_PAGELINK_JS, target))
        except Exception:
            return False

    # ---- DIS TABLO DOGRUDAN-POST SAYFALAMA ----
    # DOM tiklama uretim sayfasinda derin sayfalarda AJAX gondermiyor. Cozum:
    # sayfalama POST'unu DOGRUDAN gonder (her zaman gider), gelen gecerli list
    # HTML'ini canli DOM'a enjekte et. Sonuc formu 'elektrikUretimOzetSorguSonucu'.
    _OUTER = "elektrikUretimOzetSorguSonucu:list"
    _OUTER_FORM = "elektrikUretimOzetSorguSonucu"

    _SERIALIZE_FORM_BY_ID_JS = r"""
    (formId) => {
      const form = document.getElementById(formId);
      if (!form) return null;
      const out = [];
      for (const el of form.querySelectorAll('input,select,textarea')) {
        if (!el.name) continue;
        const t = (el.type || '').toLowerCase();
        if ((t === 'checkbox' || t === 'radio') && !el.checked) continue;
        if (el.name === 'javax.faces.ViewState') continue;
        out.push([el.name, el.value == null ? '' : el.value]);
      }
      return out;
    }
    """

    # Sayfalama yaniti SADECE <tr> satirlaridir (tbody icerigi) -> list_data
    # tbody'sinin icine koy. Tablo yapisi + paginator korunur; koordinat
    # butonlari (inline onclick) satirlarda gelir, tiklanabilir.
    _APPLY_LIST_JS = r"""
    (html) => {
      const tbody = document.getElementById('elektrikUretimOzetSorguSonucu:list_data');
      if (!tbody) return 'list_data tbody yok';
      tbody.innerHTML = html;
      return true;
    }
    """

    def _live_viewstate(self) -> str:
        try:
            return self.page.eval_on_selector(
                "input[name='javax.faces.ViewState']", "e => e ? e.value : ''") or ""
        except Exception:
            return ""

    def _direct_next(self, target: int, rows: int) -> bool:
        """Dis tabloyu DOGRUDAN-POST ile 'target' sayfasina getir + canli DOM'a
        uygula. DOM tiklama guvenilmez oldugu icin birincil yontem budur."""
        from urllib.parse import urlencode
        vs = self._live_viewstate()
        if not vs:
            return False
        pairs = self.page.evaluate(self._SERIALIZE_FORM_BY_ID_JS, self._OUTER_FORM)
        if pairs is None:
            return False
        params = {k: v for k, v in pairs}
        first = (target - 1) * rows
        params.update({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": self._OUTER,
            "javax.faces.partial.execute": self._OUTER,
            "javax.faces.partial.render": self._OUTER,
            self._OUTER: self._OUTER,
            self._OUTER + "_pagination": "true",
            self._OUTER + "_first": str(first),
            self._OUTER + "_rows": str(rows),
            self._OUTER + "_skipChildren": "true",
            self._OUTER + "_encodeFeature": "true",
            self._OUTER_FORM: self._OUTER_FORM,
            "javax.faces.ViewState": vs,
        })
        # ETIMEDOUT gibi gecici ag hatalarina karsi tekrar dene (uzun timeout)
        text = None
        for _try in range(3):
            try:
                resp = self.page.request.post(
                    self.url, data=urlencode(params), timeout=45000,
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                             "Faces-Request": "partial/ajax",
                             "X-Requested-With": "XMLHttpRequest",
                             "Referer": self.url})
                text = resp.text()
                break
            except Exception as e:
                if _try == 2:
                    self.cb.log(f"[!] liste POST 3 denemede basarisiz: {str(e)[:70]}")
                    return False
                self.page.wait_for_timeout(1500 * (_try + 1))
        if text is None:
            return False
        # TESHIS: ilk liste-POST yanitini diske yaz (format dogrulamak icin)
        if not getattr(self, "_dumped_list", False):
            self._dumped_list = True
            try:
                import os
                os.makedirs("teshis", exist_ok=True)
                with open("teshis/liste_yanit.txt", "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.cb.log("[TESHIS] Ilk liste-POST yaniti -> teshis/liste_yanit.txt")
            except Exception:
                pass
        if _is_block(text):
            raise BlockedError("WAF: erisim engellendi (liste sayfalama)")
        # list-update CDATA'sini cikar + canli DOM'a enjekte et
        m = re.search(
            r'<update id="elektrikUretimOzetSorguSonucu:list"><!\[CDATA\[(.*?)\]\]></update>',
            text, re.DOTALL)
        if not m:
            return False
        html = m.group(1)
        try:
            res = self.page.evaluate(self._APPLY_LIST_JS, html)
        except Exception as e:
            res = f"eval-hata: {str(e)[:60]}"
        if res is not True:
            if not getattr(self, "_diag_pf", False):
                self._diag_pf = True
                self.cb.log(f"[TESHIS enjekte] {res}")
            return False
        # taze ViewState'i canli input'a yaz (sonraki POST icin)
        nvs = self._extract_viewstate(text)
        if nvs:
            try:
                self.page.eval_on_selector(
                    "input[name='javax.faces.ViewState']",
                    "(e, v) => { if (e) e.value = v; }", nvs)
            except Exception:
                pass
        self.page.wait_for_timeout(300)  # DOM otursun (koordinat butonlari)
        return True

    def next_page(self) -> bool:
        """Python sayacina gore sonraki sayfaya gec: DOGRUDAN-POST + gelen list
        HTML'ini canli DOM'a enjekte (koordinat butonlari icin). DOM tiklama
        guvenilmez (uretim derin sayfalarda AJAX gondermiyor). Bozuk paginator'a
        guvenmeyiz -> sayfa no Python'da (_cur_page)."""
        if self._cur_page >= self._total_pages:
            return False
        target = self._cur_page + 1
        rows = settings.rows_per_page or 50
        if not getattr(self, "_diag_pag", False):
            self._diag_pag = True
            self.cb.log(f"[TESHIS] toplam_sayfa={self._total_pages} | "
                        f"widget: {self._widget_diag()[:160]}")
        # 1) BIRINCIL: dogrudan-POST + enjekte (her zaman istek gider)
        try:
            if self._direct_next(target, rows):
                self._cur_page = target
                return True
        except BlockedError:
            raise
        except Exception as e:
            self.cb.log(f"[!] dogrudan-POST hata: {str(e)[:80]}")
        # 2) YEDEK: DOM tiklama (onlisan yontemi)
        if self._dom_next(target):
            self._cur_page = target
            return True
        self.cb.log(f"[!] Sayfa {target}/{self._total_pages} getirilemedi.")
        return False

    def _dom_next(self, target: int) -> bool:
        """DOM tiklama yedegi: sayfa-no linki / next butonu + dogrulama."""
        cur = self._cur_page
        for attempt in range(3):
            if not self._click_pagelink(target):
                self._click_next()
            try:
                self.page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            for _ in range(40):  # ~8s
                self.page.wait_for_timeout(200)
                cp = self._pag_state().get("curP", 0)
                if cp == target or cp > cur:
                    time.sleep(settings.request_delay_ms / 1000)
                    return True
        return False

    def _diag_pag_response(self) -> str:
        """Yakalanan sayfalama POST yanitlarini incele: blok/hata/bos?"""
        bodies = []
        for r in list(self._buf):
            try:
                bodies.append(r.text())
            except Exception:
                pass
        if not bodies:
            return "[yanit=0 -> AJAX gitmedi/yakalanmadi]"
        joined = " ".join(bodies)
        if _is_block(joined):
            return "[WAF-BLOK: Access Blocked!]"
        if "ViewExpired" in joined or "viewExpired" in joined:
            return "[ViewExpiredException]"
        if "<error>" in joined or "exception" in joined.lower():
            return f"[HATA yaniti: {joined[:200]}]"
        # dis tablo update'i var mi?
        has_list = "elektrikUretimOzetSorguSonucu:list" in joined
        return f"[yanit={len(bodies)} listUpdate={has_list} ilk120={joined[:120].strip()}]"

    # ---- koordinat popup'i (AJAX-yakalama yaklasimi) ----
    # DOM'dan okumak yerine, sunucunun her tiklamaya verdigi AJAX yanitini
    # yakalayip koordinatlari ORADAN parse ederiz. Yanit = o tiklamanin tam
    # verisi; stale / eksik / durum-bozulmasi mumkun degil.
    # Kolon duzeni bu sitede SABIT: Ad | Dilim | E | N (fixture'larla dogrulandi).
    # HTML tam dialog (tablo+thead) VEYA sadece tbody satirlari (<tr>..) olabilir;
    # ciplak <tr> tarayici tarafindan atilmasin diye gerekiyorsa <table>'a sariyoruz.
    _READ_HTML_JS = r"""
    (html) => {
      const d = document.createElement('div');
      if (/<table/i.test(html)) d.innerHTML = html;
      else d.innerHTML = '<table><tbody>' + html + '</tbody></table>';
      const rows = [];
      for (const tr of Array.from(d.querySelectorAll('tr'))) {
        const tds = Array.from(tr.querySelectorAll(':scope > td'));
        if (tds.length < 4) continue;  // thead (th) ve bos satirlari atla
        const c = tds.map(td => td.innerText.trim());
        if (/Kay.t Bulunamad/i.test(c.join(' '))) continue;
        rows.push({ad: c[0], mer: c[1], e: c[2], n: c[3]});
      }
      const pg = d.querySelector('.ui-paginator-current');
      let total = 0;
      if (pg) { const m = pg.innerText.match(/Toplam Kay.t Say.s.:\s*(\d+)/); if (m) total = +m[1]; }
      return {found:true, total, rows};
    }
    """

    def _on_post(self, resp):
        """POST Response objelerini biriktir (yalnizca yakalama aciksa). text() YOK."""
        try:
            if self._cap_on and resp.request.method == "POST":
                self._buf.append(resp)
        except Exception:
            pass

    def _capture_raw(self, trigger, timeout: float = 15.0) -> str:
        """Tetikleyiciyi calistir, o eyleme ait koordinat AJAX yanitinin HAM
        govdesini dondur. Yanit yoksa None.

        KRITIK: Koordinat dialog'u 'dynamic:true' -> buton tiklamasi ONCE sadece
        dialog KABUGUnu (bos content) doner, koordinat verisi tarayicinin
        OTOMATIK 'contentLoad' istegiyle AYRI gelir. Bu yuzden kabukta ERKEN
        CIKMA; gercek DataTable icerigi (elektrikKoordinatViewDataTable_data:
        dolu YA DA 'Kayit Bulunamadi') gelene kadar bekle. Aksi halde dolu
        tesisler bos sanilir (KEBAN/KARAKAYA vb. yanlis 'koordinatsiz')."""
        self._cap_on = False
        self._buf = []
        self.page.wait_for_timeout(120)
        self._buf = []
        self._cap_on = True
        try:
            trigger()
        except Exception:
            pass
        best_body, best_rows = None, -1
        content_seen = False   # DataTable icerigi (contentLoad) geldi mi?
        last_any = None
        steps = int(timeout / 0.1)
        for _ in range(steps):
            self.page.wait_for_timeout(100)
            for r in list(self._buf):
                try:
                    body = r.text()
                except Exception:
                    continue
                if body:
                    last_any = body
                html = self._extract_coord_html(body)
                if not html:
                    continue
                # Gercek koordinat tablosu (contentLoad) DataTable_data icerir;
                # dialog kabugu icermez -> ayirt et.
                if "elektrikKoordinatViewDataTable_data" in html:
                    content_seen = True
                    nr = len(self._parse_html(html).get("rows", []))
                    if nr > best_rows:
                        best_rows, best_body = nr, body
            # Gercek icerik (dolu ya da 'Kayit Bulunamadi') geldiyse bitir.
            if content_seen and best_rows >= 0:
                # dolu ise hemen; bos ('Kayit Bulunamadi') ise bir tur daha
                # dolusu gelebilir mi diye kisa bekle, degilse cik.
                if best_rows > 0:
                    break
                # bos gorundu; 1 tur daha datatable dolusu gelmezse kabul et
                break
        self._last_bufcount = len(self._buf)
        self._last_fail_body = last_any if best_body is None else None
        self._last_blocked = bool(best_body is None and _is_block(last_any))
        self._cap_on = False
        return best_body

    @staticmethod
    def _extract_viewstate(text: str) -> str:
        m = re.search(r'<update id="[^"]*ViewState[^"]*"><!\[CDATA\[(.*?)\]\]></update>',
                      text or "", re.DOTALL)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_total(text: str) -> int:
        m = re.search(r"Toplam Kay.t Say.s.:\s*(\d+)", text or "")
        return int(m.group(1)) if m else 0

    # Koordinat datatable sayfalama bileseni (HER IKI sayfada ayni bilesen).
    # Form filtre alanlari (il, j_idt..., ONAYLANDI, ViewState) sayfaya gore
    # DEGISTIGI icin bunlar canli formdan DINAMIK serialize edilir (asagida).
    _COORD_PARAMS = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "elektrikKoordinatViewDataTable",
        "javax.faces.partial.execute": "elektrikKoordinatViewDataTable",
        "javax.faces.partial.render": "elektrikKoordinatViewDataTable",
        "elektrikKoordinatViewDataTable": "elektrikKoordinatViewDataTable",
        "elektrikKoordinatViewDataTable_pagination": "true",
        "elektrikKoordinatViewDataTable_skipChildren": "true",
        "elektrikKoordinatViewDataTable_encodeFeature": "true",
    }

    # Canli formu (elektrikUretimOzetForm) serialize et: name=value ciftleri.
    # ViewState haric (o ayri, taze gonderilir). Onlisan+uretim icin calisir.
    _SERIALIZE_FORM_JS = r"""
    () => {
      const form = document.getElementById('elektrikUretimOzetForm');
      if (!form) return [];
      const out = [];
      for (const el of form.querySelectorAll('input,select,textarea')) {
        if (!el.name) continue;
        const t = (el.type || '').toLowerCase();
        if ((t === 'checkbox' || t === 'radio') && !el.checked) continue;
        if (el.name === 'javax.faces.ViewState') continue;
        out.push([el.name, el.value == null ? '' : el.value]);
      }
      out.push(['elektrikUretimOzetForm', 'elektrikUretimOzetForm']);
      return out;
    }
    """

    def capture_form_params(self):
        """Sonuc yuklendikten sonra canli formu serialize edip sakla (koordinat
        POST'unda kullanilir). Re-auth sonrasi tekrar cagirilir."""
        try:
            pairs = self.page.evaluate(self._SERIALIZE_FORM_JS) or []
            self._form_params = {k: v for k, v in pairs}
        except Exception as e:
            self._form_params = {}
            self.cb.log(f"[!] form serialize edilemedi: {str(e)[:60]}")

    def _direct_page(self, first: int, rows: int, viewstate: str):
        """Sayfalama POST'unu DOGRUDAN gonder (DOM/tiklama YOK). (text, yeni_vs)."""
        from urllib.parse import urlencode
        params = dict(self._form_params or {})     # canli form (filtreler dahil)
        params.update(self._COORD_PARAMS)          # datatable sayfalama bileseni
        params["elektrikKoordinatViewDataTable_first"] = str(first)
        params["elektrikKoordinatViewDataTable_rows"] = str(rows)
        params["javax.faces.ViewState"] = viewstate
        resp = self.page.request.post(
            self.url, data=urlencode(params),
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                     "Faces-Request": "partial/ajax",
                     "X-Requested-With": "XMLHttpRequest",
                     "Referer": self.url})
        text = resp.text()
        if _is_block(text):
            raise BlockedError("WAF: erisim engellendi (sayfalama sirasinda)")
        return text, (self._extract_viewstate(text) or viewstate)

    def _direct_open_coord(self, btn_id: str) -> str:
        """Koordinat dialog'unu DOGRUDAN-POST ile ac (enjekte butona tiklamadan).
        Buton PrimeFaces.ab: s=btn, f=elektrikUretimOzetSorguSonucu, p=btn,
        u=elektrikKoordinatViewDialog. p=btn -> tam form gerekmez. Doner: ham yanit
        (koordinat dialog CDATA'si) veya None."""
        from urllib.parse import urlencode
        vs = self._live_viewstate()
        if not vs:
            return None
        # Facility'nin secilmesi icin tam form (ONAYLANDI vb.) + buton gonderilir.
        params = dict(self._form_params or {})          # elektrikUretimOzetForm
        params.update({
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": btn_id,
            "javax.faces.partial.execute": "@all",       # tum formu isle (secim tasinsin)
            "javax.faces.partial.render": "elektrikKoordinatViewDialog",
            btn_id: btn_id,
            "elektrikUretimOzetSorguSonucu": "elektrikUretimOzetSorguSonucu",
            "javax.faces.ViewState": vs,
        })
        text = None
        for _try in range(3):
            try:
                resp = self.page.request.post(
                    self.url, data=urlencode(params), timeout=45000,
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                             "Faces-Request": "partial/ajax",
                             "X-Requested-With": "XMLHttpRequest",
                             "Referer": self.url})
                text = resp.text()
                break
            except Exception:
                if _try == 2:
                    return None
                self.page.wait_for_timeout(1500 * (_try + 1))
        if text is None:
            return None
        # TESHIS: ilk koordinat-dialog yanitini diske yaz (bos donuyor -> neden?)
        if not getattr(self, "_dumped_coord", False):
            self._dumped_coord = True
            try:
                import os
                os.makedirs("teshis", exist_ok=True)
                with open("teshis/koord_yanit.txt", "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.cb.log("[TESHIS] Ilk koordinat-dialog yaniti -> teshis/koord_yanit.txt")
            except Exception:
                pass
        if _is_block(text):
            self._last_blocked = True
            return None
        self._last_blocked = False
        vs2 = self._extract_viewstate(text) or vs
        # Dialog 'dynamic:true' -> icerik (koordinat tablosu) AYRI istekle yuklenir.
        # contentLoad POST'u gonder; asil koordinat verisi bu yanittadir.
        content = self._direct_dialog_content(vs2)
        if content is None:
            return text  # en azindan kabuk (bos)
        return content

    def _direct_dialog_content(self, vs: str) -> str:
        """Dynamic koordinat dialog'unun icerigini yukle (contentLoad). Doner:
        koordinat datatable'i iceren ham yanit veya None."""
        from urllib.parse import urlencode
        dlg = "elektrikKoordinatViewDialog"
        params = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": dlg,
            dlg: dlg,
            dlg + "_contentLoad": "true",
            "javax.faces.partial.execute": dlg,
            "javax.faces.partial.render": dlg,
            "javax.faces.ViewState": vs,
        }
        text = None
        for _try in range(3):
            try:
                resp = self.page.request.post(
                    self.url, data=urlencode(params), timeout=45000,
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                             "Faces-Request": "partial/ajax",
                             "X-Requested-With": "XMLHttpRequest",
                             "Referer": self.url})
                text = resp.text()
                break
            except Exception:
                if _try == 2:
                    return None
                self.page.wait_for_timeout(1200 * (_try + 1))
        if text is None:
            return None
        # TESHIS: ilk contentLoad yanitini diske yaz (koordinat verisi burada mi?)
        if not getattr(self, "_dumped_content", False):
            self._dumped_content = True
            try:
                import os
                os.makedirs("teshis", exist_ok=True)
                with open("teshis/koord_content.txt", "w", encoding="utf-8") as fh:
                    fh.write(text)
                self.cb.log("[TESHIS] Ilk contentLoad yaniti -> teshis/koord_content.txt")
            except Exception:
                pass
        if _is_block(text):
            self._last_blocked = True
            return None
        nvs = self._extract_viewstate(text)
        if nvs:
            try:
                self.page.eval_on_selector(
                    "input[name='javax.faces.ViewState']",
                    "(e, v) => { if (e) e.value = v; }", nvs)
            except Exception:
                pass
        return text

    @staticmethod
    def _extract_coord_html(xml: str) -> str:
        """PrimeFaces partial-response'tan koordinat update'inin CDATA'sini cek.
        Update ID'sine gore secilir (icerige gore DEGIL): ilk tiklama tum dialog'u
        (id=...Dialog), sayfalama/rpp ise sadece tbody'yi (id=...DataTable_data) doner."""
        if not xml:
            return ""
        for m in re.finditer(
                r'<update id="([^"]+)"><!\[CDATA\[(.*?)\]\]></update>', xml, re.DOTALL):
            uid, content = m.group(1), m.group(2)
            if "elektrikKoordinatViewD" in uid:
                return content
        return ""

    def _parse_html(self, html: str) -> dict:
        if not html:
            return {"found": False, "total": 0, "rows": []}
        try:
            return self.page.evaluate(self._READ_HTML_JS, html)
        except Exception:
            return {"found": False, "total": 0, "rows": []}

    @staticmethod
    def _parse_rows(rows) -> List[dict]:
        pts = []
        for r in rows:
            m, e, n = tr_num(r.get("mer")), tr_num(r.get("e")), tr_num(r.get("n"))
            if m is not None and e is not None and n is not None:
                pts.append({"ad": r.get("ad"), "meridian": int(m), "E": e, "N": n})
        return pts

    ROWS_PER = 50  # dogrudan POST sayfa boyutu

    def fetch_coordinates(self, coord_btn_id: str) -> List[dict]:
        """TUM poligon noktalarini cek (sinir yok, DEDUP YOK).

        Yontem: butona tiklayarak tesisin koordinatlarini server-side datatable'a
        yukle + taze ViewState/total al; ardindan sayfalari 'next' TIKLAMADAN,
        sayfalama POST'unu DOGRUDAN gondererek cek (ViewState her yanitta tasinir).
        DOM/popup/tiklama kirilganligi yok. Ham satirlar dedup edilmeden korunur
        (poligon tekrar eden koseler icerebilir -> tam sayi = site 'total').
        """
        last_err = None
        for attempt in range(2):
            try:
                # 1) Butona TIKLA (onlisandaki calisan yontem; enjekte butonlar
                #    artik canli DOM'da). Buton PrimeFaces.ab -> dialog+contentLoad
                #    tarayicida dogru sekilde facility'yi secip yukler.
                raw = self._capture_raw(lambda: self.page.evaluate(
                    "(id) => { const b = document.getElementById(id); if (b) b.click(); }",
                    coord_btn_id))
                if raw is None:
                    if getattr(self, "_last_blocked", False):
                        raise BlockedError("WAF: erisim engellendi (Access Blocked)")
                    bc = getattr(self, "_last_bufcount", 0)
                    raise RuntimeError(f"koordinat yaniti gelmedi (gelen_post={bc})")
                self._last_raw = raw  # teshis: son gercek koordinat-tiklama yaniti
                # TESHIS: GERCEK cekim akisinin ilk yanitini diske yaz (olu kod
                # _direct_open_coord DEGIL, asil buton-tiklama yolu). Sorunun
                # gercek imzasini burada goruruz.
                if not getattr(self, "_dumped_fetch", False):
                    self._dumped_fetch = True
                    try:
                        import os
                        os.makedirs("teshis", exist_ok=True)
                        with open("teshis/fetch_raw.txt", "w", encoding="utf-8") as fh:
                            fh.write(raw)
                        self.cb.log("[TESHIS] Ilk GERCEK koordinat-tiklama yaniti "
                                    "-> teshis/fetch_raw.txt")
                    except Exception:
                        pass
                # KRITIK: validasyon patlamis yanit (captcha) BOS dialog dondurur.
                # Bunu 'koordinat yok' sanip kaydetmek 1600+ tesisi zehirledi ->
                # hata firlat, sync katmani re-auth yapsin.
                if _is_validation_failed(raw):
                    raise CaptchaInvalid(
                        "sunucu captcha dogrulamasina takti (validationFailed) "
                        "-> bos dialog; koordinat-yok DEGIL")
                total = self._extract_total(raw)
                vs = self._extract_viewstate(raw)
                page1 = self._parse_html(self._extract_coord_html(raw)).get("rows", [])
                # NOT: contentLoad'u ELLE cekMIYORUZ -> manuel istek facility
                # secimini kaybediyor ('Kayit Bulunamadi'). _capture_raw artik
                # tarayicinin OTOMATIK contentLoad'unu (dolu tablo) bekliyor.
                if not page1 and total == 0:  # gercekten koordinat yok
                    self._close_dialog()
                    return []
                if not vs:  # ViewState alinamadiysa dogrudan POST yapamayiz
                    self._close_dialog()
                    return self._parse_rows(page1)

                # 2) DOGRUDAN sayfala (_first'i artir, ViewState tasi). DEDUP YOK.
                all_rows = []
                first = 0
                guard = 0
                while guard < 400:
                    guard += 1
                    text, vs = self._direct_page(first, self.ROWS_PER, vs)
                    rows = self._parse_html(self._extract_coord_html(text)).get("rows", [])
                    if not rows:
                        break
                    all_rows.extend(rows)
                    if len(rows) < self.ROWS_PER:
                        break  # son sayfa
                    if total and len(all_rows) >= total:
                        break
                    first += self.ROWS_PER
                    time.sleep(settings.request_delay_ms / 1000)  # sunucuya nazik

                pts = self._parse_rows(all_rows)
                if not pts:  # dogrudan istek bos dondu -> buton yanitina dus
                    pts = self._parse_rows(page1)
                if total and len(pts) < total:
                    self.cb.log(f"    [uyari] {len(pts)}/{total} nokta okundu")
                self._close_dialog()
                return pts
            except (BlockedError, CaptchaInvalid):
                # WAF engellemesi / captcha validasyonu: ic retry ETME (retry
                # cozmez), dialog'u kapat ve HEMEN yukari firlat -> sync katmani
                # backoff ya da re-auth uygular.
                self._cap_on = False
                self._close_dialog()
                raise
            except Exception as e:
                last_err = e
                self._cap_on = False
                self.cb.log(f"    [koord retry {attempt+1}] {str(e)[:80]}")
                self._close_dialog()
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"koordinat alinamadi: {last_err}")

    def _close_dialog(self):
        try:
            # kapatma butonuna JS ile tikla; degilse ESC
            closed = self.page.eval_on_selector(
                COORD_CLOSE, "e => { if(e){ e.click(); return true;} return false; }")
            if not closed:
                self.page.keyboard.press("Escape")
            # dialog gizlenene ve modal maskesi kalkana kadar bekle
            for _ in range(20):
                visible = self.page.eval_on_selector(
                    DIALOG, "e => e && e.offsetParent !== null && "
                            "getComputedStyle(e).display !== 'none'")
                mask = self.page.eval_on_selector_all(
                    ".ui-widget-overlay",
                    "els => els.some(e => e.offsetParent !== null)")
                if not visible and not mask:
                    break
                time.sleep(0.15)
        except Exception:
            pass
