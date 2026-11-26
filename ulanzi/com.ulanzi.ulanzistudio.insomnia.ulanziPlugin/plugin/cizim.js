/**
 * Insomnia tus cizimleri: 196x196 piksellik tus ekrani icin SVG uretir.
 *
 * Bilerek sade SVG kullanilir (mask, tspan, gradyan yok): tusu cizen program
 * hangi SVG ozelliklerini destekliyor bilinmedigi icin yalnizca temel sekiller,
 * (renkler bilerek cok doygun: cihaz ekrani renkleri soluk gosteriyor)
 * yollar ve tek parca yazilar vardir. En kucuk yazi 22 piksel.
 *
 * tus(tur, D) -> SVG metni
 *   tur: "ana" | "eksi" | "arti" | "bitince" | "ekran" | "hat"
 *   D:   { S, P, K, yan, aciliyor, eski, dil }
 *        S = Insomnia'nin durumu (kapaliysa null), P = { dk, islem } secili sure ve bitis islemi
 *        K = hatirlatici tusu "kurma" kipindeyken { mod: "kur", dk } ya da { mod: "duzenle", id }; degilse null.
 *            K varken eksi/arti tuslari altin renkte cizilir ve hatirlaticinin suresini ayarlar.
 *        yan = calan hatirlatici tusunun yanip sonmesi icin (her yoklamada degisir)
 */

const ALTIN = "#ffc21a";
const KREM = "#ffffff";
const GRI = "#c0c0c8";
const ZEMIN = "#000000";
const KOYU = "#000000";
const SOLUK = "#606068";
const KUTU = "#2c2c34";
const KUTU_SOLUK = "#1a1a1f";
const IZ = "#33333b";
const FONT = 'font-family="Arial" font-weight="bold"';

export const ISLEMLER = ["none", "shutdown", "restart", "sleep", "hibernate"];
export const MERDIVEN = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 0]; // secilebilen sureler (dk); 0 = suresiz
export const ADIM_SN = 900; // calisan oturuma eklenen/cikarilan sure
export const EN_AZ_SN = 60; // sure cikarilirken kalan sure bunun altina inemez (Insomnia ile ayni)

// Hatirlatici tusu
export const HAT_MERDIVEN = [1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240]; // tustan kurulabilen sureler (dk)
export const HAT_ADIM_SN = 300; // bekleyen hatirlaticiya eklenen/cikarilan sure
export const HAT_EN_COK_SN = 1440 * 60;

// Merdivende 'dk'dan sonraki (yon > 0) ya da onceki basamak; yoksa null. Baslangic suresi
// Ayarlar'dan gelir ve merdivende olmayabilir (26 dk gibi): o zaman en yakin basamaga gidilir.
export function hatBasamak(dk, yon) {
  if (yon > 0) {
    for (const b of HAT_MERDIVEN) if (b > dk) return b;
    return null;
  }
  for (let i = HAT_MERDIVEN.length - 1; i >= 0; i--) if (HAT_MERDIVEN[i] < dk) return HAT_MERDIVEN[i];
  return null;
}
export function hatBekleyen(S, id) {
  const R = S && S.reminders;
  return (R && Array.isArray(R.pending) && R.pending.find((h) => h.id === id)) || null;
}
// Kurma kipinde sure tusu bu yonde bir sey yapabilir mi?
export function hatAdimVar(yon, S, K) {
  if (!S || !S.reminders || !K) return false;
  if (K.mod === "kur") return hatBasamak(K.dk, yon) !== null;
  const h = hatBekleyen(S, K.id);
  if (!h) return false;
  const kalan = h.left + yon * HAT_ADIM_SN;
  return kalan >= EN_AZ_SN && kalan <= HAT_EN_COK_SN;
}

