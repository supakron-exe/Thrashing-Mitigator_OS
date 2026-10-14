# Auto Optimize

Open `run.cmd`, `run_light.cmd` or `run_dark.cmd` from the project root, then select the Sync icon below Overview.

## Set up a rule

1. Choose Time interval, RAM threshold, or both. With both enabled, either condition can start a run.
2. Choose Standard, Deep or Maximum. Automatic runs default to Maximum, independently of the Manual mode selected on Overview.
3. Open Advanced settings to adjust cooldown and the duration of sustained high RAM.
4. Select Apply changes, then switch Auto on. Unsaved edits do not change a running schedule. Discard restores the saved values.

| Setting | Default | Range |
|---|---|---|
| Auto | Off | On / Off |
| Time trigger | Enabled, 3 minutes | 1–1,440 minutes |
| RAM trigger | Enabled, 75% | 50–95% |
| Mode | Maximum | Standard / Deep / Maximum |
| Sustained high RAM | 10 seconds | 2–120 seconds |
| Cooldown | 3 minutes | 1–60 minutes |
| Start with Windows | Off | Explicitly enable and Apply |

The time interval must be at least the cooldown. Turning Auto off prevents future runs; it does not interrupt a worker already running. Manual Optimize remains available after its existing three-second result hold.

## How scheduling works

The scheduler uses the same two-second RAM readings as Overview. RAM must remain at or above the threshold for the configured duration. After any completed Manual or Auto run, both the interval and cooldown restart from completion. If RAM stays high, the scheduler waits out cooldown, then measures sustained high RAM again. Simultaneous triggers start one worker.

Stale, failed or zero-total readings block automatic dispatch. After sleep or a sampling gap, the schedule starts fresh; missed jobs are not replayed. Changing themes or animations does not restart the schedule. Applying a new profile or enabling Auto starts a fresh interval. An enabled saved profile resumes after relaunch with a fresh interval and fresh RAM checks.

No measured RAM gain and partial/non-admin results are reported as outcomes. Worker exceptions pause Auto until it is enabled again. Auto pauses for the current session even if the settings file cannot be written. Invalid stored Auto fields are repaired with defaults and Auto starts off. Startup and settings errors appear inline; failed Apply retains the previous profile and restores the previous owned startup value when needed.

The Recent automatic runs list retains the latest 20 summaries in this session. Detailed results remain on Overview, labelled with Auto and its trigger. RAM gain is not guaranteed. No measurement is shown as a dash rather than invented zero gain.

## Tray and startup

Closing the window hides it in Tray, while polling and Auto continue. Click the Tray icon to reopen it. The Tray menu has Open, Pause/Resume Auto Optimize and Exit. Exit stops scheduling and waits for an active worker to finish. When the tray is unavailable, the window remains accessible and the Auto page offers Exit application.

Opening a launcher again activates the existing application. The Light/Dark launchers also change its theme. Only one application instance schedules automatic runs for this user.

Start with Windows is an optional per-user HKCU Run registration named `ThrashingMitigatorRedesign`, pointing to this folder's `pythonw.exe` and `main.py --background`. Enabling it does not enable Auto. Startup opens hidden in Tray and uses the saved Auto state. Disable it and Apply to remove only this application's value. It does not install a service or request elevation. Deep/Maximum system steps can be skipped without Administrator access, as with Manual Optimize.

Routine background successes do not raise the window or create Windows notifications. An exception that pauses Auto can create one native notification; Windows may suppress it. Opening the application shows the latest retained result through the existing compact popup. Startup diagnostics are written to `%LOCALAPPDATA%\ThrashingMitigatorRedesign\application.log`.

## Validation

See [VALIDATION.md](VALIDATION.md) for the current test commands. Auto UI reports are generated at `build/qa/auto_ui_qa_<theme>_<scale>.json`; Tray and production-startup reports are `build/qa/auto_tray_qa.json` and `build/qa/auto_production_qa.json`. Screenshots are generated under `build/qa/screenshots/`.

GUI checks use live RAM with simulated Optimize/time/startup in isolated profiles. The production-startup check launches real application processes with separate application data. Routine QA does not run real Optimize or change the user's startup registration.
