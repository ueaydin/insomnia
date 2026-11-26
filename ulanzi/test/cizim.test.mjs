// Tus cizimlerinin sinamasi:  node --test ulanzi/test
//
// Cihaz SVG'yi kati kurallarla okuyor: tarayicinin hos gordugu bir hata (ornegin ayni
// ozelligin iki kez yazilmasi) cihazda simgenin hic cizilmemesine yol aciyor. Bu yuzden
// uretilebilen butun tus goruntuleri burada kati bir XML denetiminden gecirilir.
import assert from "node:assert/strict";
import { test } from "node:test";
import { HAT_MERDIVEN, ISLEMLER, MERDIVEN, adimVar, hatAdimVar, hatBasamak, tus } from "../com.ulanzi.ulanzistudio.insomnia.ulanziPlugin/plugin/cizim.js";

const TURLER = ["ana", "eksi", "arti", "bitince", "ekran", "hat"];
const IZINLI = new Set(["svg", "rect", "circle", "path", "text", "g"]); // bilerek dar: mask, tspan, gradyan yok

// Kucuk, kati bir XML okuyucu: etiketler dengeli, ozellikler tekil ve tirnakli, metinde cplak & ve < yok.
function xmlDenetle(s) {
  const yigin = [];
  let i = 0, kok = 0;
  while (i < s.length) {
    if (s[i] !== "<") {
      const j = s.indexOf("<", i) < 0 ? s.length : s.indexOf("<", i);
      const metin = s.slice(i, j);
      assert.ok(!/&(?!(amp|lt|gt|quot|apos);)/.test(metin), "kacissiz & : " + metin);
      assert.ok(yigin.length > 0 || !metin.trim(), "kok disinda metin");
      i = j;
      continue;
    }
    const j = s.indexOf(">", i);
    assert.ok(j > 0, "kapanmayan etiket");
    const ic = s.slice(i + 1, j);
    i = j + 1;
    if (ic[0] === "/") {
      assert.equal(yigin.pop(), ic.slice(1), "etiketler dengesiz");
      continue;
    }
    const kendi = ic.endsWith("/");
    const m = /^([a-zA-Z]+)((?:\s+[a-zA-Z:-]+="[^"<]*")*)\s*\/?$/.exec(ic);
    assert.ok(m, "bozuk etiket: <" + ic + ">");
    assert.ok(IZINLI.has(m[1]), "izinsiz etiket: " + m[1]);
    const adlar = [...m[2].matchAll(/\s+([a-zA-Z:-]+)="([^"<]*)"/g)].map((x) => x[1]);
    assert.equal(new Set(adlar).size, adlar.length, "ayni ozellik iki kez: <" + ic + ">");
    for (const x of m[2].matchAll(/="([^"<]*)"/g)) {
      assert.ok(!/undefined|NaN|null|Infinity/.test(x[1]), "bozuk deger: <" + ic + ">");
      assert.ok(!/&(?!(amp|lt|gt|quot|apos);)/.test(x[1]), "kacissiz & : <" + ic + ">");
    }
    if (yigin.length === 0) kok++;
    if (!kendi) yigin.push(m[1]);
  }
  assert.equal(yigin.length, 0, "kapanmayan etiket kaldi");
  assert.equal(kok, 1, "tek kok olmali");
}

function durumlar() {
  const d = [null];
  const taban = { app: "Insomnia", infinite: false, total: 0, remaining: 0, action: "none", screen_in: 0, warn_in: 0, ending: false };
  d.push({ ...taban, phase: "idle" });
  d.push({ ...taban, phase: "idle", screen_in: 10 }, { ...taban, phase: "idle", screen_in: 1 });
  for (const action of ISLEMLER) {
    for (const [remaining, total] of [[86400, 86400], [5400, 7200], [3600, 3600], [3599, 3600], [1500, 1800], [61, 900], [60, 900], [1, 900], [0, 900], [900, 0]])
      for (const ending of [false, true]) d.push({ ...taban, phase: "running", action, remaining, total, ending });
    for (const warn_in of [60, 9, 0]) d.push({ ...taban, phase: "warning", action, warn_in, total: 900 });
  }
  d.push({ ...taban, phase: "running", infinite: true });
  d.push({ ...taban, phase: "running", action: "gelecekte-eklenen", remaining: 100, total: 900 }); // bilinmeyen islem
  d.push({ ...taban, phase: "warning", action: "gelecekte-eklenen", warn_in: 5 });
  return d;
}

test("butun tus goruntuleri gecerli ve sade SVG", () => {
  let sayi = 0;
  for (const dil of ["tr", "en", "de"])
    for (const S of durumlar())
      for (const dk of MERDIVEN)
        for (const islem of ISLEMLER)
          for (const ek of S ? [{}] : [{}, { aciliyor: true }, { eski: true }, { eski: true, aciliyor: true }])
            for (const tur of TURLER) {
              const s = tus(tur, { S, P: { dk, islem }, dil, ...ek });
              try {
                xmlDenetle(s);
              } catch (e) {
                throw new Error(`${tur} ${dil} ${JSON.stringify(S)} P=${dk}/${islem}: ${e.message}`);
              }
              assert.ok(s.startsWith('<svg xmlns="http://www.w3.org/2000/svg" width="196" height="196"'));
              assert.ok(!s.includes(">undefined<") && !s.includes(">NaN"), `${tur}: bos yazi`);
              sayi++;
            }
  assert.ok(sayi > 10000);
});