// Sure tusu bu yonde bir sey yapabilir mi? Yapamiyorsa tus soluk cizilir ve basis yok sayilir.
export function adimVar(yon, S, P) {
  if (!S) return true;
  if (S.phase === "warning") return false;
  if (S.phase === "running") return !S.infinite && (yon > 0 || S.remaining - ADIM_SN >= EN_AZ_SN);
  const i = MERDIVEN.indexOf(P.dk);
  return yon > 0 ? i < MERDIVEN.length - 1 : i !== 0;
}
export const IRENK = { none: GRI, shutdown: "#ff4b3e", restart: "#ff9500", sleep: "#a970ff", hibernate: "#1e90ff" };

const METIN = {
  tr: {
    kapali: "Kapalı", aciliyor: "Açılıyor", guncelle: "Güncelle", vazgec: "VAZGEÇ", sure: "Süre", bitince: "BİTİNCE", ekran: "EKRANI", ekranKapat: "Kapat", kapaniyor: "KAPANIYOR", iptal: "İptal",
    hatirlat: "HATIRLAT", kur: "KUR", iptalmi: "İPTAL?", sil: "Sil", tamam: "TAMAM", hatirlatma: "Hatırlatma", hatSure: "Hatırlat",
    dk: "dk", sa: "sa", sn: "sn",
    kisa: { none: "Yok", shutdown: "Kapat", restart: "Yeniden", sleep: "Uyut", hibernate: "Beklet" },
    simdi: { shutdown: ["ŞİMDİ", "Kapat"], restart: ["ŞİMDİ YENİDEN", "Başlat"], sleep: ["ŞİMDİ", "Uyut"], hibernate: ["ŞİMDİ HAZIRDA", "Beklet"] },
  },
  en: {
    kapali: "Closed", aciliyor: "Opening", guncelle: "Update", vazgec: "CANCEL", sure: "Time", bitince: "WHEN DONE", ekran: "SCREEN", ekranKapat: "Turn off", kapaniyor: "TURNING OFF", iptal: "Cancel",
    hatirlat: "REMINDER", kur: "SET", iptalmi: "CANCEL?", sil: "Delete", tamam: "OK", hatirlatma: "Reminder", hatSure: "Remind",
    dk: "m", sa: "h", sn: "s",
    kisa: { none: "None", shutdown: "Shut down", restart: "Restart", sleep: "Sleep", hibernate: "Hibernate" },
    simdi: { shutdown: ["NOW", "Shut down"], restart: ["NOW", "Restart"], sleep: ["NOW", "Sleep"], hibernate: ["NOW", "Hibernate"] },
  },
};

