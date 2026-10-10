/*
 * Aseko test cases card: mark test cases in the frame log, photograph the unit's
 * display, and download everything later from any device.
 *
 *   type: custom:aseko-test-cases-card
 *   language: sk   # optional; defaults to the Home Assistant user language
 *
 * Loaded on every dashboard by the Aseko Local integration.  Cases (markers)
 * and photos are kept in Home Assistant, so the list below is the same on a
 * phone and a PC, and shows which cases have not been downloaded yet.
 * Admin users only, like the diagnostics download.
 */

const STATUS_URL = "/api/aseko_local/status";
const PHOTO_URL = "/api/aseko_local/photo";
const EXPORT_URL = "/api/aseko_local/export";
const FORGET_URL = "/api/aseko_local/forget";
const EXPORTED_URL = "/api/aseko_local/exported";
const RECORDING_URL = "/api/aseko_local/recording";
const DELETE_URL = "/api/aseko_local/delete";

const STRINGS = {
  "en": {
    "title": "Aseko test cases",
    "last_frame": "Last frame: {v}",
    "last_frame_ago": "Last frame: <b>{s} s</b> ago",
    "last_frame_none": "Last frame: none received yet",
    "last_frame_error": "Last frame: unavailable ({e})",
    "placeholder": "What did you change? e.g. Heating control ON",
    "photo_mark": "Photo + mark",
    "mark": "Mark",
    "wait": "wait for next frame",
    "unit": "Unit",
    "intro": "Mark each change; download the cases whenever you like.",
    "cases": "Cases",
    "cases_count": "Cases ({n}, not downloaded: {f})",
    "no_cases": "No cases yet.",
    "download_new": "Download new",
    "download_all": "Download all",
    "clear": "Clear list",
    "downloaded": "downloaded",
    "not_downloaded": "NOT downloaded",
    "frames_kept": "frames kept",
    "frames_gone": "frames aged out",
    "no_frame_flag": "no frame came",
    "no_note": "(no note)",
    "photo": "photo",
    "case_saved": "Case #{n} saved at {time}",
    "with_photo": " with photo",
    "uploading": "Uploading photo\u2026 the case is not saved yet.",
    "photo_failed": "Photo not stored: {e}",
    "waiting": "Waiting for the next frame\u2026 the case is not saved yet, leave the unit as it is.",
    "saving": "Saving case\u2026",
    "no_frame": "No frame within 60 s.\n{cases} without one.",
    "frame_received": " \u2014 frame received, go on with the next change.",
    "mark_failed": "Case not saved: {e}",
    "zipping": "Building the zip\u2026",
    "zipped": "Zip downloaded ({kb} kB).",
    "zipped_unconfirmed": "Zip downloaded ({kb} kB), but Home Assistant did not confirm it: the cases stay not downloaded and Download new offers them again.",
    "download_failed": "Download failed: {e}",
    "clear_confirm": "Clear the list of cases? Frames and photos stay in Home Assistant.",
    "cleared": "List cleared.",
    "clear_failed": "Not cleared: {e}",
    "recording_on": "Recording on",
    "recording_off": "Recording off",
    "recording_off_hint": "Recording is off: frames are not saved and cases cannot be marked. Turn it on first.",
    "recording_turned_on": "Recording on: every frame is saved from now on.",
    "recording_turned_off": "Recording off. What is recorded stays until you delete it.",
    "recording_failed": "Recording not switched: {e}",
    "delete": "Delete recording",
    "delete_confirm": "Delete every recorded frame, case and photo? This cannot be undone.",
    "deleted": "Recording deleted ({p} photos).",
    "delete_failed": "Not deleted: {e}"
  },
  "sk": {
    "title": "Aseko \u2013 z\u00e1znam pokusov",
    "last_frame": "Posledn\u00fd r\u00e1mec: {v}",
    "last_frame_ago": "Posledn\u00fd r\u00e1mec: pred <b>{s} s</b>",
    "last_frame_none": "Posledn\u00fd r\u00e1mec: zatia\u013e \u017eiadny",
    "last_frame_error": "Posledn\u00fd r\u00e1mec: nedostupn\u00e9 ({e})",
    "placeholder": "\u010co si zmenil? napr. Ohrev ZAP",
    "photo_mark": "Fotka + z\u00e1znam",
    "mark": "Z\u00e1znam",
    "wait": "po\u010dka\u0165 na \u010fal\u0161\u00ed r\u00e1mec",
    "unit": "Jednotka",
    "intro": "Zaznamenaj ka\u017ed\u00fa zmenu; pokusy si stiahni kedyko\u013evek.",
    "cases": "Pokusy",
    "cases_count": "Pokusy ({n}, nestiahnut\u00e9: {f})",
    "no_cases": "Zatia\u013e \u017eiadne pokusy.",
    "download_new": "Stiahnu\u0165 nov\u00e9",
    "download_all": "Stiahnu\u0165 v\u0161etko",
    "clear": "Vymaza\u0165 zoznam",
    "downloaded": "stiahnut\u00e9",
    "not_downloaded": "NESTIAHNUT\u00c9",
    "frames_kept": "r\u00e1mce ulo\u017een\u00e9",
    "frames_gone": "r\u00e1mce u\u017e vypadli",
    "no_frame_flag": "r\u00e1mec nepri\u0161iel",
    "no_note": "(bez pozn\u00e1mky)",
    "photo": "fotka",
    "case_saved": "Pokus #{n} ulo\u017een\u00fd o {time}",
    "with_photo": " s fotkou",
    "uploading": "Nahr\u00e1vam fotku\u2026 pokus e\u0161te nie je ulo\u017een\u00fd.",
    "photo_failed": "Fotka neulo\u017een\u00e1: {e}",
    "waiting": "\u010cak\u00e1m na \u010fal\u0161\u00ed r\u00e1mec\u2026 pokus e\u0161te nie je ulo\u017een\u00fd, na jednotke ni\u010d neme\u0148.",
    "saving": "Uklad\u00e1m pokus\u2026",
    "no_frame": "\u017diadny r\u00e1mec do 60 s.\n{cases} bez neho.",
    "frame_received": " \u2014 r\u00e1mec pri\u0161iel, m\u00f4\u017ee\u0161 robi\u0165 \u010fal\u0161iu zmenu.",
    "mark_failed": "Pokus neulo\u017een\u00fd: {e}",
    "zipping": "Vytv\u00e1ram zip\u2026",
    "zipped": "Zip stiahnut\u00fd ({kb} kB).",
    "zipped_unconfirmed": "Zip stiahnut\u00fd ({kb} kB), ale Home Assistant to nepotvrdil: pokusy ost\u00e1vaj\u00fa nestiahnut\u00e9 a Stiahnu\u0165 nov\u00e9 ich pon\u00fakne znova.",
    "download_failed": "S\u0165ahovanie zlyhalo: {e}",
    "clear_confirm": "Vymaza\u0165 zoznam pokusov? R\u00e1mce a fotky ostan\u00fa v Home Assistante.",
    "cleared": "Zoznam vymazan\u00fd.",
    "clear_failed": "Nevymazan\u00e9: {e}",
    "recording_on": "Nahr\u00e1vanie zapnut\u00e9",
    "recording_off": "Nahr\u00e1vanie vypnut\u00e9",
    "recording_off_hint": "Nahr\u00e1vanie je vypnut\u00e9: r\u00e1mce sa neukladaj\u00fa a pokusy sa nedaj\u00fa zaznamena\u0165. Najprv ho zapni.",
    "recording_turned_on": "Nahr\u00e1vanie zapnut\u00e9: odteraz sa uklad\u00e1 ka\u017ed\u00fd r\u00e1mec.",
    "recording_turned_off": "Nahr\u00e1vanie vypnut\u00e9. Nahrat\u00e9 ost\u00e1va, k\u00fdm ho nevyma\u017ee\u0161.",
    "recording_failed": "Nahr\u00e1vanie sa neprepnulo: {e}",
    "delete": "Vymaza\u0165 nahr\u00e1vku",
    "delete_confirm": "Vymaza\u0165 v\u0161etky nahrat\u00e9 r\u00e1mce, pokusy a fotky? Ned\u00e1 sa to vr\u00e1ti\u0165.",
    "deleted": "Nahr\u00e1vka vymazan\u00e1 (fotky: {p}).",
    "delete_failed": "Nevymazan\u00e9: {e}"
  },
  "cs": {
    "title": "Aseko \u2013 z\u00e1znam pokus\u016f",
    "last_frame": "Posledn\u00ed r\u00e1mec: {v}",
    "last_frame_ago": "Posledn\u00ed r\u00e1mec: p\u0159ed <b>{s} s</b>",
    "last_frame_none": "Posledn\u00ed r\u00e1mec: zat\u00edm \u017e\u00e1dn\u00fd",
    "last_frame_error": "Posledn\u00ed r\u00e1mec: nedostupn\u00e9 ({e})",
    "placeholder": "Co jste zm\u011bnili? nap\u0159. Oh\u0159ev ZAP",
    "photo_mark": "Fotka + z\u00e1znam",
    "mark": "Z\u00e1znam",
    "wait": "po\u010dkat na dal\u0161\u00ed r\u00e1mec",
    "unit": "Jednotka",
    "intro": "Zaznamenejte ka\u017edou zm\u011bnu; pokusy si st\u00e1hn\u011bte kdykoli.",
    "cases": "Pokusy",
    "cases_count": "Pokusy ({n}, nesta\u017eeno: {f})",
    "no_cases": "Zat\u00edm \u017e\u00e1dn\u00e9 pokusy.",
    "download_new": "St\u00e1hnout nov\u00e9",
    "download_all": "St\u00e1hnout v\u0161e",
    "clear": "Vymazat seznam",
    "downloaded": "sta\u017eeno",
    "not_downloaded": "NESTA\u017dENO",
    "frames_kept": "r\u00e1mce ulo\u017eeny",
    "frames_gone": "r\u00e1mce u\u017e vypadly",
    "no_frame_flag": "r\u00e1mec nep\u0159i\u0161el",
    "no_note": "(bez pozn\u00e1mky)",
    "photo": "fotka",
    "case_saved": "Pokus #{n} ulo\u017een v {time}",
    "with_photo": " s fotkou",
    "uploading": "Nahr\u00e1v\u00e1m fotku\u2026 pokus je\u0161t\u011b nen\u00ed ulo\u017een.",
    "photo_failed": "Fotka neulo\u017eena: {e}",
    "waiting": "\u010cek\u00e1m na dal\u0161\u00ed r\u00e1mec\u2026 pokus je\u0161t\u011b nen\u00ed ulo\u017een, na jednotce nic nem\u011b\u0148te.",
    "saving": "Ukl\u00e1d\u00e1m pokus\u2026",
    "no_frame": "\u017d\u00e1dn\u00fd r\u00e1mec do 60 s.\n{cases} bez n\u011bj.",
    "frame_received": " \u2014 r\u00e1mec p\u0159i\u0161el, pokra\u010dujte dal\u0161\u00ed zm\u011bnou.",
    "mark_failed": "Pokus neulo\u017een: {e}",
    "zipping": "Vytv\u00e1\u0159\u00edm zip\u2026",
    "zipped": "Zip sta\u017een ({kb} kB).",
    "zipped_unconfirmed": "Zip sta\u017een ({kb} kB), ale Home Assistant to nepotvrdil: pokusy z\u016fst\u00e1vaj\u00ed nesta\u017een\u00e9 a St\u00e1hnout nov\u00e9 je nab\u00eddne znovu.",
    "download_failed": "Stahov\u00e1n\u00ed selhalo: {e}",
    "clear_confirm": "Vymazat seznam pokus\u016f? R\u00e1mce a fotky z\u016fstanou v Home Assistantu.",
    "cleared": "Seznam vymaz\u00e1n.",
    "clear_failed": "Nevymaz\u00e1no: {e}",
    "recording_on": "Nahr\u00e1v\u00e1n\u00ed zapnuto",
    "recording_off": "Nahr\u00e1v\u00e1n\u00ed vypnuto",
    "recording_off_hint": "Nahr\u00e1v\u00e1n\u00ed je vypnut\u00e9: r\u00e1mce se neukl\u00e1daj\u00ed a pokusy nelze zaznamenat. Nejprve ho zapn\u011bte.",
    "recording_turned_on": "Nahr\u00e1v\u00e1n\u00ed zapnuto: od te\u010f se ukl\u00e1d\u00e1 ka\u017ed\u00fd r\u00e1mec.",
    "recording_turned_off": "Nahr\u00e1v\u00e1n\u00ed vypnuto. Nahran\u00e9 z\u016fst\u00e1v\u00e1, dokud ho nesma\u017eete.",
    "recording_failed": "Nahr\u00e1v\u00e1n\u00ed se nep\u0159epnulo: {e}",
    "delete": "Smazat nahr\u00e1vku",
    "delete_confirm": "Smazat v\u0161echny nahran\u00e9 r\u00e1mce, pokusy a fotky? Nelze to vr\u00e1tit.",
    "deleted": "Nahr\u00e1vka smaz\u00e1na (fotky: {p}).",
    "delete_failed": "Nesmaz\u00e1no: {e}"
  },
  "de": {
    "title": "Aseko-Testf\u00e4lle",
    "last_frame": "Letzter Frame: {v}",
    "last_frame_ago": "Letzter Frame: vor <b>{s} s</b>",
    "last_frame_none": "Letzter Frame: noch keiner empfangen",
    "last_frame_error": "Letzter Frame: nicht verf\u00fcgbar ({e})",
    "placeholder": "Was wurde ge\u00e4ndert? z. B. Heizung EIN",
    "photo_mark": "Foto + Markierung",
    "mark": "Markieren",
    "wait": "auf n\u00e4chsten Frame warten",
    "unit": "Ger\u00e4t",
    "intro": "Jede \u00c4nderung markieren; die F\u00e4lle jederzeit herunterladen.",
    "cases": "F\u00e4lle",
    "cases_count": "F\u00e4lle ({n}, nicht heruntergeladen: {f})",
    "no_cases": "Noch keine F\u00e4lle.",
    "download_new": "Neue herunterladen",
    "download_all": "Alle herunterladen",
    "clear": "Liste leeren",
    "downloaded": "heruntergeladen",
    "not_downloaded": "NICHT heruntergeladen",
    "frames_kept": "Frames vorhanden",
    "frames_gone": "Frames verfallen",
    "no_frame_flag": "kein Frame gekommen",
    "no_note": "(keine Notiz)",
    "photo": "Foto",
    "case_saved": "Fall #{n} gespeichert um {time}",
    "with_photo": " mit Foto",
    "uploading": "Foto wird hochgeladen\u2026 der Fall ist noch nicht gespeichert.",
    "photo_failed": "Foto nicht gespeichert: {e}",
    "waiting": "Warte auf den n\u00e4chsten Frame\u2026 der Fall ist noch nicht gespeichert, am Ger\u00e4t nichts \u00e4ndern.",
    "saving": "Fall wird gespeichert\u2026",
    "no_frame": "Kein Frame innerhalb von 60 s.\n{cases} ohne Frame.",
    "frame_received": " \u2014 Frame empfangen, weiter mit der n\u00e4chsten \u00c4nderung.",
    "mark_failed": "Fall nicht gespeichert: {e}",
    "zipping": "Zip wird erstellt\u2026",
    "zipped": "Zip heruntergeladen ({kb} kB).",
    "zipped_unconfirmed": "Zip heruntergeladen ({kb} kB), aber Home Assistant hat es nicht best\u00e4tigt: die F\u00e4lle bleiben nicht heruntergeladen und Neue herunterladen bietet sie erneut an.",
    "download_failed": "Download fehlgeschlagen: {e}",
    "clear_confirm": "Liste der F\u00e4lle leeren? Frames und Fotos bleiben in Home Assistant.",
    "cleared": "Liste geleert.",
    "clear_failed": "Nicht geleert: {e}",
    "recording_on": "Aufzeichnung an",
    "recording_off": "Aufzeichnung aus",
    "recording_off_hint": "Die Aufzeichnung ist aus: Frames werden nicht gespeichert und F\u00e4lle k\u00f6nnen nicht markiert werden. Zuerst einschalten.",
    "recording_turned_on": "Aufzeichnung an: ab jetzt wird jeder Frame gespeichert.",
    "recording_turned_off": "Aufzeichnung aus. Das Aufgezeichnete bleibt, bis es gel\u00f6scht wird.",
    "recording_failed": "Aufzeichnung nicht umgeschaltet: {e}",
    "delete": "Aufzeichnung l\u00f6schen",
    "delete_confirm": "Alle aufgezeichneten Frames, F\u00e4lle und Fotos l\u00f6schen? Das kann nicht r\u00fcckg\u00e4ngig gemacht werden.",
    "deleted": "Aufzeichnung gel\u00f6scht ({p} Fotos).",
    "delete_failed": "Nicht gel\u00f6scht: {e}"
  },
  "fr": {
    "title": "Cas de test Aseko",
    "last_frame": "Derni\u00e8re trame : {v}",
    "last_frame_ago": "Derni\u00e8re trame : il y a <b>{s} s</b>",
    "last_frame_none": "Derni\u00e8re trame : aucune re\u00e7ue",
    "last_frame_error": "Derni\u00e8re trame : indisponible ({e})",
    "placeholder": "Qu'avez-vous chang\u00e9 ? ex. Chauffage ON",
    "photo_mark": "Photo + marque",
    "mark": "Marquer",
    "wait": "attendre la trame suivante",
    "unit": "Appareil",
    "intro": "Marquez chaque changement ; t\u00e9l\u00e9chargez les cas quand vous voulez.",
    "cases": "Cas",
    "cases_count": "Cas ({n}, non t\u00e9l\u00e9charg\u00e9s : {f})",
    "no_cases": "Aucun cas pour l'instant.",
    "download_new": "T\u00e9l\u00e9charger les nouveaux",
    "download_all": "Tout t\u00e9l\u00e9charger",
    "clear": "Vider la liste",
    "downloaded": "t\u00e9l\u00e9charg\u00e9",
    "not_downloaded": "NON t\u00e9l\u00e9charg\u00e9",
    "frames_kept": "trames conserv\u00e9es",
    "frames_gone": "trames expir\u00e9es",
    "no_frame_flag": "aucune trame re\u00e7ue",
    "no_note": "(sans note)",
    "photo": "photo",
    "case_saved": "Cas #{n} enregistr\u00e9 \u00e0 {time}",
    "with_photo": " avec photo",
    "uploading": "Envoi de la photo\u2026 le cas n'est pas encore enregistr\u00e9.",
    "photo_failed": "Photo non enregistr\u00e9e : {e}",
    "waiting": "Attente de la trame suivante\u2026 le cas n'est pas encore enregistr\u00e9, ne touchez pas l'appareil.",
    "saving": "Enregistrement du cas\u2026",
    "no_frame": "Aucune trame en 60 s.\n{cases} sans trame.",
    "frame_received": " \u2014 trame re\u00e7ue, passez au changement suivant.",
    "mark_failed": "Cas non enregistr\u00e9 : {e}",
    "zipping": "Cr\u00e9ation du zip\u2026",
    "zipped": "Zip t\u00e9l\u00e9charg\u00e9 ({kb} ko).",
    "zipped_unconfirmed": "Zip t\u00e9l\u00e9charg\u00e9 ({kb} ko), mais Home Assistant ne l'a pas confirm\u00e9 : les cas restent non t\u00e9l\u00e9charg\u00e9s et T\u00e9l\u00e9charger les nouveaux les propose \u00e0 nouveau.",
    "download_failed": "\u00c9chec du t\u00e9l\u00e9chargement : {e}",
    "clear_confirm": "Vider la liste des cas ? Les trames et photos restent dans Home Assistant.",
    "cleared": "Liste vid\u00e9e.",
    "clear_failed": "Non vid\u00e9e : {e}",
    "recording_on": "Enregistrement activ\u00e9",
    "recording_off": "Enregistrement d\u00e9sactiv\u00e9",
    "recording_off_hint": "L'enregistrement est d\u00e9sactiv\u00e9 : les trames ne sont pas conserv\u00e9es et aucun cas ne peut \u00eatre marqu\u00e9. Activez-le d'abord.",
    "recording_turned_on": "Enregistrement activ\u00e9 : chaque trame est conserv\u00e9e \u00e0 partir de maintenant.",
    "recording_turned_off": "Enregistrement d\u00e9sactiv\u00e9. Ce qui est enregistr\u00e9 reste jusqu'\u00e0 sa suppression.",
    "recording_failed": "Enregistrement non bascul\u00e9 : {e}",
    "delete": "Supprimer l'enregistrement",
    "delete_confirm": "Supprimer toutes les trames, cas et photos enregistr\u00e9s ? Action irr\u00e9versible.",
    "deleted": "Enregistrement supprim\u00e9 ({p} photos).",
    "delete_failed": "Non supprim\u00e9 : {e}"
  }
};

