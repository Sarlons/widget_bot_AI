; Inno Setup installer for AI Token Widget.
; Build with packaging/build.ps1, which passes AppVersion, SourceDir, OutputDir
; and IconFile. The installer is per-user and does not require administrator.

#ifndef AppVersion
  #define AppVersion "0.5.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif
#ifndef IconFile
  #define IconFile "..\build\assets\icon.ico"
#endif

[Setup]
AppId={{0129F552-017B-4F62-BE56-8C56A0F60F47}
AppName=AI Token Widget
AppVersion={#AppVersion}
AppVerName=AI Token Widget {#AppVersion}
AppPublisher=AI Token Widget
DefaultDirName={localappdata}\Programs\AITokenWidget
DefaultGroupName=AI Token Widget
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=AI-Token-Widget-{#AppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\AITokenWidget.exe
UninstallDisplayName=AI Token Widget
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
InfoAfterFile={#SourceDir}\AITokenWidget\INSTALL_NOTES.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Start AI Token Widget with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\AITokenWidget\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI Token Widget"; Filename: "{app}\AITokenWidget.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall AI Token Widget"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AI Token Widget"; Filename: "{app}\AITokenWidget.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AITokenWidget"; ValueData: """{app}\AITokenWidget.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\AITokenWidget.exe"; Description: "{cm:LaunchProgram,AI Token Widget}"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopRunningWidget();
var
  ResultCode: Integer;
  WidgetExe: String;
begin
  WidgetExe := ExpandConstant('{app}\AITokenWidget.exe');
  if FileExists(WidgetExe) then
  begin
    { Ask the running widget to save state and exit. The --quit process
      returns once the instance has closed its single-instance socket. }
    Exec(WidgetExe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(300);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopRunningWidget();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopRunningWidget();
end;
