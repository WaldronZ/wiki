# macOS Packaging Plan

## Choice

Use Tauri as the desktop shell and PyInstaller for the local FastAPI backend.

Rationale:
- Tauri keeps the app bundle smaller than Electron because it uses the system WebView.
- The current frontend is already a static Vite build, and the backend can serve `frontend/dist` from one local process.
- Python stays isolated inside a PyInstaller bundle while the UI remains ordinary React.

## Runtime Shape

1. `scripts/package_backend.sh` builds `frontend/dist`.
2. PyInstaller packages `backend/app/desktop_server.py` as `AutoPaperReaderServer`.
3. The desktop shell starts the server on `127.0.0.1:8765`.
4. The WebView opens `http://127.0.0.1:8765/`.

## Local Data Paths

When `AUTOPAPER_DESKTOP=1`, the backend stores mutable user data under:

```text
~/Library/Application Support/AutoPaperReader/
```

Default files:

```text
app.db
docs/
sources/
```

The app bundle should stay read-only; reports, source archives, cloned code, and SQLite data live in Application Support.

## Unsigned DMG

After the Tauri shell is added:

```bash
./scripts/package_backend.sh
npm --prefix desktop install
npm --prefix desktop run tauri build
```

Expected output is an unsigned `.dmg` under the Tauri target directory. This is suitable for local testing only.

## Signing And Notarization

Distribution outside the local machine needs:

1. Apple Developer ID Application certificate.
2. Hardened runtime enabled in Tauri config.
3. Code signing for the Tauri app bundle and bundled backend binary.
4. `xcrun notarytool submit` with Apple credentials.
5. `xcrun stapler staple` on the final app or DMG.

Signing should be added only after the app id, icon, bundle name, and entitlement needs are stable.