function kacis(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function iki(n) {
  return (n < 10 ? "0" : "") + n;
}
function svg(ic, zemin) {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" width="196" height="196" viewBox="0 0 196 196">' +
    `<rect width="196" height="196" fill="${zemin || ZEMIN}"/>` + ic + "</svg>"
  );
}
function yazi(m, y, boy, renk, x, hiza) {
  return `<text x="${x === undefined ? 98 : x}" y="${y}" ${FONT} font-size="${boy}" fill="${renk}" text-anchor="${hiza || "middle"}">${kacis(m)}</text>`;
}
// Buyuk sayi + kucuk birim, birlikte ortalanir (genislikler Arial kalin icin yaklasik).
function sayiBirim(sayi, birim, y, boy, birimBoy, renk) {
  const s = String(sayi);
  const gs = s.length * boy * 0.556, gb = birim.length * birimBoy * 0.6, ara = boy * 0.08;
  const x = 98 - (gs + ara + gb) / 2 + gs;
  return yazi(s, y, boy, renk, x.toFixed(1), "end") + yazi(birim, y, birimBoy, renk, (x + ara).toFixed(1), "start");
}
function sonsuz(cx, cy, olcek, renk, kalinlik) {
  return (
    `<path transform="translate(${cx} ${cy}) scale(${olcek})" fill="none" stroke="${renk}" stroke-width="${kalinlik}" stroke-linecap="round" ` +
    'd="M0 0C8 -14 34 -18 34 0C34 18 8 14 0 0C-8 -14 -34 -18 -34 0C-34 18 -8 14 0 0"/>'
  );
}
// Kalan sureyi gosteren halka: ustten baslar, saat yonunde 'oran' kadar dolar.
function halka(renk, oran) {
  const r = 82, iz = `<circle cx="98" cy="98" r="${r}" fill="none" stroke="${IZ}" stroke-width="16"/>`;
  if (!(oran > 0.004)) return iz;
  if (oran >= 0.999) return iz + `<circle cx="98" cy="98" r="${r}" fill="none" stroke="${renk}" stroke-width="16"/>`;
  const a = oran * 2 * Math.PI;
  const x = (98 + r * Math.sin(a)).toFixed(2), y = (98 - r * Math.cos(a)).toFixed(2);
  return iz + `<path d="M98 ${98 - r}A${r} ${r} 0 ${oran > 0.5 ? 1 : 0} 1 ${x} ${y}" fill="none" stroke="${renk}" stroke-width="16" stroke-linecap="round"/>`;
}
// Hilal: dolu daire + ustune zemin renginde ikinci daire.
function ay(renk, cx, cy, r, zemin) {
  return (
    `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${renk}"/>` +
    `<circle cx="${(cx + r * 0.5).toFixed(1)}" cy="${(cy - r * 0.36).toFixed(1)}" r="${(r * 0.86).toFixed(1)}" fill="${zemin}"/>`
  );
}
// Bitis islemi simgesi: (cx, cy) merkezli, 'boy' piksel.
export function islemSimge(islem, cx, cy, boy, renk, zemin) {
  const o = boy / 24;
  const c = `fill="none" stroke="${renk}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"`;
  let ic;
  if (islem === "shutdown") ic = `<path ${c} d="M12 2.5v9.5"/><path ${c} d="M6.2 6.4a8.5 8.5 0 1 0 11.6 0"/>`;
  else if (islem === "restart") ic = `<path ${c} d="M20.2 12.5a8.3 8.3 0 1 1-2.9-6.3"/><path fill="${renk}" d="M21.6 2.6v7.2h-7.2z"/>`;
  else if (islem === "sleep")
    // Dikkat: bir etikette ayni ozellik iki kez yazilirsa cihaz simgeyi hic cizmez.
    ic =
      `<path ${c} d="M4 9h9l-9 11h9"/>` +
      `<path fill="none" stroke="${renk}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" d="M15 3h5l-5 5.5h5"/>`;
  else if (islem === "hibernate")
    ic =
      `<circle cx="11" cy="13" r="9" fill="${renk}"/><circle cx="16.4" cy="8.4" r="7.6" fill="${zemin || ZEMIN}"/>` +
      `<path fill="none" stroke="${renk}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M15 3.4h5l-5 5.2h5"/>`;
  else ic = `<circle ${c} cx="12" cy="12" r="9"/><path ${c} d="M5.8 5.8l12.4 12.4"/>`;
  return `<g transform="translate(${(cx - 12 * o).toFixed(1)} ${(cy - 12 * o).toFixed(1)}) scale(${o.toFixed(3)})">${ic}</g>`;
}

function sureYazi(dk, y, T) {
  if (dk === 0) return sonsuz(98, y - 28, 1.7, KREM, 6);
  if (dk < 60) return sayiBirim(dk, T.dk, y, 84, 34, KREM);
  if (dk % 60 === 0) return sayiBirim(dk / 60, T.sa, y, 84, 34, KREM);
  return yazi(Math.floor(dk / 60) + ":" + iki(dk % 60), y, 72, KREM);
}

export function sonluMu(S) {
  return !!(S && S.phase === "running" && S.ending);
}

function kapaliTus(ic, D, T) {
  // "Guncelle": program acildi ama kumanda kapisi gelmedi = Insomnia 1.2.0'dan eski
  if (D.eski && !D.aciliyor) return svg(ic + yazi(T.guncelle, 176, 28, ALTIN));
  return svg(ic + yazi(D.aciliyor ? T.aciliyor : T.kapali, 176, 28, "#8c8c94"));
}

