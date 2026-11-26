/**
 * Insomnia - UlanziDeck eklentisi ana servisi (Node.js)
 *
 * Insomnia'nin "kumanda kapisi"na baglanir (bkz. Insomnia: insomnia/remote.py):
 *   %LOCALAPPDATA%\Insomnia\kumanda.json  -> kapi numarasi + anahtar + programin yeri
 *   GET  http://127.0.0.1:<kapi>/durum    -> oturum durumu
 *   POST http://127.0.0.1:<kapi>/komut    -> komut
 *
 * Alti tus vardir:
 *   ana      bostayken baslatir, calisirken durdurur, uyarida vazgecer
 *   eksi/arti bostayken baslatilacak sureyi secer; calisirken 15 dk cikarir/ekler
 *   bitince  sure bitince ne olacagini secer (yok, kapat, yeniden baslat, uyut, hazirda beklet); 60 sn'lik uyarida "simdi yap" olur
 *   ekran    ekrani 10 sn sonra kapatir; tekrar basinca iptal eder
 *   hat      hatirlatici (Insomnia 1.5.0+). Ilk basis "kurma kipi"ni acar: tus ve eksi/arti altin olur,
 *            eksi/arti birkac saniyeligine hatirlaticinin suresini ayarlar; ikinci basis kurar.
 *            Bekleyen hatirlatici varken ayni yol onu duzenler (eksi/arti 5 dk oynatir, ikinci basis siler).
 *            Calarken tek basis kapatir. Kipte bir sure dokunulmazsa hicbir sey yapmadan cikilir.
 *
 * Insomnia kapaliyken bir tusa basilirsa program tepside acilir; basilan tus
 * ana ya da ekran ise istek program acilinca yerine getirilir.
 */

import { spawn } from "child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import http from "http";
import { join } from "path";
import { UlanziApi } from "../plugin-common-node/index.js";
import { ADIM_SN, HAT_ADIM_SN, ISLEMLER, MERDIVEN, adimVar, hatAdimVar, hatBasamak, tus } from "./cizim.js";

const PLUGIN_UUID = "com.ulanzi.ulanzistudio.insomnia";
const TURLER = ["ana", "eksi", "arti", "bitince", "ekran", "hat"];
const YOKLAMA_MS = 500;
const ISTEK_MS = 1500;
const BAYAT_MS = 2000; // bundan eski durum bilgisine guvenilmez
const ACILMA_MS = 20000; // program acilirken en cok bu kadar beklenir
const CIFT_BASIS_MS = 500;
const SIMDI_KORUMA_MS = 2000; // uyari basladiktan sonra "simdi yap" bu kadar sure calismaz
const KUR_MS = 6000; // hatirlatici kurma kipi: son dokunustan sonra bu kadar surer
const HAT_CIFT_MS = 250; // hatirlatici tusunda iki basis bilerek yapilir; yalniz tus sekmesi elenir
const HAT_KORUMA_MS = 1000; // hatirlatici calmaya basladiktan sonra "tamam" bu kadar sure calismaz

const YEREL = process.env.LOCALAPPDATA || "";
const KAPI_DOSYASI = join(YEREL, "Insomnia", "kumanda.json");
const SECIM_DOSYASI = join(YEREL, "Insomnia", "ulanzi.json");
const VARSAYILAN_EXE = join(YEREL, "Programs", "Insomnia", "Insomnia.exe");

const $UD = new UlanziApi();