const format = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));

const esc = (text) =>
  String(text == null ? "" : text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class AsekoTestCasesCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._lang = this._lang || "en";
    this._pruneThumbs(null);
    this._thumbs = {};
    this._listKey = "";
    this._isBusy = false;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const lang = this._language(hass);
    if (lang !== this._lang) {
      this._lang = lang;
      this._listKey = "";
      if (this.shadowRoot) {
        this._render();
        this._poll();
      }
    }
  }

  _language(hass) {
    const wanted = this._config.language || (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
    const base = String(wanted).toLowerCase().split(/[-_]/)[0];
    return STRINGS[base] ? base : "en";
  }

  _t(key, values) {
    const table = STRINGS[this._lang] || STRINGS.en;
    return format(table[key] || STRINGS.en[key] || key, values);
  }

  _locale() {
    return (this._hass && this._hass.locale && this._hass.locale.language) || this._lang;
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  connectedCallback() {
    this._poll();
    clearInterval(this._timer);
    // the timer waits for an unanswered poll; a slow Home Assistant must not
    // pile up requests
    this._timer = setInterval(() => {
      if (!this._polling) this._poll();
    }, 3000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    // an answer arriving after this is stale
    this._pollSeq = (this._pollSeq || 0) + 1;
    this._polling = false;
    this._pruneThumbs(null);
    this._listKey = "";
  }

  _render() {
    const title = this._config.title || this._t("title");
    const note = this.shadowRoot.getElementById && this.shadowRoot.getElementById("note");
    const draft = note ? note.value : "";
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --aseko-accent: var(--primary-color, #2b87ff);
          --aseko-accent-soft: color-mix(in srgb, var(--aseko-accent) 12%, transparent);
          --aseko-surface: color-mix(in srgb, var(--primary-text-color) 4%, var(--card-background-color));
          --aseko-border: color-mix(in srgb, var(--primary-text-color) 12%, transparent);
          display: block;
        }
        * { box-sizing: border-box; }
        ha-card {
          display: block;
          container-type: inline-size;
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 16px);
          background: var(--ha-card-background, var(--card-background-color));
        }
        .hero {
          position: relative;
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 20px 22px 18px;
          border-bottom: 1px solid var(--aseko-border);
          background:
            radial-gradient(circle at 92% -20%, color-mix(in srgb, var(--aseko-accent) 22%, transparent), transparent 52%),
            linear-gradient(135deg, color-mix(in srgb, var(--aseko-accent) 8%, transparent), transparent 58%);
        }
        .brand-icon {
          display: grid;
          width: 44px;
          height: 44px;
          flex: 0 0 44px;
          place-items: center;
          border-radius: 14px;
          color: var(--aseko-accent);
          background: var(--aseko-accent-soft);
          box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--aseko-accent) 20%, transparent);
        }
        .brand-icon ha-icon { --mdc-icon-size: 26px; }
        .hero-copy { min-width: 0; flex: 1; }
        h2 { margin: 0; color: var(--primary-text-color); font-size: 1.22rem; font-weight: 700; line-height: 1.25; }
        .age {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          margin-top: 5px;
          color: var(--secondary-text-color);
          font-size: .84rem;
          line-height: 1.3;
        }
        .age::before {
          width: 8px;
          height: 8px;
          flex: 0 0 8px;
          border-radius: 50%;
          background: var(--disabled-text-color);
          content: "";
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--disabled-text-color) 16%, transparent);
        }
        .age[data-state="fresh"]::before { background: var(--success-color, #43a047); box-shadow: 0 0 0 3px color-mix(in srgb, var(--success-color, #43a047) 18%, transparent); }
        .age[data-state="stale"]::before { background: var(--warning-color, #f0a000); box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning-color, #f0a000) 18%, transparent); }
        .age[data-state="error"]::before { background: var(--error-color, #db4437); box-shadow: 0 0 0 3px color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); }
        .age b { color: var(--primary-text-color); font-size: 1em; font-weight: 700; }
        .rec { flex: 0 0 auto; min-height: 36px; padding: 0 12px; font-size: .82rem; }
        .rec::before { flex: 0 0 9px; width: 9px; height: 9px; border-radius: 50%; background: var(--disabled-text-color); content: ""; }
        .rec[aria-pressed="true"]::before { background: var(--error-color, #db4437); box-shadow: 0 0 0 3px color-mix(in srgb, var(--error-color, #db4437) 20%, transparent); }
        .body { padding: 20px 22px 22px; }
        .composer {
          padding: 14px;
          border: 1px solid var(--aseko-border);
          border-radius: 15px;
          background: var(--aseko-surface);
        }
        .input-wrap { position: relative; }
        .input-wrap ha-icon {
          position: absolute;
          top: 50%;
          left: 13px;
          color: var(--secondary-text-color);
          pointer-events: none;
          transform: translateY(-50%);
          --mdc-icon-size: 20px;
        }
        input[type=text] {
          width: 100%;
          min-width: 0;
          height: 46px;
          padding: 0 14px 0 42px;
          border: 1px solid var(--aseko-border);
          border-radius: 11px;
          outline: none;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          transition: border-color .18s ease, box-shadow .18s ease;
        }
        input[type=text]::placeholder { color: var(--secondary-text-color); opacity: .82; }
        input[type=text]:focus { border-color: var(--aseko-accent); box-shadow: 0 0 0 3px var(--aseko-accent-soft); }
        .action-row { display: flex; align-items: center; gap: 9px; margin-top: 10px; }
        button {
          display: inline-flex;
          min-height: 42px;
          align-items: center;
          justify-content: center;
          gap: 7px;
          padding: 0 15px;
          border: 1px solid transparent;
          border-radius: 11px;
          outline: none;
          background: var(--aseko-accent);
          color: var(--text-primary-color, #fff);
          font: inherit;
          font-size: .92rem;
          font-weight: 650;
          cursor: pointer;
          transition: transform .15s ease, filter .15s ease, box-shadow .15s ease;
        }
        button:hover:not(:disabled) { filter: brightness(1.06); box-shadow: 0 4px 12px color-mix(in srgb, var(--aseko-accent) 22%, transparent); transform: translateY(-1px); }
        button:active:not(:disabled) { transform: translateY(0); }
        button:focus-visible { box-shadow: 0 0 0 3px var(--card-background-color), 0 0 0 5px var(--aseko-accent); }
        button ha-icon { --mdc-icon-size: 19px; }
        button.secondary { border-color: var(--aseko-border); background: transparent; color: var(--primary-text-color); }
        button.secondary:hover:not(:disabled) { background: var(--aseko-surface); box-shadow: none; }
        button.danger { color: var(--error-color, #db4437); }
        button:disabled { opacity: .46; cursor: not-allowed; }
        .wait-option {
          display: flex;
          min-height: 42px;
          align-items: center;
          gap: 8px;
          margin-left: auto;
          color: var(--secondary-text-color);
          font-size: .84rem;
          cursor: pointer;
          user-select: none;
        }
        .wait-option input { width: 17px; height: 17px; margin: 0; accent-color: var(--aseko-accent); }
        .wait-option[hidden] { display: none; }
        .wait-option select { min-height: 30px; border: 1px solid var(--aseko-border); border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
        .status {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          margin-top: 11px;
          padding: 10px 12px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--secondary-text-color) 8%, transparent);
          color: var(--secondary-text-color);
          font-size: .86rem;
          line-height: 1.4;
          white-space: pre-line;
        }
        .status::before { flex: 0 0 auto; content: "ⓘ"; font-weight: 700; }
        .status.waiting { background: color-mix(in srgb, var(--warning-color, #f0a000) 14%, transparent); color: var(--primary-text-color); }
        .status.waiting::before { content: "⏳"; }
        .status.done { background: color-mix(in srgb, var(--success-color, #43a047) 14%, transparent); color: var(--primary-text-color); }
        .status.done::before { color: var(--success-color, #43a047); content: "✓"; }
        .status.error { background: color-mix(in srgb, var(--error-color, #db4437) 14%, transparent); color: var(--primary-text-color); }
        .status.error::before { color: var(--error-color, #db4437); content: "!"; }
        .history { margin-top: 22px; }
        .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
        h3 { margin: 0; color: var(--primary-text-color); font-size: .98rem; font-weight: 700; }
        .cases { display: flex; flex-direction: column; gap: 8px; }
        .case {
          position: relative;
          display: flex;
          min-width: 0;
          align-items: center;
          gap: 12px;
          padding: 11px 12px;
          border: 1px solid var(--aseko-border);
          border-radius: 13px;
          background: var(--card-background-color);
        }
        .case.new { border-color: color-mix(in srgb, var(--warning-color, #f0a000) 40%, var(--aseko-border)); background: color-mix(in srgb, var(--warning-color, #f0a000) 5%, var(--card-background-color)); }
        .case.new::before { position: absolute; inset: 10px auto 10px 0; width: 3px; border-radius: 0 3px 3px 0; background: var(--warning-color, #f0a000); content: ""; }
        .case img { width: 58px; height: 58px; flex: 0 0 58px; object-fit: cover; border-radius: 10px; cursor: zoom-in; }
        .case-number {
          display: grid;
          width: 34px;
          height: 34px;
          flex: 0 0 34px;
          place-items: center;
          border-radius: 10px;
          background: var(--aseko-accent-soft);
          color: var(--aseko-accent);
          font-size: .78rem;
          font-weight: 800;
        }
        .case .txt { min-width: 0; flex: 1; }
        .case .note { overflow-wrap: anywhere; color: var(--primary-text-color); font-size: .93rem; font-weight: 650; line-height: 1.35; }
        .case .meta { margin-top: 3px; color: var(--secondary-text-color); font-size: .77rem; line-height: 1.35; }
        .case-flags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px; }
        .flag { padding: 3px 7px; border-radius: 999px; background: var(--aseko-surface); color: var(--secondary-text-color); font-size: .68rem; font-weight: 650; }
        .flag.new { background: color-mix(in srgb, var(--warning-color, #f0a000) 15%, transparent); color: color-mix(in srgb, var(--warning-color, #f0a000) 72%, var(--primary-text-color)); }
        .empty {
          display: grid;
          min-height: 104px;
          place-items: center;
          padding: 20px;
          border: 1px dashed var(--aseko-border);
          border-radius: 13px;
          color: var(--secondary-text-color);
          text-align: center;
          font-size: .88rem;
        }
        .footer-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
        .footer-actions .danger { margin-left: auto; }
        .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
        @container (max-width: 560px) {
          .hero { flex-wrap: wrap; padding: 17px 16px 15px; }
          .rec { width: 100%; }
          .body { padding: 16px; }
          .composer { padding: 12px; }
          .action-row { align-items: stretch; flex-wrap: wrap; }
          .action-row button { flex: 1 1 calc(50% - 5px); padding-inline: 10px; }
          .wait-option { width: 100%; min-height: 32px; margin-left: 2px; }
          .footer-actions button { flex: 1 1 calc(50% - 4px); padding-inline: 10px; }
          .footer-actions .danger { flex-basis: 100%; margin-left: 0; }
          .case { align-items: flex-start; }
          .case-number { display: none; }
          .case img { width: 52px; height: 52px; flex-basis: 52px; }
        }
        @media (prefers-reduced-motion: reduce) { button, input { transition: none; } }
      </style>
      <ha-card>
        <header class="hero">
          <div class="brand-icon" aria-hidden="true"><ha-icon icon="mdi:pool"></ha-icon></div>
          <div class="hero-copy">
            <h2>${esc(title)}</h2>
            <div class="age" id="age" data-state="unknown">${esc(this._t("last_frame", { v: "\u2026" }))}</div>
          </div>
          <button id="recording" class="secondary rec" aria-pressed="false" hidden>${esc(this._t("recording_off"))}</button>
        </header>
        <div class="body">
          <section class="composer">
            <label class="sr-only" for="note">${esc(this._t("placeholder"))}</label>
            <div class="input-wrap">
              <ha-icon icon="mdi:text-box-edit-outline" aria-hidden="true"></ha-icon>
              <input id="note" type="text" placeholder="${esc(this._t("placeholder"))}" maxlength="200" autocomplete="off">
            </div>
            <div class="action-row">
              <button id="photo"><ha-icon icon="mdi:camera-plus-outline" aria-hidden="true"></ha-icon>${esc(this._t("photo_mark"))}</button>
              <button id="mark"><ha-icon icon="mdi:flag-checkered" aria-hidden="true"></ha-icon>${esc(this._t("mark"))}</button>
              <label class="wait-option" id="unit-option" hidden>${esc(this._t("unit"))} <select id="unit"></select></label>
            </div>
            <input id="file" type="file" accept="image/*" capture="environment" hidden>
            <div class="status" id="status" role="status" aria-live="polite">${esc(this._t("intro"))}</div>
          </section>
          <section class="history">
            <div class="section-heading"><h3 id="heading">${esc(this._t("cases"))}</h3></div>
            <div class="cases" id="cases"><div class="empty">${esc(this._t("no_cases"))}</div></div>
            <div class="footer-actions">
              <button id="export-new"><ha-icon icon="mdi:download-outline" aria-hidden="true"></ha-icon>${esc(this._t("download_new"))}</button>
              <button id="export-all" class="secondary"><ha-icon icon="mdi:archive-arrow-down-outline" aria-hidden="true"></ha-icon>${esc(this._t("download_all"))}</button>
              <button id="forget" class="secondary"><ha-icon icon="mdi:delete-sweep-outline" aria-hidden="true"></ha-icon>${esc(this._t("clear"))}</button>
              <button id="delete" class="secondary danger"><ha-icon icon="mdi:delete-forever-outline" aria-hidden="true"></ha-icon>${esc(this._t("delete"))}</button>
            </div>
          </section>
        </div>
      </ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("note").value = draft;
    $("photo").addEventListener("click", () => $("file").click());
    $("file").addEventListener("change", (ev) => this._upload(ev.target));
    $("mark").addEventListener("click", () => this._mark());
    $("note").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.isComposing) {
        ev.preventDefault();
        this._mark();
      }
    });
    $("export-new").addEventListener("click", () => this._export(true));
    $("export-all").addEventListener("click", () => this._export(false));
    $("forget").addEventListener("click", () => this._forget());
    $("delete").addEventListener("click", () => this._delete());
    $("recording").addEventListener("click", () => this._toggleRecording());
    this._applyRecording();
  }

  _el(id) {
    return this.shadowRoot.getElementById(id);
  }

  _setStatus(text, kind) {
    const el = this._el("status");
    el.textContent = text;
    el.className = `status ${kind || ""}`;
  }

  _busy(busy) {
    this._isBusy = busy;
    for (const id of ["recording", "export-new", "export-all", "forget", "delete"]) this._el(id).disabled = busy;
    this._el("unit").disabled = busy;
    this._el("status").setAttribute("aria-busy", String(busy));
    this._applyRecording();
  }

  // Cases can be marked only while the frame log records: a case with no
  // frames around it says nothing.
  _applyRecording() {
    const button = this._el("recording");
    if (!button) return;
    const known = this._recording !== undefined;
    const on = this._recording === true;
    button.hidden = !known;
    button.setAttribute("aria-pressed", String(on));
    button.textContent = this._t(on ? "recording_on" : "recording_off");
    for (const id of ["photo", "mark"]) this._el(id).disabled = this._isBusy || !on;
    this._el("note").disabled = this._isBusy || !on;
    const status = this._el("status");
    if (known && !on && !this._isBusy && !/done|error|waiting/.test(status.className)) {
      this._setStatus(this._t("recording_off_hint"), "");
    }
  }

  async _toggleRecording() {
    const enabled = !this._recording;
    this._busy(true);
    try {
      const response = await this._hass.fetchWithAuth(RECORDING_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      this._recording = enabled;
      this._setStatus(this._t(enabled ? "recording_turned_on" : "recording_turned_off"), "done");
      this._poll();
    } catch (err) {
      this._setStatus(this._t("recording_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }

  async _delete() {
    if (!window.confirm(this._t("delete_confirm"))) return;
    this._busy(true);
    try {
      const response = await this._hass.fetchWithAuth(DELETE_URL, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
      this._setStatus(this._t("deleted", { p: data.photos_deleted }), "done");
      this._poll();
    } catch (err) {
      this._setStatus(this._t("delete_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }

  async _poll() {
    if (!this._hass || !this.shadowRoot) return;
    // Only the newest request may paint: an older answer arriving late (after
    // a toggle asked for a fresh one, or after the card left the page) would
    // put the card back to a state that is gone.
    const seq = (this._pollSeq = (this._pollSeq || 0) + 1);
    const stale = () => seq !== this._pollSeq || !this.isConnected;
    this._polling = true;
    try {
      const response = await this._hass.fetchWithAuth(STATUS_URL);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (stale()) return;
      const ages = data.entries.flatMap((e) => Object.values(e.seconds_since_last_frame));
      const youngest = ages.length ? Math.min(...ages) : null;
      this._el("age").innerHTML = ages.length
        ? this._t("last_frame_ago", { s: Math.round(youngest) })
        : esc(this._t("last_frame_none"));
      this._el("age").dataset.state = youngest == null ? "unknown" : youngest <= 15 ? "fresh" : "stale";
      this._recording = data.entries.some((e) => e.recording);
      this._applyRecording();
      this._renderCases(data.entries);
      this._renderUnits(data.entries);
    } catch (err) {
      if (stale()) return;
      this._el("age").textContent = this._t("last_frame_error", { e: err.message });
      this._el("age").dataset.state = "error";
    } finally {
      if (seq === this._pollSeq) this._polling = false;
    }
  }

  _renderCases(entries) {
    // Marker numbers count per config entry, so order by time and keep the
    // entry each case came from.
    const cases = entries
      .flatMap((e) => (e.markers || []).map((m) => ({ ...m, entry: e.entry, entryId: e.entry_id })))
      .sort((a, b) => new Date(b.t) - new Date(a.t) || b.n - a.n);
    const several = entries.length > 1;
    const fresh = entries.reduce((sum, e) => sum + (e.not_downloaded || 0), 0);
    this._el("heading").textContent = this._t("cases_count", { n: cases.length, f: fresh });
    this._el("export-new").textContent = `\u2B07 ${this._t("download_new")} (${fresh})`;
    const key = JSON.stringify([several, cases.map((c) => [c.entryId, c.n, c.t, c.note, c.downloaded, c.frames, c.photo, c.waited_for_frame, c.serial_number])]);
    this._pruneThumbs(new Set(cases.map((c) => c.photo).filter(Boolean)));
    if (key === this._listKey) return;
    this._listKey = key;
    const list = this._el("cases");
    if (!cases.length) {
      list.innerHTML = `<div class="empty">${esc(this._t("no_cases"))}</div>`;
      return;
    }
    list.innerHTML = cases
      .map((c) => {
        const when = new Date(c.t).toLocaleString(this._locale());
        const downloadFlag = this._t(c.downloaded ? "downloaded" : "not_downloaded");
        const framesFlag = this._t(c.frames ? "frames_kept" : "frames_gone");
        const img = c.photo ? `<img data-photo="${esc(c.photo)}" alt="${esc(this._t("photo"))}">` : "";
        return `<article class="case ${c.downloaded ? "" : "new"}">${img}
          <div class="case-number" aria-hidden="true">#${c.n}</div>
          <div class="txt"><div class="note">${esc(c.note || this._t("no_note"))}</div>
          <div class="meta">#${c.n} \u00B7 ${esc(when)}${several ? ` \u00B7 ${esc(c.entry)}` : ""}</div>
          <div class="case-flags"><span class="flag ${c.downloaded ? "" : "new"}">${esc(downloadFlag)}</span><span class="flag">${esc(framesFlag)}</span>${c.waited_for_frame === false ? `<span class="flag new">${esc(this._t("no_frame_flag"))}</span>` : ""}${c.serial_number ? `<span class="flag">${esc(c.serial_number)}</span>` : ""}</div></div></article>`;
      })
      .join("");
    for (const img of list.querySelectorAll("img[data-photo]")) this._loadThumb(img);
  }

  async _loadThumb(img) {
    const name = img.dataset.photo;
    if (!this._thumbs[name]) {
      this._thumbs[name] = this._hass
        .fetchWithAuth(`${PHOTO_URL}/${encodeURIComponent(name)}`)
        .then((r) => (r.ok ? r.blob() : null))
        .then((blob) => (blob ? URL.createObjectURL(blob) : null))
        .catch(() => null);
    }
    const pending = this._thumbs[name];
    const url = await pending;
    if (!url && this._thumbs[name] === pending) delete this._thumbs[name]; // try again next render
    if (url) {
      img.src = url;
      img.onclick = () => window.open(url, "_blank");
    }
  }

  _pruneThumbs(keep) {
    for (const [name, pending] of Object.entries(this._thumbs || {})) {
      if (keep && keep.has(name)) continue;
      delete this._thumbs[name];
      pending.then((url) => url && URL.revokeObjectURL(url));
    }
  }

  _reportMarkers(markers, extra) {
    const late = markers.some((m) => !m.waited_for_frame);
    this._setStatus(
      late
        ? this._t("no_frame", { cases: this._describe(markers, extra) })
        : this._describe(markers, extra) + this._t("frame_received"),
      late ? "error" : "done",
    );
  }

  _unit() {
    const select = this._el("unit");
    return select && !this._el("unit-option").hidden && select.value ? Number(select.value) : null;
  }

  _renderUnits(entries) {
    const serials = [...new Set(entries.flatMap((e) => Object.keys(e.seconds_since_last_frame || {})))].sort();
    const option = this._el("unit-option");
    const select = this._el("unit");
    option.hidden = serials.length < 2;
    const key = serials.join(",");
    if (select.dataset.key === key) return;
    const current = select.value;
    select.dataset.key = key;
    select.innerHTML = serials.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
    if (serials.includes(current)) select.value = current;
  }

  _note() {
    return this._el("note").value.trim();
  }

  _describe(markers, extra) {
    return markers
      .map((m) => this._t("case_saved", { n: m.marker, time: new Date(m.time).toLocaleTimeString(this._locale()) }) + (extra || ""))
      .join("\n");
  }

  async _upload(input) {
    const file = input.files && input.files[0];
    input.value = "";
    if (!file) return;
    this._busy(true);
    this._setStatus(this._t("waiting"), "waiting");
    try {
      const form = new FormData();
      form.append("note", this._note());
      form.append("wait", "1");
      if (this._unit()) form.append("serial_number", String(this._unit()));
      form.append("photo", file, file.name || "photo.jpg");
      const response = await this._hass.fetchWithAuth(PHOTO_URL, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
      this._reportMarkers(data.markers, this._t("with_photo"));
      this._el("note").value = "";
      this._poll();
    } catch (err) {
      this._setStatus(this._t("photo_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }

  async _mark() {
    this._busy(true);
    this._setStatus(this._t("waiting"), "waiting");
    try {
      const serviceData = { wait_for_next_frame: true };
      if (this._unit()) serviceData.serial_number = this._unit();
      if (this._note()) serviceData.note = this._note();
      const result = await this._hass.callWS({
        type: "call_service",
        domain: "aseko_local",
        service: "mark_dump",
        service_data: serviceData,
        return_response: true,
      });
      this._reportMarkers(result.response.markers, "");
      this._el("note").value = "";
      this._poll();
    } catch (err) {
      this._setStatus(this._t("mark_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }

  async _export(onlyNew) {
    this._busy(true);
    this._setStatus(this._t("zipping"), "waiting");
    try {
      const response = await this._hass.fetchWithAuth(`${EXPORT_URL}${onlyNew ? "?new=1" : ""}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob(); // the whole zip is here now
      const through = response.headers.get("X-Aseko-Export-Through");
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/.exec(disposition);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = match ? match[1] : "aseko-local-export.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 60000);
      if (through) {
        // Only now, with the zip received, are its cases downloaded.
        const confirmed = await this._hass
          .fetchWithAuth(EXPORTED_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ through: JSON.parse(through) }),
          })
          .then((r) => r.ok)
          .catch(() => false);
        if (!confirmed) {
          // the zip is saved, but the cases stay "new": say so
          this._setStatus(this._t("zipped_unconfirmed", { kb: Math.round(blob.size / 1024) }), "error");
          this._poll();
          return;
        }
      }
      this._setStatus(this._t("zipped", { kb: Math.round(blob.size / 1024) }), "done");
      this._poll();
    } catch (err) {
      this._setStatus(this._t("download_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }

  async _forget() {
    if (!window.confirm(this._t("clear_confirm"))) return;
    this._busy(true);
    try {
      const response = await this._hass.fetchWithAuth(FORGET_URL, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      this._setStatus(this._t("cleared"), "done");
      this._poll();
    } catch (err) {
      this._setStatus(this._t("clear_failed", { e: err.message }), "error");
    } finally {
      this._busy(false);
    }
  }
}

if (!customElements.get("aseko-test-cases-card")) {
  customElements.define("aseko-test-cases-card", AsekoTestCasesCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "aseko-test-cases-card",
    name: "Aseko test cases",
    description: "Mark test cases in the Aseko frame log, photograph the unit's display and download them from any device.",
  });
}
