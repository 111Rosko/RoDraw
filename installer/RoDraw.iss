; Inno Setup script for RoDraw.
;
; Build the app first (build/build.ps1), then compile this with Inno Setup 6.
; Produces installer/Output/RoDraw-Setup-1.3.2.exe
;
; Defaults to a per-user install so it works on a locked-down school PC
; without an administrator password; the user can still choose "all users"
; from the privileges dialog if they have rights.

#define AppName       "RoDraw"
#define AppVersion    "1.3.2"
#define AppPublisher  "Ростислав Лозанов"
#define AppExe        "RoDraw.exe"

[Setup]
AppId={{8F2C1A43-6B7E-4E0D-9C15-2A7D5E3B91F4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}

; Full classic wizard: Welcome -> Destination folder -> Start Menu folder ->
; Desktop icon -> Ready -> Finish. Inno 6 hides the welcome page by default,
; so it has to be asked for explicitly.
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no
DisableReadyPage=no
AllowNoIcons=yes

OutputDir=Output
OutputBaseFilename={#AppName} Setup
SetupIconFile=..\rodraw\resources\rodraw.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Per-user by default; the wizard offers to elevate for an all-users install.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Refuse to install over a running copy -- the files would be locked.
AppMutex=RoDraw.SingleInstance.Mutex

; Keep the uninstaller out of the install root. Inno always names it
; unins000.exe, which looks out of place next to the program; tucked in with
; the support files the root holds just RoDraw.exe and one folder.
UninstallFilesDir={app}\RoDraw

; Always ask which language, rather than silently following the Windows
; display language: the person installing may well want a different one.
ShowLanguageDialog=yes

[Languages]
; English first so it is the default, Bulgarian immediately after it, then the
; rest. These are the translations Inno Setup ships, so nothing extra has to
; be downloaded to build the installer.
Name: "english";    MessagesFile: "compiler:Default.isl"
Name: "bulgarian";  MessagesFile: "compiler:Languages\Bulgarian.isl"
Name: "german";     MessagesFile: "compiler:Languages\German.isl"
Name: "spanish";    MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french";     MessagesFile: "compiler:Languages\French.isl"
Name: "italian";    MessagesFile: "compiler:Languages\Italian.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "russian";    MessagesFile: "compiler:Languages\Russian.isl"
Name: "turkish";    MessagesFile: "compiler:Languages\Turkish.isl"
Name: "ukrainian";  MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
; Deliberately no "start at sign-in" task: RoDraw owns that setting itself
; (Settings > General). Offering it in both places would create two
; independent startup entries and launch RoDraw twice.
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"

[Files]
; The whole PyInstaller one-folder build.
Source: "..\dist\RoDraw\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings live in the user's profile; leave them unless asked to remove.
Type: dirifempty; Name: "{app}"

[Code]
{ Walk up until we hit a folder that exists. The proposed install directory
  normally does not exist yet, and handing the browse dialog a missing path
  makes it give up and open somewhere unrelated, like Documents. }
function NearestExistingDir(Path: String): String;
var
  Parent: String;
begin
  Result := Path;
  while (Result <> '') and not DirExists(Result) do
  begin
    Parent := ExtractFileDir(Result);
    if Parent = Result then
    begin
      Result := '';
      Exit;
    end;
    Result := Parent;
  end;
end;

procedure DirBrowseButtonClick(Sender: TObject);
var
  Dir, Start: String;
begin
  Start := NearestExistingDir(WizardForm.DirEdit.Text);
  if Start = '' then
    Start := WizardForm.DirEdit.Text;
  Dir := Start;
  { The third argument is what adds the "New folder" button. The stock Browse
    button calls the same dialog without it, so anyone wanting RoDraw in a
    folder that does not exist yet had to leave Setup and make it in Explorer
    first. Whatever is picked is used verbatim -- no app name appended, since
    with a New folder button people create the exact folder they want. }
  if BrowseForFolder(SetupMessage(msgBrowseDialogLabel), Dir, True) then
    WizardForm.DirEdit.Text := Dir;
end;

procedure InitializeWizard;
begin
  WizardForm.DirBrowseButton.OnClick := @DirBrowseButtonClick;
end;

function AppLanguageCode: String;
begin
  { Inno language name -> the code RoDraw stores in settings.json. }
  if ActiveLanguage = 'bulgarian' then Result := 'bg'
  else if ActiveLanguage = 'german' then Result := 'de'
  else if ActiveLanguage = 'spanish' then Result := 'es'
  else if ActiveLanguage = 'french' then Result := 'fr'
  else if ActiveLanguage = 'italian' then Result := 'it'
  else if ActiveLanguage = 'portuguese' then Result := 'pt'
  else if ActiveLanguage = 'russian' then Result := 'ru'
  else if ActiveLanguage = 'turkish' then Result := 'tr'
  else if ActiveLanguage = 'ukrainian' then Result := 'uk'
  else Result := 'en';
end;

procedure SeedLanguage;
var
  Dir, Path: String;
begin
  { Start RoDraw in the language Setup was run in -- but only on a first
    install. An existing settings.json is the user's own choice, and their
    language selection there must not be overwritten by a reinstall. }
  Dir := ExpandConstant('{userappdata}\RoDraw');
  Path := Dir + '\settings.json';
  if FileExists(Path) then
    Exit;
  if not DirExists(Dir) then
    if not CreateDir(Dir) then
      Exit;
  SaveStringToFile(Path, '{"general": {"language": "' + AppLanguageCode + '"}}', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SeedLanguage;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Settings: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Settings := ExpandConstant('{userappdata}\RoDraw');
    if DirExists(Settings) then
      if MsgBox('Also remove your RoDraw settings and keybinds?' + #13#10 + #13#10 +
                Settings, mbConfirmation, MB_YESNO) = IDYES then
        DelTree(Settings, True, True, True);
  end;
end;
