#define AppName "Telemetry Frame Mapper"
#define AppVersion "2.0.4"
#define AppExeName "Telemetry Frame Mapper.exe"

[Setup]
AppId={{962FDDB9-30EC-4AEE-B048-67273AFCD2E8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BrandonRobare
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist-installer
OutputBaseFilename=telemetry-frame-mapper-{#AppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\Telemetry Frame Mapper\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{localappdata}\Telemetry Frame Mapper"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{localappdata}\Telemetry Frame Mapper"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; WorkingDir: "{localappdata}\Telemetry Frame Mapper"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"