#ifndef AppVersion
#define AppVersion "4.0.0-beta.1"
#endif
[Setup]
AppId={{D76C810A-2884-40AE-8C0C-B76DE8EBBC9E}
AppName=Mystic Llama Controller Studio
AppVersion={#AppVersion}
AppPublisher=MysticLlama
DefaultDirName={localappdata}\Programs\MysticLlama\ControllerStudio
DefaultGroupName=Mystic Llama Controller Studio
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=ControllerStudio-{#AppVersion}-Windows-Setup
SetupIconFile=..\assets\studio.ico
UninstallDisplayIcon={app}\ControllerStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\ControllerStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Controller Studio"; Filename: "{app}\ControllerStudio.exe"
Name: "{autodesktop}\Controller Studio"; Filename: "{app}\ControllerStudio.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ControllerStudio.exe"; Description: "Open Controller Studio"; Flags: nowait postinstall skipifsilent
