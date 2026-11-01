; Inno Setup script for Genshin Macro.
; Build: ISCC.exe /DAppVersion=1.3.1 installer\GenshinMacro.iss
; Expects the PyInstaller onedir output at dist\GenshinMacro\ (see build.bat).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Genshin Macro"
#define AppExe "GenshinMacro.exe"
#define AppPublisher "billy2204"
#define AppURL "https://github.com/billy2204/genshin-macro"

[Setup]
AppId={{7D2B1E7A-3C4F-4B7A-9C1E-5A2F9B3D1C04}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=GenshinMacroSetup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
DisableProgramGroupPage=yes
SetupIconFile=..\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\GenshinMacro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall shellexec

[UninstallDelete]
; user data lives in %LOCALAPPDATA%\GenshinMacro and is intentionally kept on uninstall
Type: filesandordirs; Name: "{app}\_internal"