const tuslar = new Map(); // context -> tur
const sonSvg = new Map(); // context -> son gonderilen SVG
const sonBasis = new Map(); // context -> zaman
let P = { dk: 15, islem: "none" }; // secili sure ve bitis islemi
let S = null; // Insomnia'nin durumu; kapaliysa null
let exeYolu = "";
let acilmaSonu = 0; // program acilirken: beklemenin bitecegi an
let bekleyen = null; // program acilinca yollanacak komut
let eskiSurum = false; // program acildi ama kumanda kapisi gelmedi (1.2.0 oncesi Insomnia)
let uyariBasi = 0;
let K = null; // hatirlatici kurma kipi: { mod: "kur", dk, son } | { mod: "duzenle", id, son }; degilse null
let calanHat = null; // calan hatirlaticinin kimligi
let calmaBasi = 0;
let yan = false; // calan hatirlatici tusu her yoklamada renk degistirir
let sonDurumAni = 0;
let zamanlayici = null;
let yokluyor = false;

// ---------------------------------------------------------------- secim --

function secimiOku() {
  try {
    const v = JSON.parse(readFileSync(SECIM_DOSYASI, "utf8"));
    if (MERDIVEN.includes(v.dk)) P.dk = v.dk;
    if (ISLEMLER.includes(v.islem)) P.islem = v.islem;
  } catch (e) {
    /* dosya yok ya da bozuk: varsayilan kalir */
  }
}
function secimiYaz() {
  try {
    mkdirSync(join(YEREL, "Insomnia"), { recursive: true });
    writeFileSync(SECIM_DOSYASI, JSON.stringify(P));
  } catch (e) {
    /* yazilamazsa secim yalnizca bu oturumda gecerli olur */
  }
}

// ----------------------------------------------------------------- kapi --

function kapiBilgisi() {
  try {
    const v = JSON.parse(readFileSync(KAPI_DOSYASI, "utf8"));
    if (typeof v.exe === "string" && v.exe) exeYolu = v.exe;
    if (Number.isInteger(v.port) && v.port > 0 && typeof v.token === "string" && v.token) return v;
  } catch (e) {
    /* dosya yok: Insomnia hic acilmamis ya da eski surum */
  }
  return null;
}

function istek(yol, govde) {
  return new Promise((cozum) => {
    // Yanit yarida kesilse bile soz mutlaka sonuclanir; yoksa yoklama sonsuza dek kilitlenirdi.
    let bitti = false;
    const coz = (v) => {
      if (bitti) return;
      bitti = true;
      clearTimeout(emniyet);
      cozum(v);
    };
    const emniyet = setTimeout(() => coz(null), ISTEK_MS + 1000);
    const kapi = kapiBilgisi();
    if (!kapi) return coz(null);
    const veri = govde ? Buffer.from(JSON.stringify(govde)) : null;
    const basliklar = { "X-Insomnia-Anahtar": kapi.token };
    if (veri) {
      basliklar["Content-Type"] = "application/json";
      basliklar["Content-Length"] = veri.length;
    }
    const req = http.request(
      { host: "127.0.0.1", port: kapi.port, path: yol, method: veri ? "POST" : "GET", headers: basliklar, timeout: ISTEK_MS, agent: false },
      (res) => {
        let metin = "";
        res.setEncoding("utf8");
        res.on("data", (p) => {
          if (metin.length < 65536) metin += p;
        });
        res.on("error", () => coz(null));
        res.on("close", () => coz(null)); // "end" gelmeden kapandiysa
        res.on("end", () => {
          if (res.statusCode !== 200) return coz(null);
          try {
            coz(JSON.parse(metin));
          } catch (e) {
            coz(null);
          }
        });
      }
    );
    req.on("timeout", () => req.destroy());
    req.on("error", () => coz(null));
    req.end(veri || undefined);
  });
}