function anaTus(D, T) {
  const { S, P } = D;
  if (!S)
    return kapaliTus(
      ay(SOLUK, 92, 82, 50, ZEMIN) + `<path d="M48 128L148 34" stroke="${SOLUK}" stroke-width="10" stroke-linecap="round"/>`,
      D, T
    );
  const ir = IRENK[S.action] || GRI;
  // Uyari: tusun tamami islem rengi; simge + kalan saniye + VAZGEC
  if (S.phase === "warning")
    return svg(islemSimge(S.action, 98, 40, 66, KOYU, ir) + yazi(S.warn_in, 132, 78, KOYU) + yazi(T.vazgec, 180, 32, KOYU), ir);
  if (S.phase !== "running") {
    const pi = P.dk === 0 ? "none" : P.islem;
    // Bosta: buyuk secili sure; altinda "baslat" ucgeni ve bitiste olacak sey
    return svg(
      sureYazi(P.dk, 96, T) +
        `<rect x="24" y="122" width="148" height="56" rx="28" fill="${KUTU}"/>` +
        `<path d="M52 134l26 16-26 16z" fill="${ALTIN}" stroke="${ALTIN}" stroke-width="5" stroke-linejoin="round"/>` +
        '<path d="M98 134v32" stroke="#4a4a54" stroke-width="3" stroke-linecap="round"/>' +
        (pi === "none" ? ay(ALTIN, 134, 150, 17, KUTU) : islemSimge(pi, 136, 150, 38, IRENK[pi], KUTU))
    );
  }
  const renk = sonluMu(S) ? ir : ALTIN;
  const k = S.remaining, dk = Math.ceil(k / 60);
  let orta;
  if (S.infinite) orta = sonsuz(98, 98, 1.35, KREM, 6.5);
  else if (k <= 60) orta = sayiBirim(k, T.sn, 108, 64, 26, KREM);
  else if (dk >= 60) orta = yazi(Math.floor(dk / 60) + ":" + iki(dk % 60), 108, 56, KREM);
  else orta = sayiBirim(dk, T.dk, 108, 64, 26, KREM);
  // Calisirken: halka = kalan sure; altta bitiste olacak seyin simgesi (yoksa kucuk ay)
  const alt = S.infinite ? "" : S.action === "none" ? ay("#8c8c94", 96, 142, 14, ZEMIN) : islemSimge(S.action, 98, 142, 36, ir, ZEMIN);
  return svg(halka(renk, S.infinite || !S.total ? 1 : S.remaining / S.total) + orta + alt);
}

function adimTusu(yon, D, T) {
  const cizim = (renk, kutu) =>
    `<rect x="30" y="18" width="136" height="110" rx="30" fill="${kutu}"/>` +
    `<path d="M68 73h60${yon > 0 ? "M98 43v60" : ""}" stroke="${renk}" stroke-width="16" stroke-linecap="round" fill="none"/>`;
  const { S } = D;
  if (!S) return kapaliTus(cizim(SOLUK, KUTU_SOLUK), D, T);
  // Hatirlatici kurma kipi: tus altin olur; neyi ayarladigi renginden anlasilir.
  if (D.K && S.reminders) {
    const yok = !hatAdimVar(yon, S, D.K);
    return svg(
      cizim(yok ? SOLUK : KOYU, yok ? KUTU_SOLUK : ALTIN) +
        yazi(D.K.mod === "kur" ? T.hatSure : HAT_ADIM_SN / 60 + " " + T.dk, 174, 30, yok ? SOLUK : ALTIN)
    );
  }
  const pasif = !adimVar(yon, S, D.P);
  return svg(
    cizim(pasif ? SOLUK : KREM, pasif ? KUTU_SOLUK : KUTU) +
      yazi(S.phase === "running" ? "15 " + T.dk : T.sure, 174, 30, pasif ? SOLUK : GRI)
  );
}

