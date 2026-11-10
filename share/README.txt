MOIA KRAMNYTSIA — SHARING PACKAGE

HOW TO SHARE
1. Send this folder or the ZIP archive to another person.
2. Open index.html to view the download page.
3. Use the Windows or Mac download button after the first GitHub release is published.
   The Windows executable included here can also be run directly.
4. Each computer has separate local data. Backups must be shared separately.

HOST THE DOWNLOAD PAGE
The download buttons point to the latest release in the GitHub repository.
Do not upload your local database or personal backup files.

WINDOWS CODE SIGNING
This EXE is not signed with a trusted publisher certificate.
To reduce Windows SmartScreen warnings, the publisher must obtain a code-signing
certificate from a trusted certificate authority and sign the EXE with SignTool
from the Windows SDK. Do not include or share the private key or PFX file.
A self-signed certificate will not make the publisher trusted on other computers.

FILE CHECK
The SHA-256 checksum for the Windows executable is in SHA256SUMS.txt.
After downloading, verify it in Command Prompt:
  certutil -hashfile MoiaKramnytsia.exe SHA256

MACOS
The Mac DMG files are built automatically by GitHub Actions for Apple Silicon
and Intel Macs. The app is not signed or notarized with an Apple Developer ID,
so macOS may show a Gatekeeper warning on first launch. To open it, Control-click
the app in Finder, choose Open, then confirm the prompt.