function durumAl(yeni) {
  const gecerli = yeni && yeni.app === "Insomnia" && typeof yeni.phase === "string" ? yeni : null;
  const simdi = Date.now();
  // Tuslar gorunmezken yoklama durur; eski bilgi "uyari zaten suruyordu" sanilmasin.
  const oncekiUyari = S && S.phase === "warning" && simdi - sonDurumAni < BAYAT_MS;
  if (gecerli && gecerli.phase === "warning" && !oncekiUyari) uyariBasi = simdi;
  sonDurumAni = simdi;
  S = gecerli;
  const R = S && S.reminders;
  if (!(R && R.due)) calanHat = null;
  else if (calanHat !== R.due.id) {
    calanHat = R.due.id;
    calmaBasi = simdi;
  }
  // Kip biter: suresi doldu, program kapandi, hatirlatici calmaya basladi ya da duzenlenen hatirlatici artik yok.
  if (K && (!R || R.due || simdi > K.son || (K.mod === "duzenle" && !(Array.isArray(R.pending) && R.pending.some((h) => h.id === K.id))))) K = null;
  if (S) {
    acilmaSonu = 0;
    eskiSurum = false;
    // Secili islem bu Insomnia'da yoksa (eski surum, uyku/hazirda bekletme kapali) tus
    // olmayacak bir seyi gostermesin.
    if (P.islem !== "none" && !islemVar(P.islem)) {
      P.islem = "none";
      secimiYaz();
    }
  }
}

async function komut(govde, context) {
  const yanit = await istek("/komut", govde);
  if (yanit && yanit.state) durumAl(yanit.state);
  if ((!yanit || !yanit.ok) && context) $UD.showAlert(context);
  ciz();
  return yanit;
}

async function yokla() {
  if (yokluyor) return;
  yokluyor = true;
  try {
    durumAl(await istek("/durum"));
    yan = !yan;
    if (S && bekleyen) {
      const b = bekleyen;
      bekleyen = null;
      // Suresi gecmis istek uygulanmaz: dakikalar sonra kendiliginden oturum baslamasin.
      // Komut simdi kurulur: secili islem bu Insomnia'da yoksa durumAl onu az once duzeltti.
      if (Date.now() <= b.son) await komut(b.tur === "ana" ? baslatKomutu() : { komut: "screen_off" }, b.context);
    }
    if (!S && acilmaSonu && Date.now() > acilmaSonu) {
      acilmaSonu = 0; // acildi ama kapi gelmedi
      bekleyen = null;
      eskiSurum = true;
    }
    ciz();
  } finally {
    yokluyor = false;
  }
}

function programiAc(context) {
  if (acilmaSonu) return; // zaten aciliyor
  kapiBilgisi(); // exe yolunu tazeler
  const exe = exeYolu && existsSync(exeYolu) ? exeYolu : VARSAYILAN_EXE;
  if (!existsSync(exe)) {
    $UD.logMessage(`[Insomnia] program bulunamadi: ${exe}`, "warn");
    $UD.showAlert(context);
    bekleyen = null;
    return;
  }
  try {
    spawn(exe, ["--tray"], { detached: true, stdio: "ignore" }).unref();
    acilmaSonu = Date.now() + ACILMA_MS;
  } catch (e) {
    $UD.logMessage(`[Insomnia] program acilamadi: ${e && e.message}`, "warn");
    $UD.showAlert(context);
    bekleyen = null;
  }
  ciz();
}

// ---------------------------------------------------------------- cizim --

function ciz() {
  if (K && Date.now() > K.son) K = null;
  const D = { S, P, K, yan, aciliyor: !S && acilmaSonu > 0, eski: eskiSurum, dil: (S && S.lang) || sonDil };
  if (S && S.lang) sonDil = S.lang;
  for (const [context, tur] of tuslar) {
    const svg = tus(tur, D);
    if (sonSvg.get(context) === svg) continue;
    sonSvg.set(context, svg);
    $UD.setBaseDataIcon(context, "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64"));
  }
}
let sonDil = "tr";

function motoruAyarla() {
  if (tuslar.size === 0) {
    if (zamanlayici) clearInterval(zamanlayici);
    zamanlayici = null;
    return;
  }
  if (!zamanlayici) {
    zamanlayici = setInterval(yokla, YOKLAMA_MS);
    yokla();
  }
}

// ---------------------------------------------------------------- tuslar --