// ---------------------------------------------------------------- hatirlatici tusu --

const H = (id, left, span, note) => ({ id, time: "14:30", tomorrow: false, note: note || "", show: true, sound: true, left, span });
function hatDurumlari() {
  const R = (pending, due, ek) => ({ pending, due: due || null, max: 3, snooze: 10, default: 15, ...ek });
  const liste = [
    R([]), R([], null, { default: 26 }), R([], null, { default: 90 }), R([], null, { default: 240 }), R([], null, { default: undefined }),
    R([H("a", 900, 900)]), R([H("a", 61, 900)]), R([H("a", 60, 900)]), R([H("a", 1, 900)]), R([H("a", 0, 900)]),
    R([H("a", 5400, 7200)]), R([H("a", 86400, 86400)]), R([H("a", 300, 0)]), R([H("a", 900, 300)]),
    R([H("a", 120, 600), H("b", 900, 900)]), R([H("a", 120, 600), H("b", 900, 900), H("c", 3600, 3600)]),
    R([H("a", undefined, undefined)]), R(undefined),
    R([], { id: "d", note: "Çayı kapat", time: "14:30", late: false, more: 0 }),
    R([], { id: "d", note: "", time: "14:30", late: true, more: 2 }),
    R([H("a", 900, 900)], { id: "d", note: "Çok uzun bir not: <rapor> & toplantı odası", time: "14:30", late: false, more: 0 }),
  ];
  const taban = { app: "Insomnia", infinite: false, total: 900, remaining: 600, action: "none", screen_in: 0, warn_in: 0, ending: false };
  const d = [];
  for (const reminders of liste)
    for (const phase of ["idle", "running", "warning"]) d.push({ ...taban, phase, reminders });
  return d;
}
const KIPLER = [null, { mod: "kur", dk: 15 }, { mod: "kur", dk: 1 }, { mod: "kur", dk: 26 }, { mod: "kur", dk: 90 }, { mod: "kur", dk: 240 }, { mod: "duzenle", id: "a" }, { mod: "duzenle", id: "yok" }];

test("hatirlatici tusu ve kurma kipindeki sure tuslari gecerli ve sade SVG", () => {
  let sayi = 0;
  for (const dil of ["tr", "en", "de"])
    for (const S of hatDurumlari())
      for (const K of KIPLER)
        for (const yan of [false, true])
          for (const tur of ["hat", "eksi", "arti"]) {
            const s = tus(tur, { S, P: { dk: 15, islem: "none" }, K, yan, dil });
            try {
              xmlDenetle(s);
            } catch (e) {
              throw new Error(`${tur} ${dil} K=${JSON.stringify(K)} ${JSON.stringify(S.reminders)}: ${e.message}`);
            }
            assert.ok(!s.includes(">undefined") && !s.includes(">NaN") && !s.includes("undefined<"), `${tur}: bos yazi ${s}`);
            sayi++;
          }
  assert.ok(sayi > 3000);
});

