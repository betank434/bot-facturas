; Script de Inno Setup para Facturador Saint Enterprise
; Genera el instalador oficial de Windows con accesos directos y desinstalador completo.

#define MyAppName "Facturador Saint"
#define MyAppVersion "2.4"
#define MyAppPublisher "Saint Enterprise Automation"
#define MyAppExeName "FacturadorSaint.exe"

[Setup]
AppId={{D37B428A-9A2E-47C1-B73F-58DE81A90E21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
MinVersion=10.0.10240
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist_installer
OutputBaseFilename=Instalador_Facturador_Saint_v{#MyAppVersion}
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DisableProgramGroupPage=auto

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo a Facturador Saint en el Escritorio"; GroupDescription: "Accesos directos en el Escritorio:"
Name: "desktopicon_pdf"; Description: "Crear acceso directo a la Carpeta Facturas PDF en el Escritorio (para arrastrar facturas)"; GroupDescription: "Accesos directos en el Escritorio:"
Name: "desktopicon_json"; Description: "Crear acceso directo a la Carpeta Facturas JSON en el Escritorio"; GroupDescription: "Accesos directos en el Escritorio:"

[InstallDelete]
; Garantizar que las carpetas queden totalmente limpias sin archivos de prueba previos
Type: files; Name: "{app}\facturas_pdf\*.*"
Type: files; Name: "{app}\facturas_json\*.*"
Type: files; Name: "{app}\cache_capturas\*.*"

[Files]
; Todos los archivos del ejecutable y dependencias generados por PyInstaller (excluyendo cualquier archivo residual en pdf y json)
Source: "dist\FacturadorSaint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "facturas_pdf\*,facturas_json\*,cache_capturas\*"

[Dirs]
; Crear las carpetas de trabajo completamente vacias y con permisos completos
Name: "{app}\facturas_pdf"; Permissions: users-full
Name: "{app}\facturas_json"; Permissions: users-full
Name: "{app}\cache_capturas"; Permissions: users-full

[Icons]
; Acceso directo al programa en el Escritorio
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Acceso directo a la carpeta de PDFs en el Escritorio
Name: "{autodesktop}\Carpeta Facturas PDF"; Filename: "{app}\facturas_pdf"; WorkingDir: "{app}\facturas_pdf"; Tasks: desktopicon_pdf

; Acceso directo a la carpeta de JSONs en el Escritorio
Name: "{autodesktop}\Carpeta Facturas JSON"; Filename: "{app}\facturas_json"; WorkingDir: "{app}\facturas_json"; Tasks: desktopicon_json

; Accesos directos en el Menu Inicio
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Carpeta Facturas PDF"; Filename: "{app}\facturas_pdf"
Name: "{group}\Carpeta Facturas JSON"; Filename: "{app}\facturas_json"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