function baslatKomutu() {
  // Secili islem bu Insomnia'da yoksa (eski surum) bitiste bir sey yapilmaz.
  const islem = P.dk === 0 || (S && !islemVar(P.islem)) ? "none" : P.islem;
  return { komut: "start", minutes: P.dk || null, infinite: P.dk === 0, action: islem };
}

function sureTusu(yon, context) {
  // Hatirlatici kurma kipinde bu tuslar oturumu degil hatirlaticiyi ayarlar.
  if (K && S && S.reminders) {
    if (!hatAdimVar(yon, S, K)) return;
    K.son = Date.now() + KUR_MS;
    if (K.mod === "kur") {
      K.dk = hatBasamak(K.dk, yon);
      return ciz();
    }
    return komut({ komut: "reminder_adjust", id: K.id, seconds: yon * HAT_ADIM_SN }, context);
  }
  if (!adimVar(yon, S, P)) return; // tus soluk: yapacak bir sey yok, uyari da gosterme
  if (S.phase === "running") return komut({ komut: "adjust", seconds: yon * ADIM_SN }, context);
  let i = MERDIVEN.indexOf(P.dk);
  if (i < 0) i = 3;
  const j = Math.max(0, Math.min(MERDIVEN.length - 1, i + yon));
  if (j === i) return;
  P.dk = MERDIVEN[j];
  secimiYaz();
  ciz();
}

// Insomnia bu islemi yapabiliyor mu? Yeni surumler listeyi kendisi bildirir (actions).
function islemVar(islem) {
  if (Array.isArray(S.actions)) return S.actions.includes(islem);
  if (islem === "sleep") return false; // 1.2.0: uyku yok
  return islem !== "hibernate" || S.hibernate !== false;
}

function siradakiIslem(simdiki) {
  let i = ISLEMLER.indexOf(simdiki);
  for (let n = 0; n < ISLEMLER.length; n++) {
    i = (i + 1) % ISLEMLER.length;
    if (islemVar(ISLEMLER[i])) return ISLEMLER[i];
  }
  return "none";
}

function bitinceTusu(context) {
  if (S.phase === "warning") {
    // Yeni baslamis uyarida yanlislikla basmaya karsi kisa koruma
    if (Date.now() - uyariBasi < SIMDI_KORUMA_MS) return;
    return komut({ komut: "act_now" }, context);
  }
  if (S.phase === "running") {
    if (S.infinite) return $UD.showAlert(context);
    const yeni = siradakiIslem(S.action);
    P.islem = yeni;
    secimiYaz();
    return komut({ komut: "set_action", action: yeni }, context);
  }
  if (P.dk === 0) return $UD.showAlert(context); // suresiz oturumun bitisi olmaz
  P.islem = siradakiIslem(P.islem);
  secimiYaz();
  ciz();
}

function hatTusu(context) {
  const R = S.reminders;
  if (!R) return $UD.showAlert(context); // Insomnia 1.5.0'dan eski: tus "Guncelle" gosterir
  if (R.due) {
    // Tam calmaya basladigi anda (baska bir sey icin) basilan tus hatirlaticiyi gorulmeden kapatmasin.
    if (Date.now() - calmaBasi < HAT_KORUMA_MS) return;
    return komut({ komut: "reminder_dismiss", id: R.due.id }, context);
  }
  if (K && K.mod === "kur") {
    const dk = K.dk;
    K = null;
    return komut({ komut: "reminder_add", minutes: dk }, context);
  }
  if (K && K.mod === "duzenle") {
    const id = K.id;
    K = null;
    return komut({ komut: "reminder_remove", id }, context);
  }
  const son = Date.now() + KUR_MS;
  const bekleyenler = Array.isArray(R.pending) ? R.pending : [];
  const dk = Number.isInteger(R.default) && R.default > 0 ? R.default : 15;
  K = bekleyenler.length ? { mod: "duzenle", id: bekleyenler[0].id, son } : { mod: "kur", dk, son };
  ciz();
}

