# Put the project on GitHub and build the application

1. Create your repository. Put the CONTENTS of this source package at the repository
   root, including the `.github` directory. `app.py`, `requirements.txt` and `.github/`
   must be siblings. Do not upload the old virtual environment, personal bindings,
   logs, or game artwork. `.gitignore` excludes them in a normal Git checkout.
2. Open **Actions → Build Windows application → Run workflow**. Enable Actions if
   GitHub asks. The workflow installs build tools on GitHub's Windows runner, runs
   the tests, builds the app, and creates an installer and portable ZIP.
3. After a successful run, download the **ControllerStudio-Windows** artifact.
   GitHub wraps the files in an artifact ZIP: extract it to find the Setup EXE.
4. Test on Windows and in UO using VALIDATION.md. This initial package does not
   contain a precompiled or signed Windows EXE.
5. Create a tag such as `v4.0.0-beta.1` that matches controller_bridge.VERSION.
   A tag build creates a **draft prerelease** with the installer, portable ZIP and
   checksums. Review and publish it yourself. Nothing uploads to Discord automatically.
6. Share the GitHub release-page link in Discord. Players download the Setup EXE;
   they do not need the source ZIP or developer commands.

The workflow needs normal Actions permissions and contents-write permission only
for its draft-release job. Configure code signing separately before calling a
release signed. Signing credentials are not included, generated or requested here.

Dependencies are pinned directly; transitive dependencies are resolved during the
build. For a stable release, keep the tested artifact and build logs and consider
locking the full dependency graph. Review and choose the repository license before
publishing: this draft supplies MIT for the application source, with dependencies
under their own licenses.