function bitinceTusu(D, T) {
  const { S, P } = D;
  if (!S) return kapaliTus(islemSimge("shutdown", 98, 78, 96, SOLUK, ZEMIN), D, T);
  // Uyarida bu tus "simdi yap" olur: tamami islem renginde
  if (S.phase === "warning") {
    const u = T.simdi[S.action] || ["", ""], ir = IRENK[S.action] || GRI;
    return svg(yazi(u[0], 30, 22, KOYU) + islemSimge(S.action, 98, 92, 92, KOYU, ir) + yazi(u[1], 178, 30, KOYU), ir);
  }
  const calisiyor = S.phase === "running";
  const gecerli = calisiyor ? S.action : P.dk === 0 ? "none" : P.islem;
  const pasif = calisiyor ? S.infinite : P.dk === 0;
  // Bilinmeyen islem (ileride Insomnia'ya eklenen): gri simge ve "?" ile gosterilir, cizim bozulmaz.
  const renk = pasif ? SOLUK : IRENK[gecerli] || GRI;
  return svg(
    yazi(T.bitince, 30, 22, pasif ? SOLUK : GRI) +
      islemSimge(gecerli, 98, 92, 88, renk, ZEMIN) +
      yazi(T.kisa[gecerli] || "?", 178, 32, pasif ? SOLUK : gecerli === "none" ? KREM : renk)
  );
}

function ekranTusu(D, T) {
  const mon = (r) =>
    `<rect x="40" y="28" width="116" height="78" rx="12" fill="none" stroke="${r}" stroke-width="12"/>` +
    `<path d="M98 106v20M70 130h56" stroke="${r}" stroke-width="12" stroke-linecap="round" fill="none"/>`;
  const { S } = D;
  if (!S) return kapaliTus(mon(SOLUK), D, T);
  // Geri sayim: ustte ne oldugu, ortada kalan saniye, altta basinca ne olacagi (iptal)
  if (S.screen_in > 0)
    return svg(
      yazi(T.kapaniyor, 30, 22, ALTIN) + yazi(S.screen_in, 122, 88, KREM) +
        `<rect x="34" y="142" width="128" height="44" rx="22" fill="${KUTU}"/>` + yazi(T.iptal, 174, 28, KREM)
    );
  // Bitince tusuyla ayni duzen: ustte neyin, altta ne yapilacagi
  return svg(yazi(T.ekran, 30, 22, GRI) + `<g transform="translate(27.4 24) scale(0.72)">${mon(KREM)}</g>` + yazi(T.ekranKapat, 178, 32, KREM));
}

// Zil simgesi: (cx, cy) merkezli, 'boy' piksel.
function zil(cx, cy, boy, renk) {
  const o = boy / 24;
  const c = `fill="none" stroke="${renk}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"`;
  return (
    `<g transform="translate(${(cx - 12 * o).toFixed(1)} ${(cy - 12 * o).toFixed(1)}) scale(${o.toFixed(3)})">` +
    `<path ${c} d="M6 16.4V11a6 6 0 0 1 12 0v5.4l1.7 2.3H4.3z"/><path ${c} d="M10 21.7h4"/></g>`
  );
}
function kisaSure(dk, T) {
  if (dk < 60) return dk + " " + T.dk;
  if (dk % 60 === 0) return dk / 60 + " " + T.sa;
  return Math.floor(dk / 60) + ":" + iki(dk % 60);
}
function buyukSure(dk, y, T, renk) {
  if (dk < 60) return sayiBirim(dk, T.dk, y, 84, 34, renk);
  if (dk % 60 === 0) return sayiBirim(dk / 60, T.sa, y, 84, 34, renk);
  return yazi(Math.floor(dk / 60) + ":" + iki(dk % 60), y, 72, renk);
}
// Kalan sure: son dakikada saniye, bir saatten uzunsa saat:dakika.
function kalanYazi(sn, y, renk, T) {
  const k = Math.max(0, Math.round(Number(sn) || 0)), dk = Math.ceil(k / 60);
  if (k <= 60) return sayiBirim(k, T.sn, y, 76, 30, renk);
  if (dk >= 60) return yazi(Math.floor(dk / 60) + ":" + iki(dk % 60), y, 64, renk);
  return sayiBirim(dk, T.dk, y, 76, 30, renk);
}
function kisalt(s, n) {
  const a = Array.from(String(s));
  return a.length > n ? a.slice(0, n - 1).join("") + "…" : a.join("");
}

