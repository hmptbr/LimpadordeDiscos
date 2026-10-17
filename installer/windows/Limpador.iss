; Instalador do Windows (Inno Setup 6). Gera dist\Limpador-Setup.exe
; Pré-requisito: dist\Limpador.exe já compilado com o PyInstaller.
[Setup]
AppName=Limpador
AppVersion=1.0
AppPublisher=Limpador
DefaultDirName={autopf}\Limpador
DefaultGroupName=Limpador
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=Limpador-Setup
SetupIconFile=..\..\icons\icon.ico
UninstallDisplayIcon={app}\Limpador.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\Limpador.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Limpador"; Filename: "{app}\Limpador.exe"
Name: "{autodesktop}\Limpador"; Filename: "{app}\Limpador.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Limpador.exe"; Description: "{cm:LaunchProgram,Limpador}"; Flags: nowait postinstall skipifsilent