test("hatirlatici tusu her durumda farkli gorunur", () => {
  const taban = { app: "Insomnia", phase: "idle", reminders: { pending: [], due: null, max: 3, snooze: 10, default: 15 } };
  const bekleyen = { ...taban, reminders: { ...taban.reminders, pending: [H("a", 600, 900)] } };
  const calan = { ...taban, reminders: { ...taban.reminders, due: { id: "d", note: "Çay", time: "14:30", late: false, more: 0 } } };
  const ciz = (S, K, yan) => tus("hat", { S, P: { dk: 15, islem: "none" }, K: K || null, yan: !!yan, dil: "tr" });
  const hepsi = [
    ciz(null), ciz({ app: "Insomnia", phase: "idle" }), ciz(taban), ciz(taban, { mod: "kur", dk: 15 }), ciz(taban, { mod: "kur", dk: 20 }),
    ciz(bekleyen), ciz(bekleyen, { mod: "duzenle", id: "a" }), ciz(calan), ciz(calan, null, true),
  ];
  assert.equal(new Set(hepsi).size, hepsi.length);
  assert.ok(/>Güncelle</.test(hepsi[1]), "eski Insomnia'da Guncelle yazmali");
  assert.ok(/>KUR</.test(hepsi[3]) && />15</.test(hepsi[3]));
  assert.ok(/>İPTAL\?</.test(hepsi[6]) && />Sil</.test(hepsi[6]));
  assert.ok(/>Çay</.test(hepsi[7]) && />TAMAM</.test(hepsi[7]));
  // Not yoksa "Hatırlatma"; uzun not kisalir, ozel karakterler kacisli yazilir.
  const uzun = { ...taban, reminders: { ...taban.reminders, due: { id: "d", note: "<b>Çok & uzun bir not</b>", time: "1", late: false, more: 0 } } };
  assert.ok(/>&lt;b&gt;Çok &amp; uzu…</.test(ciz(uzun)), ciz(uzun));
  assert.ok(/>Hatırlatma</.test(ciz({ ...taban, reminders: { ...taban.reminders, due: { id: "d", note: "", time: "1", late: true, more: 0 } } })));
  // Kurma kipinde sure tuslari oturum tuslarindan farkli (altin) cizilir; kip yokken eskisi gibi.
  const arti = (K) => tus("arti", { S: taban, P: { dk: 15, islem: "none" }, K, dil: "tr" });
  assert.notEqual(arti(null), arti({ mod: "kur", dk: 15 }));
  assert.ok(/>Süre</.test(arti(null)) && />Hatırlat</.test(arti({ mod: "kur", dk: 15 })));
  assert.ok(/>5 dk</.test(tus("arti", { S: bekleyen, P: { dk: 15, islem: "none" }, K: { mod: "duzenle", id: "a" }, dil: "tr" })));
  // Eski Insomnia (reminders yok): kip olsa bile sure tuslari oturum tusu olarak kalir.
  const eski = { app: "Insomnia", phase: "idle" };
  assert.equal(tus("arti", { S: eski, P: { dk: 15, islem: "none" }, K: { mod: "kur", dk: 15 }, dil: "tr" }), tus("arti", { S: eski, P: { dk: 15, islem: "none" }, K: null, dil: "tr" }));
});

test("hatirlatici sure basamaklari", () => {
  assert.equal(hatBasamak(15, 1), 20);
  assert.equal(hatBasamak(15, -1), 10);
  assert.equal(hatBasamak(26, 1), 30); // Ayarlar'dan gelen ara deger en yakin basamaga gider
  assert.equal(hatBasamak(26, -1), 20);
  assert.equal(hatBasamak(1, -1), null);
  assert.equal(hatBasamak(HAT_MERDIVEN[HAT_MERDIVEN.length - 1], 1), null);
  assert.equal(hatBasamak(1000, 1), null);
  assert.equal(hatBasamak(1000, -1), 240);
  const S = { reminders: { pending: [H("a", 359, 900), H("b", 86400 - 200, 86400)] } };
  assert.equal(hatAdimVar(-1, S, { mod: "kur", dk: 1 }), false);
  assert.equal(hatAdimVar(1, S, { mod: "kur", dk: 1 }), true);
  assert.equal(hatAdimVar(-1, S, { mod: "duzenle", id: "a" }), false); // 59 sn kalirdi
  assert.equal(hatAdimVar(1, S, { mod: "duzenle", id: "a" }), true);
  assert.equal(hatAdimVar(1, S, { mod: "duzenle", id: "b" }), false); // 24 saati asardi
  assert.equal(hatAdimVar(1, S, { mod: "duzenle", id: "yok" }), false);
  assert.equal(hatAdimVar(1, S, null), false);
  assert.equal(hatAdimVar(1, { phase: "idle" }, { mod: "kur", dk: 15 }), false); // eski Insomnia
  assert.equal(hatAdimVar(1, null, { mod: "kur", dk: 15 }), false);
});

test("her islemin kendi simgesi ve yazisi var", () => {
  const gorulen = new Set();
  for (const islem of ISLEMLER) {
    const s = tus("bitince", { S: { phase: "idle" }, P: { dk: 30, islem }, dil: "tr" });
    assert.ok(!gorulen.has(s), islem + " baskasiyla ayni ciziliyor");
    gorulen.add(s);
    if (islem !== "none") {
      const u = tus("bitince", { S: { phase: "warning", action: islem, warn_in: 30 }, P: { dk: 30, islem }, dil: "tr" });
      assert.ok(/<text[^>]*>ŞİMDİ/.test(u), islem + ": uyarida simdi yazisi yok");
    }
  }
});

test("sure tuslari gidemeyecegi yonde pasif", () => {
  const bos = { phase: "idle" };
  assert.equal(adimVar(-1, bos, { dk: MERDIVEN[0] }), false);
  assert.equal(adimVar(1, bos, { dk: MERDIVEN[0] }), true);
  assert.equal(adimVar(1, bos, { dk: 0 }), false);
  assert.equal(adimVar(-1, bos, { dk: 0 }), true);
  assert.equal(adimVar(-1, { phase: "running", remaining: 959 }, {}), false);
  assert.equal(adimVar(-1, { phase: "running", remaining: 960 }, {}), true);
  assert.equal(adimVar(1, { phase: "running", remaining: 1, infinite: true }, {}), false);
  assert.equal(adimVar(1, { phase: "warning" }, {}), false);
  assert.equal(adimVar(-1, null, { dk: 15 }), true); // kapaliyken basis programi acar
});
