# Validation and QA

Run these commands from the project root after `setup.cmd`. Tests keep generated reports, screenshots and isolated profiles under `build/qa/`; documentation contains only reusable guides. Old test artifacts are retained in the pre-consolidation backup rather than shipped with the current project.

## Unit and behavior tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\.venv\Scripts\python.exe tests\check_instance.py
.\.venv\Scripts\python.exe tests\check_production_instance.py
```

The unit suite covers live-snapshot consistency, Optimize mode dispatch and worker lifetime, duplicate-run guards, result evidence, Auto scheduling, settings/startup rollback, localization, Insights history/gaps/partial readings, app identity and native-frame coordinates. Production-startup verification uses isolated application data and checks that the user's Start with Windows registration is unchanged.

## UI and Insights

```powershell
.\.venv\Scripts\python.exe tests\check_insights_visual_matrix.py
.\.venv\Scripts\python.exe tests\check_insights_visual.py --theme light --language th --exercise
.\.venv\Scripts\python.exe tests\check_insights_visual.py --theme dark --language th --live
.\.venv\Scripts\python.exe tests\check_insights_updates.py
.\.venv\Scripts\python.exe tests\check_native_frame.py
.\.venv\Scripts\python.exe tests\check_auto_tray.py
.\.venv\Scripts\python.exe tools\check_shutdown.py
.\.venv\Scripts\python.exe tools\check_shutdown.py --idle
```

The Insights matrix checks 36 combinations: Light/Dark, Thai/English, minimum/default/maximized windows, and effective scaling 100%/125%/150%. Reports include the measured window geometry and DPR; no Windows display settings are changed. Interaction checks cover details/search/focus restoration, selected history, growing/decreasing apps, latest-point visibility and continued monitoring while a test worker runs. Native-frame verification checks clicks and resize edges on monitors at positive and negative coordinates.

`build/qa/insights_visual/` contains per-case reports/screenshots, `matrix.json`, `ranking_updates.json` and `native_frame.json`. Images named `fixture_*` contain test-only readings; `live_*` use real Windows monitoring. Fixtures do not exist in the product UI.

## Overview, Auto and language regressions

```powershell
foreach ($theme in @('light','dark')) {
    foreach ($scale in @('1','1.25','1.5')) {
        .\.venv\Scripts\python.exe tests\check_auto_ui.py --theme $theme --scale $scale
        if ($LASTEXITCODE -ne 0) { throw 'Auto UI QA failed' }
        .\.venv\Scripts\python.exe tests\check_localization.py --theme $theme --scale $scale
        if ($LASTEXITCODE -ne 0) { throw 'Localization QA failed' }
        .\.venv\Scripts\python.exe tests\check_history_geometry.py --theme $theme --scale $scale
        if ($LASTEXITCODE -ne 0) { throw 'History geometry QA failed' }
        .\.venv\Scripts\python.exe tests\check_result_toast.py --theme $theme --scale $scale
        if ($LASTEXITCODE -ne 0) { throw 'Result popup QA failed' }
    }
}
```

These tools use live RAM and simulated Optimize results, clock and startup registration. They check long messages, expanded results, a stable chart, keyboard focus, live monitoring, compact popup lifetime and Thai/English retranslation. Reports are written directly under `build/qa/`; screenshots are in `build/qa/screenshots/`.

## Optional performance and real Optimize

```powershell
.\.venv\Scripts\python.exe tools\check_idle.py --collect-seconds 13 --screenshots
.\.venv\Scripts\python.exe tests\check_insights_performance.py --seconds-per-stage 240
```

The performance check records live baseline, hidden-window and Insights observations, then separately exercises a synthetic 24-hour database. Synthetic rows never enter the user's history. CPU/RAM measurements vary with the machine and workload.

`tests/check_insights_real_optimization.py` and `tools/render_qa.py --live-optimize` explicitly run real Optimize actions on Windows. They are optional manual checks; do not include them in routine unit/UI testing. Available RAM may rise, stay unchanged or fall. Store only the values actually measured.

## Packaged application and migration

```powershell
.\.venv\Scripts\python.exe tests\check_packaged_exe.py
```

The packaged check extracts the current portable ZIP into an isolated folder and launches the EXE without relying on source or the project virtual environment. See [PACKAGING.md](PACKAGING.md) for build and sharing instructions. Migration checks record source checksums, backup validation and preserved application data under `build/qa/`; the user's settings and history remain in `%LOCALAPPDATA%\ThrashingMitigatorRedesign`.
