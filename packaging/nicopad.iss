; Instalador do nicoPad (Inno Setup 6). Uso: iscc /DAppVersion=1.2.3 packaging\nicopad.iss
;
; Instala por usuário (sem UAC), então o auto-atualizador roda este mesmo instalador em
; silêncio sem pedir permissão. O AppId é fixo: instalar por cima de QUALQUER versão
; anterior (a última ou a de várias releases atrás) só troca os arquivos.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3B6C1E-5A47-4D2B-9E0C-6D1A2F7B4C93}
AppName=nicoPad
AppVersion={#AppVersion}
AppPublisher=Matheus Goncalves
DefaultDirName={localappdata}\Programs\nicoPad
DefaultGroupName=nicoPad
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=nicopad.ico
UninstallDisplayIcon={app}\nicopad.exe
OutputDir=..\dist
OutputBaseFilename=nicopad-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\nicopad\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; Migração da versão portátil: se o instalador estiver na mesma pasta do antigo nicopad.json
; (é o que acontece quando a versão portátil se atualiza sozinha), a configuração vem junto.
Source: "{src}\nicopad.json"; DestDir: "{localappdata}\nicoPad"; Flags: external skipifsourcedoesntexist onlyifdoesntexist uninsneveruninstall
Source: "{src}\soundpad.json"; DestDir: "{localappdata}\nicoPad"; Flags: external skipifsourcedoesntexist onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\nicoPad"; Filename: "{app}\nicopad.exe"
Name: "{autodesktop}\nicoPad"; Filename: "{app}\nicopad.exe"; Tasks: desktopicon

; Sem skipifsilent: depois da atualização automática (silenciosa) o app reabre sozinho.
[Run]
Filename: "{app}\nicopad.exe"; Description: "{cm:LaunchProgram,nicoPad}"; Flags: nowait postinstall