async function bas(context, tur) {
  const simdi = Date.now();
  if (tur === "hat") {
    if (simdi - (sonBasis.get(context) || 0) < HAT_CIFT_MS) return;
    sonBasis.set(context, simdi);
  }
  const tekrarKorumali = tur === "ana" || tur === "ekran" || (tur === "bitince" && S && S.phase === "warning");
  if (tekrarKorumali) {
    if (simdi - (sonBasis.get(context) || 0) < CIFT_BASIS_MS) return;
    sonBasis.set(context, simdi);
  }
  // Basis aninda guncel durumu al: yarim saniyelik eski bilgiyle karar verme.
  durumAl(await istek("/durum"));

  if (!S) {
    if (tur === "ana" || tur === "ekran") bekleyen = { tur, context, son: simdi + ACILMA_MS };
    programiAc(context);
    return;
  }
  if (tur === "hat") return hatTusu(context);
  if (tur === "ana") {
    if (S.phase === "warning") return komut({ komut: "cancel" }, context);
    if (S.phase === "running") return komut({ komut: "stop" }, context);
    return komut(baslatKomutu(), context);
  }
  if (tur === "ekran") return komut({ komut: S.screen_in > 0 ? "cancel_screen_off" : "screen_off" }, context);
  if (tur === "eksi") return sureTusu(-1, context);
  if (tur === "arti") return sureTusu(1, context);
  return bitinceTusu(context);
}

// ------------------------------------------------------------- olaylar --

// Olaydaki uuid her zaman aksiyon uuid'si olmayabiliyor; context uzerinden de bakilir.
function turBul(jsn) {
  const uuid = (jsn && jsn.uuid) || "";
  const ctx = (jsn && jsn.context) || "";
  for (const tur of TURLER) {
    const aksiyon = `${PLUGIN_UUID}.${tur}`;
    if (uuid === aksiyon || uuid.endsWith("." + tur) || ctx.startsWith(aksiyon) || ctx.includes("." + tur + "___")) return tur;
  }
  return null;
}

function ekle(jsn) {
  const tur = turBul(jsn);
  if (!tur || !jsn.context) return;
  tuslar.set(jsn.context, tur);
  sonSvg.delete(jsn.context);
  ciz();
  motoruAyarla();
}

function cikar(context) {
  tuslar.delete(context);
  sonSvg.delete(context);
  sonBasis.delete(context);
}

function main() {
  secimiOku();
  $UD.onConnected(() => $UD.logMessage("[Insomnia] baglandi", "info"));
  $UD.onAdd(ekle);
  $UD.onSetActive((jsn) => {
    if (!jsn.context) return;
    if (jsn.active) ekle(jsn);
    else {
      cikar(jsn.context);
      motoruAyarla();
    }
  });
  $UD.onRun((jsn) => {
    const tur = turBul(jsn);
    if (!tur || !jsn.context) return;
    if (!tuslar.has(jsn.context)) ekle(jsn);
    bas(jsn.context, tur).catch((e) => {
      $UD.showAlert(jsn.context);
      $UD.logMessage(`[Insomnia] tus hatasi: ${e && e.message}`, "warn");
    });
  });
  $UD.onClear((jsn) => {
    for (const item of (jsn && jsn.param) || []) if (item.context) cikar(item.context);
    motoruAyarla();
  });
  const kapat = () => process.exit(0);
  // Ulanzi Studio kapaninca baglanti kopar; kitaplik yeniden baglanmaz. Sahipsiz kalip
  // bos yere yoklamayi surdurmemek icin eklenti de kapanir (Studio acilinca yeniden baslatir).
  $UD.onClose(kapat);
  $UD.connect(PLUGIN_UUID);
  process.on("SIGINT", kapat);
  process.on("SIGTERM", kapat);
}

// Sinamalar bu dosyayi ice aktarmaz; dogrudan calistirilinca baslar.
main();
