; Insomnia kurulum paketi (Inno Setup 6).
;
;   python build.py        exe'yi derler, Inno Setup varsa bu dosyadan kurulum paketini de üretir
;
; Yönetici izni istemez: program %LOCALAPPDATA%\Programs\Insomnia altına kurulur.
; Ulanzi eklentisi yalnız bilgisayarda Ulanzi Studio varsa sorulur.

#ifndef Surum
  #define Surum "0.0.0"
#endif
#define Eklenti "com.ulanzi.ulanzistudio.insomnia.ulanziPlugin"
#define CalistirAnahtari "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{8E0C3B4A-6F1D-4E57-9C2A-1D5B7A3F9E21}
AppName=Insomnia
AppVersion={#Surum}
AppVerName=Insomnia {#Surum}
AppPublisher=ufukenginaydin
VersionInfoVersion={#Surum}
PrivilegesRequired=lowest
DefaultDirName={autopf}\Insomnia
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
UninstallDisplayIcon={app}\Insomnia.exe
UninstallDisplayName=Insomnia
SetupIconFile=..\dist\Insomnia.ico
OutputDir=..\dist
OutputBaseFilename=Insomnia-Setup-{#Surum}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Çalışan kopyayı aşağıdaki kod kapatır (oturum varsa sorarak).
CloseApplications=no
UsePreviousTasks=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
tr.Ulanzi=Ulanzi D200 eklentisini de kur (Ulanzi Studio'yu yeniden başlatman gerekir)
en.Ulanzi=Also install the Ulanzi D200 plugin (restart Ulanzi Studio afterwards)
de.Ulanzi=Auch das Ulanzi-D200-Plugin installieren (Ulanzi Studio danach neu starten)
fr.Ulanzi=Installer aussi le plugin Ulanzi D200 (redémarrez ensuite Ulanzi Studio)
es.Ulanzi=Instalar también el complemento para Ulanzi D200 (reinicia Ulanzi Studio después)
tr.Acilis=Windows açılışında başlat (saatin yanında)
en.Acilis=Start with Windows (in the tray)
de.Acilis=Mit Windows starten (im Infobereich)
fr.Acilis=Lancer au démarrage de Windows (dans la zone de notification)
es.Acilis=Iniciar con Windows (en la bandeja)
tr.Masaustu=Masaüstüne kısayol koy
en.Masaustu=Create a desktop shortcut
de.Masaustu=Desktop-Verknüpfung erstellen
fr.Masaustu=Créer un raccourci sur le bureau
es.Masaustu=Crear un acceso directo en el escritorio
tr.Baslat=Insomnia'yı başlat
en.Baslat=Start Insomnia
de.Baslat=Insomnia starten
fr.Baslat=Lancer Insomnia
es.Baslat=Iniciar Insomnia
tr.OturumVar=Insomnia şu anda bir oturum yürütüyor. Kurulum onu durdurup programı kapatacak.%n%nDevam edilsin mi?
en.OturumVar=Insomnia is running a session right now. Setup will stop it and close the program.%n%nContinue?
de.OturumVar=Insomnia führt gerade eine Sitzung aus. Setup beendet sie und schließt das Programm.%n%nFortfahren?
fr.OturumVar=Insomnia exécute une session en ce moment. L'installation va l'arrêter et fermer le programme.%n%nContinuer ?
es.OturumVar=Insomnia está ejecutando una sesión ahora mismo. La instalación la detendrá y cerrará el programa.%n%n¿Continuar?
tr.Kapanmadi=Insomnia kapatılamadı. Saatin yanındaki simgeden çıkıp yeniden dene.
en.Kapanmadi=Insomnia could not be closed. Exit it from the tray icon and try again.
de.Kapanmadi=Insomnia konnte nicht geschlossen werden. Beende es über das Infobereichssymbol und versuche es erneut.
fr.Kapanmadi=Impossible de fermer Insomnia. Quittez-le depuis l'icône de la zone de notification et réessayez.
es.Kapanmadi=No se pudo cerrar Insomnia. Sal desde el icono de la bandeja e inténtalo de nuevo.

[Tasks]
Name: "ulanzi"; Description: "{cm:Ulanzi}"; Check: UlanziVar
Name: "acilis"; Description: "{cm:Acilis}"; Flags: checkedonce
Name: "masaustu"; Description: "{cm:Masaustu}"; Flags: unchecked

[Files]
Source: "..\dist\Insomnia.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ulanzi\{#Eklenti}\*"; DestDir: "{userappdata}\Ulanzi\UlanziDeck\Plugins\{#Eklenti}"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: ulanzi

[Icons]
Name: "{autoprograms}\Insomnia"; Filename: "{app}\Insomnia.exe"
Name: "{autodesktop}\Insomnia"; Filename: "{app}\Insomnia.exe"; Tasks: masaustu

[Registry]
; Programın kendi "Windows açılışında başlat" ayarıyla aynı değer (bkz. insomnia/startup.py).
Root: HKCU; Subkey: "{#CalistirAnahtari}"; ValueType: string; ValueName: "Insomnia"; ValueData: """{app}\Insomnia.exe"" --tray"; Tasks: acilis

[Run]
Filename: "{app}\Insomnia.exe"; Description: "{cm:Baslat}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Önbellek, kumanda dosyası ve tuş seçimi. Ayarlar (%APPDATA%\Insomnia) bilerek bırakılır.
Type: filesandordirs; Name: "{localappdata}\Insomnia"
Type: filesandordirs; Name: "{userappdata}\Ulanzi\UlanziDeck\Plugins\{#Eklenti}"

[Code]
const
  MUTEX = 'Local\Insomnia.Instance';

function UlanziVar: Boolean;
begin
  Result := DirExists(ExpandConstant('{userappdata}\Ulanzi\UlanziDeck'))
    or DirExists(ExpandConstant('{commonpf32}\Ulanzi Studio'))
    or DirExists(ExpandConstant('{commonpf}\Ulanzi Studio'));
end;

function Calisiyor: Boolean;
begin
  Result := CheckForMutexes(MUTEX);
end;

{ Çalışan Insomnia'yı kapatır. Exe: kurulu kopyanın yolu. Başarılıysa True. }
function InsomniayiKapat(Exe: String; Sor: Boolean): Boolean;
var
  Kod, I: Integer;
begin
  Result := True;
  if not Calisiyor then
    Exit;
  if FileExists(Exe) then
  begin
    { --oturum-var: oturum sürüyorsa 3 ile çıkar (1.4.0 ve sonrası; eskiler pencereyi gösterip 0 döner). }
    if Sor and Exec(Exe, '--oturum-var', '', SW_HIDE, ewWaitUntilTerminated, Kod) and (Kod = 3) then
      if SuppressibleMsgBox(CustomMessage('OturumVar'), mbConfirmation, MB_YESNO, IDYES) <> IDYES then
      begin
        Result := False;
        Exit;
      end;
    Exec(Exe, '--cik', '', SW_HIDE, ewWaitUntilTerminated, Kod);
    Log(Format('Insomnia: --cik yollandi, cikis kodu %d', [Kod]));
    for I := 1 to 20 do
    begin
      if not Calisiyor then
        Break;
      Sleep(250);
    end;
  end;
  if Calisiyor then
  begin
    { Eski sürüm --cik bilmez ya da program yanıt vermiyor. }
    Log('Insomnia: kendiliginden kapanmadi, zorla kapatiliyor');
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM Insomnia.exe', '', SW_HIDE, ewWaitUntilTerminated, Kod);
    for I := 1 to 20 do
    begin
      if not Calisiyor then
        Break;
      Sleep(250);
    end;
  end;
  Sleep(1000); { exe üzerindeki dosya kilidi biraz geç kalkıyor }
  Result := not Calisiyor;
  Log(Format('Insomnia: kapandi mi = %d', [Ord(Result)]));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not InsomniayiKapat(ExpandConstant('{app}\Insomnia.exe'), True) then
    Result := CustomMessage('Kapanmadi');
end;

function InitializeUninstall: Boolean;
begin
  Result := InsomniayiKapat(ExpandConstant('{app}\Insomnia.exe'), True);
  if not Result then
    MsgBox(CustomMessage('Kapanmadi'), mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Deger: String;
begin
  { "Açılışta başlat" programın içinden de açılabiliyor; bu kopyayı gösteriyorsa kaldırılır. }
  if CurUninstallStep = usPostUninstall then
    if RegQueryStringValue(HKCU, '{#CalistirAnahtari}', 'Insomnia', Deger) then
      if Pos(Lowercase(ExpandConstant('{app}\')), Lowercase(Deger)) > 0 then
        RegDeleteValue(HKCU, '{#CalistirAnahtari}', 'Insomnia');
end;