/**
 * Hatirlatici tusu. Oteki tuslarla ayni duzen: ustte ne oldugu, ortada deger, altta basinca ne olacagi.
 *   bosta     HATIRLAT / zil / baslangic suresi        -> basinca kurma kipi
 *   kur       altin zemin: HATIRLAT / sure / KUR       -> eksi-arti sureyi degistirir, basinca kurar
 *   bekliyor  HATIRLAT / kalan sure / ilerleme cubugu  -> basinca duzenleme kipi
 *   duzenle   altin zemin: IPTAL? / kalan sure / Sil   -> eksi-arti 5 dk oynatir, basinca siler
 *   caliyor   yanip sonen altin: zil / not / TAMAM     -> basinca kapatir
 * Calisan oturumu gosteren ana tus halka kullandigi icin burada bilerek cubuk var: iki sayac yan yana karismaz.
 */
function hatTusu(D, T) {
  const { S, K } = D;
  if (!S) return kapaliTus(zil(98, 80, 104, SOLUK), D, T);
  const R = S.reminders;
  if (!R) return svg(zil(98, 80, 104, SOLUK) + yazi(T.guncelle, 176, 28, ALTIN)); // hatirlatici 1.5.0 ile geldi
  if (R.due) {
    const zemin = D.yan ? ZEMIN : ALTIN, renk = D.yan ? ALTIN : KOYU;
    return svg(zil(98, 54, 84, renk) + yazi(kisalt(R.due.note || T.hatirlatma, 13), 134, 24, renk) + yazi(T.tamam, 180, 32, renk), zemin);
  }
  const bekleyen = Array.isArray(R.pending) ? R.pending : [];
  if (K && K.mod === "kur") return svg(yazi(T.hatirlat, 30, 22, KOYU) + buyukSure(K.dk, 124, T, KOYU) + yazi(T.kur, 180, 32, KOYU), ALTIN);
  const h = K && K.mod === "duzenle" ? hatBekleyen(S, K.id) : null;
  if (h) return svg(yazi(T.iptalmi, 30, 22, KOYU) + kalanYazi(h.left, 120, KOYU, T) + yazi(T.sil, 180, 32, KOYU), ALTIN);
  if (bekleyen.length) {
    const ilk = bekleyen[0], kalan = Number(ilk.left) || 0, toplam = Number(ilk.span) || 0;
    const oran = toplam > 0 ? Math.max(0, Math.min(1, kalan / toplam)) : 1;
    const ust = bekleyen.length > 1 ? T.hatirlat + " +" + (bekleyen.length - 1) : T.hatirlat;
    return svg(
      yazi(ust, 30, 22, ALTIN) + kalanYazi(kalan, 120, KREM, T) +
        `<rect x="28" y="150" width="140" height="16" rx="8" fill="${IZ}"/>` +
        `<rect x="28" y="150" width="${(16 + 124 * oran).toFixed(1)}" height="16" rx="8" fill="${ALTIN}"/>`
    );
  }
  const dk = Number.isInteger(R.default) && R.default > 0 ? R.default : 15;
  return svg(yazi(T.hatirlat, 30, 22, GRI) + zil(98, 92, 92, KREM) + yazi(kisaSure(dk, T), 178, 32, KREM));
}

export function tus(tur, D) {
  const T = METIN[D.dil] || METIN.en;
  if (tur === "hat") return hatTusu(D, T);
  if (tur === "ana") return anaTus(D, T);
  if (tur === "eksi") return adimTusu(-1, D, T);
  if (tur === "arti") return adimTusu(1, D, T);
  if (tur === "bitince") return bitinceTusu(D, T);
  return ekranTusu(D, T);
}
