// Tus cizimlerinin sinamasi:  node --test ulanzi/test
//
// Cihaz SVG'yi kati kurallarla okuyor: tarayicinin hos gordugu bir hata (ornegin ayni
// ozelligin iki kez yazilmasi) cihazda simgenin hic cizilmemesine yol aciyor. Bu yuzden
// uretilebilen butun tus goruntuleri burada kati bir XML denetiminden gecirilir.
import assert from "node:assert/strict";
import { test } from "node:test";
import { ISLEMLER, MERDIVEN, adimVar, tus } from "../com.ulanzi.ulanzistudio.insomnia.ulanziPlugin/plugin/cizim.js";

const TURLER = ["ana", "eksi", "arti", "bitince", "ekran"];
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
