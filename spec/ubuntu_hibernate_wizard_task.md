# Ubuntu Hibernate Wizard — GTK4 GUI Implementation Task v0.42

## 1. Goal

Update **Ubuntu Hibernate Wizard** to use a native **GTK4 + libadwaita** interface that matches the approved GTK4 mockups and the original GTK-style icon set. The new GUI must be maintainable, accessible, responsive, and safe for a system-configuration tool.

The implementation must not be a static image copy of the mockups. The screenshots are design references only. Build real GTK widgets, real navigation pages, real status rows, and real progress/log output.

**Important v0.42 scope decision:** this implementation supports only existing valid swap partition/file targets. It must not create, resize, format, repartition, or enable new swap storage. Machines with no usable disk swap must be shown as blocked with a clear explanation and manual guidance. Swap-file creation/resizing is intentionally postponed to a later task.

## 2. Required framework decision

Use this stack:

| Area | Required choice |
|---|---|
| GUI toolkit | GTK4 |
| Style layer | libadwaita |
| Language | Python with PyGObject |
| UI layout | GTK Builder XML `.ui` files with Python controllers; do **not** use Blueprint for this implementation |
| Icons | Bundled original SVG icon set from this task package |
| Privileged changes | Small privileged helper using polkit/pkexec, not a root-run GUI |
| Main package format | Debian package first |

Do not switch to Qt, Electron, Tauri, webview, Tkinter, or custom-drawn canvas UI unless a later task explicitly changes the framework decision.

## 3. Design references included with this task

Use the included files as visual references:

```text
assets/screens/00_contact_sheet_all_menu_screens.png
assets/screens/01_introduction.png
assets/screens/02_system_check.png
assets/screens/03_configuration.png
assets/screens/04_planned_modifications.png
assets/screens/05_review_apply.png
assets/screens/06_finish.png
assets/screens/07_help.png
assets/screens/08_about.png
assets/icons/icons_preview_v038.png
assets/icons/gtk4_icon_preview_generated.png
assets/icons/svg/*.svg
assets/icons/icon_manifest.json
assets/icons/LICENSE_ASSETS.txt
```

The visual target is GTK4/libadwaita style: clean white/light surfaces, rounded cards, calm shadows, purple primary action color, green success states, blue informational process cards, and clear wizard navigation.

## 4. License and icon rules

Use only the supplied original SVG icons or newly created original icons drawn from simple geometric primitives.

Forbidden unless explicitly license-reviewed later:

- Ubuntu logo marks.
- Tux/Linux penguin artwork.
- GNOME symbolic icons copied from GNOME icon themes.
- FontAwesome, Material Icons, Bootstrap Icons, Heroicons, Remix Icons, or other third-party icon packs.
- Any trademarked distribution or desktop-environment logo.

The app may mention “Ubuntu” in text and package metadata if the project owner accepts the naming risk, but do not embed the Ubuntu logo in the artwork.

## 5. Required repository layout

Use a root-level Python package layout:

```text
ubuntu-hibernate-wizard/
├── ubuntu_hibernate_wizard/
│   ├── __init__.py
│   ├── main.py
│   ├── app.py
│   ├── window.py
│   ├── wizard_state.py
│   ├── ui/
│   │   ├── main_window.ui
│   │   ├── widgets.ui
│   │   └── resources.gresource.xml
│   ├── views/
│   │   ├── introduction_view.py
│   │   ├── system_check_view.py
│   │   ├── configuration_view.py
│   │   ├── planned_modifications_view.py
│   │   ├── review_apply_view.py
│   │   ├── finish_view.py
│   │   ├── help_view.py
│   │   └── about_view.py
│   ├── services/
│   │   ├── system_probe.py
│   │   ├── swap_detector.py
│   │   ├── swap_target_model.py
│   │   ├── hibernate_planner.py
│   │   ├── rollback_manager.py
│   │   ├── apply_runner.py
│   │   ├── command_runner.py
│   │   ├── log_exporter.py
│   │   └── reboot_notice.py
│   ├── assets/
│   │   └── icons/
│   └── css/
│       └── app.css
├── helper/
│   ├── ubuntu-hibernate-wizard-helper
│   └── io.github.ami3go.UbuntuHibernateWizard.policy
├── data/
│   ├── io.github.ami3go.UbuntuHibernateWizard.desktop
│   ├── io.github.ami3go.UbuntuHibernateWizard.metainfo.xml
│   └── icons/
├── tests/
│   └── fixtures/
│       └── system_profiles/
├── docs/
├── pyproject.toml
├── README.md
└── LICENSE
```

Keep the GUI package directly in the repository root. Do not create a `src/` folder for this project unless a later project-wide decision changes the layout.

## 6. Application architecture

Separate the project into these layers:

### 6.1 GUI layer

Responsibilities:

- Render pages.
- Navigate between wizard steps.
- Display status, warnings, and progress.
- Collect user choices.
- Never directly edit system files.
- Never run `sudo` commands from random button handlers.

### 6.2 Planner layer

Responsibilities:

- Convert detected system facts and user choices into a modification plan.
- Produce human-readable planned modifications.
- Produce machine-readable actions for the privileged helper.
- Validate that the plan is still safe before apply.

### 6.3 Privileged helper layer

Responsibilities:

- Perform the minimum required privileged actions.
- Create rollback data before modification.
- Write configuration files safely using atomic writes.
- Run `update-initramfs` and `update-grub` when required.
- Return structured status events to the GUI.

The GUI process must stay unprivileged. Escalation must happen only for specific helper actions.

## 7. Navigation model

Implement the left menu as a persistent wizard sidebar. Each item opens a page in the main content area.

Required menu items:

1. Introduction
2. System Check
3. Configuration
4. Planned Modifications
5. Review & Apply
6. Finish
7. Help
8. About

The first six are main wizard flow pages. Help and About are secondary pages accessible from the bottom of the sidebar.

### 7.1 Sidebar state behavior

Each wizard item must show one of these states:

| State | Meaning |
|---|---|
| Pending | Step not completed yet |
| Active | Current visible page |
| Passed | Step completed successfully |
| Warning | Step completed with non-blocking warning |
| Error | Step blocked by problem |

Use the supplied status icons: `success-check`, `status-pending`, `warning`, and `error`.

### 7.2 Navigation restrictions

- User may go back to previous pages at any time before apply.
- User may not go to Review & Apply until required checks are complete.
- User may not apply when a blocking system check exists.
- After successful apply, Finish page becomes available.
- Help and About remain available at all times.

## 8. Page requirements

### 8.1 Introduction page

Reference: `assets/screens/01_introduction.png`

Purpose: explain what the wizard does and what will happen.

Required content:

- App title and short explanation.
- “What this wizard can do” card.
- “Before you continue” safety card.
- Small process preview: check system → choose target → review changes → apply → reboot manually.
- Continue button.

Important wording:

- The app helps configure hibernation.
- The app will show every planned system change before applying.
- The user should save work before testing hibernation.
- The app does not force reboot automatically.

### 8.2 System Check page

Reference: `assets/screens/02_system_check.png`

Purpose: inspect the machine and identify whether hibernation can be configured safely.

Required checks:

- Distribution and version.
- Kernel version.
- Secure Boot state if detectable.
- Lockdown mode if detectable.
- Active swap devices and files.
- Swap size versus RAM size.
- Available hibernation target candidates.
- Filesystem type for swap file support.
- Bootloader/initramfs tooling availability.
- Timeshift availability for rollback snapshot.
- Current `/etc/fstab` and resume configuration status.

Required UI:

- Top summary card: Ready / Warnings / Blocked.
- Cards for major check groups.
- Per-check status rows with icon, label, result, and detail text.
- “Refresh checks” button.
- “Export system report” button.

Blocking cases must be clear and actionable. Do not hide command failures behind generic text.

### 8.3 Configuration page

Reference: `assets/screens/03_configuration.png`

Purpose: let the user select the hibernation configuration strategy.

Required sections:

1. **Swap target selection**
   - Existing swap partition.
   - Existing swap file.
   - “Automatic recommended target” option.
   - A disabled informational row may say “Create or resize swap file — planned for a later release”, but v0.42 must not implement swap-file creation or resizing.

2. **Rollback protection**
   - Timeshift snapshot option when Timeshift is installed.
   - Manual backup fallback when Timeshift is not available.
   - Clearly show what rollback will and will not protect.

3. **Boot configuration**
   - Resume device/UUID summary.
   - Swap file resume offset summary when relevant.
   - GRUB/initramfs update plan summary.

4. **Advanced details**
   - Show exact target device/file.
   - Show UUID/PARTUUID.
   - Show size.
   - Show risk level.

Required behavior:

- Update the planned modifications whenever configuration changes.
- Warn when selected swap is smaller than RAM.
- Warn when swap file offset cannot be detected reliably.
- Do not allow apply when target is invalid.

### 8.4 Planned Modifications page

Reference: `assets/screens/04_planned_modifications.png`

Purpose: show the complete plan before apply.

Required left card:

- Step 1: Detect swap target.
- Step 2: Create rollback snapshot or fallback backup.
- Step 3: Write configuration files.
- Step 4: Regenerate boot artifacts.
- Note card with selected target details.

Required right card:

- “Apply Phase” process diagram:
  1. Detect swap target.
  2. Create rollback snapshot.
  3. Write config files.
  4. Regenerate boot artifacts.

- “Runtime” hibernation/resume diagram:
  1. User selects hibernate.
  2. Services stop safely.
  3. RAM image saved to swap.
  4. Power off.
  5. Bootloader starts.
  6. Initramfs resumes.
  7. Kernel restores RAM.
  8. Desktop returns.

The diagrams must use real GTK layout and icons, not a pasted PNG. SVG icons may be displayed with `Gtk.Image`.

### 8.5 Review & Apply page

Reference: `assets/screens/05_review_apply.png`

Purpose: final confirmation and controlled execution.

Required content:

- Final summary of target and planned files.
- Risk and rollback summary.
- Checkbox: “I understand these changes modify boot/hibernate configuration.”
- Apply button disabled until the checkbox is selected and plan is valid.
- Progress list showing each operation.
- Expandable log output.
- Cancel button before privileged execution begins.
- No cancel once critical writes are in progress unless helper supports safe cancellation.

Required behavior:

- Re-run a quick validation immediately before apply.
- Ask for polkit authorization only when the user presses Apply.
- Stream progress from helper to GUI.
- Save apply log to a predictable support file.
- On failure, show exact failed step and rollback options.

Important UI rule:

- Do not add a “Reboot now” button. Prior design decision: reboot should be communicated as text only. The user should reboot manually after reviewing the finish message.

### 8.6 Finish page

Reference: `assets/screens/06_finish.png`

Purpose: communicate the result and next steps.

Required success state:

- “Configuration applied” success card.
- Manual reboot instruction.
- “After reboot, test hibernation” instructions.
- Show selected hibernation target.
- Show apply log path.
- Button to copy support summary.
- Button to export diagnostic bundle.

Required failure state:

- Failure card with failed step.
- Suggested correction.
- Rollback availability.
- Button to open Help page.
- Button to export diagnostic bundle.

Again: no automatic reboot and no reboot button.

### 8.7 Help page

Reference: `assets/screens/07_help.png`

Purpose: support troubleshooting without leaving the app.

Required sections:

- Common problems.
- Swap partition versus swap file explanation.
- Secure Boot / lockdown warning explanation.
- Where configuration files are written.
- How to rollback.
- How to collect support logs.
- Manual commands shown read-only.

Required actions:

- Export diagnostic bundle.
- Copy system summary.
- Open project documentation URL if available.

The Help page must not perform dangerous modifications.

### 8.8 About page

Reference: `assets/screens/08_about.png`

Purpose: show product identity, version, license, and asset provenance.

Required content:

- App name.
- Version.
- Short description.
- Project/repository link if configured.
- License.
- Icon provenance: original project icons, no third-party icon packs.
- System information summary.

Use `Adw.AboutWindow` where practical, or a custom page matching the screenshots.

## 9. GTK widget mapping

Use these widget patterns:

| UI element | Recommended GTK/libadwaita component |
|---|---|
| App window | `Adw.ApplicationWindow` |
| Header | `Adw.HeaderBar` |
| Main two-pane layout | `Adw.NavigationSplitView` or `Gtk.Paned` + custom sidebar |
| Page stack | `Adw.NavigationView` or `Gtk.Stack` |
| Sidebar rows | `Gtk.ListBoxRow` with custom content |
| Rounded cards | `Gtk.Box` with CSS class `.card` |
| Settings rows | `Adw.PreferencesGroup`, `Adw.ActionRow`, `Adw.ComboRow`, `Adw.SwitchRow` |
| Buttons | `Gtk.Button` with libadwaita suggested/destructive styles |
| Status banners | `Adw.Banner` |
| Toasts | `Adw.ToastOverlay` |
| Confirmation | `Adw.AlertDialog` |
| Logs | `Gtk.TextView` inside `Gtk.ScrolledWindow` |
| Progress | `Gtk.ProgressBar` and status rows |
| Icons | `Gtk.Image` loading app resource SVGs |

## 10. Styling requirements

Create a small app stylesheet, not a large custom theme.

Required CSS classes:

```css
.card
.sidebar-step
.sidebar-step-active
.status-success
.status-warning
.status-error
.status-info
.diagram-card
.diagram-node
.muted-text
.monospace-detail
```

Style goals:

- Respect system light/dark theme where possible.
- Use libadwaita defaults first.
- Use purple only as the product accent and primary action color.
- Use green only for success and safe runtime states.
- Use blue for informational/apply-process cards.
- Use orange/yellow for warnings.
- Use red only for blocked/error/destructive states.
- Do not hard-code huge font sizes that break scaling.
- Do not rely on the Ubuntu wallpaper being present.

## 11. Icon integration task

### 11.1 Required icon import

Copy all supplied SVGs from:

```text
assets/icons/svg/*.svg
```

into the app resources, for example:

```text
ubuntu_hibernate_wizard/assets/icons/*.svg
```

Then compile them into a GResource bundle or load them from package data.

### 11.2 Required icon name mapping

Use these semantic names in code:

| Semantic usage | Icon name |
|---|---|
| Application icon | `app-icon` |
| Introduction step | `introduction` |
| System check step | `system-check` |
| Configuration step | `configuration` |
| Planned modifications step | `planned-modifications` |
| Review/apply step | `review-apply` |
| Finish step | `finish` |
| Help | `help` |
| About | `about` |
| Detect swap target | `swap-target-search` |
| Existing swap partition | `partition` |
| Existing swap file | `swap-file` |
| Rollback snapshot | `rollback-snapshot` |
| Config file | `config-file` |
| Boot artifacts | `boot-gears` |
| Apply phase | `apply-phase` |
| Runtime cycle | `runtime-cycle` |
| Hibernate action | `hibernate-power` |
| Services stop | `services-stop` |
| Save RAM to swap | `ram-save` |
| Power off | `power-off` |
| Bootloader | `bootloader-terminal` |
| Initramfs | `initramfs-box` |
| Restore RAM | `kernel-restore-ram` |
| Desktop return | `desktop-return` |
| Save plan | `save-plan` |
| Back | `back` |
| Next | `next` |
| Success | `success-check` |
| Pending | `status-pending` |
| Warning | `warning` |
| Error | `error` |
| Info note | `info-note` |

Do not reference icon files by hard-coded absolute paths. Use package resources.

## 12. State model

Create a central `WizardState` model. It must be serializable for diagnostics.

Minimum fields:

```text
current_page
completed_pages
system_check_status
blocking_issues
warnings
ram_size_bytes
swap_candidates
selected_swap_target
rollback_mode
planned_actions
apply_status
apply_log_path
last_error
reboot_required
```

All pages must read and update this state through clear methods. Do not duplicate independent page-specific state that can go stale.

## 13. Swap target display requirements

Every swap candidate must have a model containing:

```text
kind: partition | file | zram | unknown
path
uuid
partuuid
filesystem
mount_source
size_bytes
used_bytes
priority
active
supports_hibernation
requires_resume_offset
resume_offset
risk_level
warnings
blocking_reason
```

Do not show zram as a valid hibernation target. It may be displayed as detected swap, but must be marked unsuitable for hibernation.

## 14. Apply flow requirements

The apply flow must execute in this order:

1. Re-check selected swap target still exists.
2. Verify no blocking issue appeared since planning.
3. Create rollback snapshot or fallback backup.
4. Write/update hibernation configuration files using atomic writes.
5. Regenerate initramfs.
6. Regenerate GRUB configuration if needed.
7. Save apply log and final plan snapshot.
8. Set `reboot_required = true`.
9. Navigate to Finish page.

Each step must emit structured progress:

```text
step_id
step_title
status: pending | running | success | warning | error
message
log_excerpt
```

## 15. Files and command safety

Required safety rules:

- Never overwrite config files without backup.
- Use atomic writes: write temp file, fsync if practical, rename.
- Preserve unrelated user content in files.
- Mark wizard-managed sections clearly.
- Validate generated files before replacing originals when possible.
- Capture stdout/stderr from every command.
- Timeout long commands and report timeout clearly.
- Never run shell commands with unsanitized string concatenation.
- Prefer argument arrays over shell strings.

## 16. Rollback requirements

Implement rollback preparation before writing changes:

- Prefer Timeshift snapshot if available and accepted by user.
- If Timeshift is unavailable, back up every file that the helper may change.
- Store backup metadata with timestamp, app version, target path, original checksum, and backup path.
- Show rollback availability in Planned Modifications, Review & Apply, and Finish.
- Do not claim full-system rollback exists when only file backups exist.

## 17. Supportability requirements

Add a diagnostic export action that creates a ZIP containing:

- App version.
- OS and kernel summary.
- Swap detection JSON.
- Selected plan JSON.
- Apply log.
- Relevant command output.
- Redacted config snippets.
- Rollback metadata.

Do not include private user files or excessive system data.

## 18. Accessibility requirements

- Every interactive element must have a visible label or accessible name.
- Keyboard navigation must work through the whole wizard.
- Do not use color alone to communicate status.
- Status icons must have text labels.
- Use sufficient contrast in light and dark modes.
- Text must not be baked into images.

## 19. Testing requirements

Add tests for:

### 19.1 Pure logic tests

- Swap candidate parsing.
- RAM versus swap sizing decisions.
- zram exclusion.
- swap file offset handling.
- plan generation.
- rollback mode selection.
- blocking/warning classification.

### 19.2 GUI smoke tests

- App starts without root.
- All pages can be opened.
- Sidebar status changes when model state changes.
- Review & Apply button stays disabled when plan is invalid.
- Apply button becomes enabled only after confirmation checkbox and valid plan.
- Finish page shows manual reboot instruction, not a reboot button.

### 19.3 Helper tests

- Dry-run mode produces expected action list.
- Atomic write path works in temporary directory.
- Backup metadata is written.
- Command failure returns structured error.
- Long command timeout returns structured error.

## 20. Packaging requirements

Debian packaging must include:

- Python package.
- GTK resources.
- SVG icons.
- `.desktop` file.
- AppStream metadata.
- Polkit policy file.
- Privileged helper installed in a controlled path.
- Correct dependency list for Python, GTK4, libadwaita, PyGObject, and helper runtime.

Do not require the user to launch the GUI with `sudo`.

## 21. Acceptance criteria

The task is complete when:

1. The app opens as a GTK4/libadwaita window.
2. The UI visually matches the supplied menu screenshots at a functional level.
3. All eight menu pages exist.
4. Sidebar navigation and status indicators work.
5. The supplied SVG icon set is used through package resources.
6. No forbidden third-party/trademark icon artwork is introduced.
7. System Check displays real detected system information.
8. Configuration page updates the plan model.
9. Planned Modifications page shows the real plan and both process diagrams.
10. Review & Apply uses a safe confirmation flow and does not run the whole GUI as root.
11. Finish page gives text-only manual reboot instructions and has no Reboot Now button.
12. Help and About pages exist and contain useful support information.
13. Diagnostic export works.
14. Unit tests for planner logic pass.
15. GUI smoke tests pass.
16. Debian package can be built and installed on a clean Ubuntu test VM.

## 22. Non-goals for this task

Do not implement these unless a later task requests them:

- Automatic reboot button.
- Automatic GNOME extension installation.
- Cross-platform Windows/macOS GUI.
- Electron/web UI rewrite.
- Remote management dashboard.
- Animated splash screen.
- Distribution logos or mascot artwork.

## 23. AI-agent implementation warnings

When using this task with an AI coding agent, explicitly check for these mistakes:

- Replacing GTK widgets with a static screenshot image.
- Running the whole GUI as root.
- Hard-coding `/dev/nvme0n1p3` from the mockup.
- Assuming every machine uses GRUB.
- Treating zram as a valid hibernate target.
- Losing user changes in config files.
- Writing config before rollback backup.
- Adding a Reboot Now button despite the requirement not to.
- Copying icons from GNOME, Ubuntu, FontAwesome, Material Icons, or web sources.
- Making GUI state independent from planner state.
- Blocking the UI thread during long commands.
- Hiding command failures behind generic error messages.

## 24. Suggested implementation phases

### Phase 1 — UI skeleton

- Create GTK4/libadwaita app shell.
- Add sidebar and page stack.
- Add all eight placeholder pages.
- Load bundled SVG icons.
- Add app CSS.

### Phase 2 — Real page layouts

- Implement each page layout matching screenshots.
- Implement process diagrams as GTK widgets.
- Add status rows and cards.
- Add responsive behavior.

### Phase 3 — State and planner integration

- Add `WizardState`.
- Connect system checks to UI.
- Connect configuration choices to plan generation.
- Update sidebar states from model.

### Phase 4 — Privileged helper integration

- Add polkit/pkexec helper with the v0.42 JSON protocol.
- Add dry-run apply first.
- Add real apply execution with progress events only after helper and planner tests pass.
- Add failure handling and rollback metadata.

### Phase 5 — Support and packaging

- Add diagnostic export.
- Add About metadata.
- Add Debian packaging.
- Add tests and CI checks.
- Update README and GitHub Pages screenshots.


## 25. Implementation readiness addendum v0.42

This section supersedes any earlier ambiguous wording in this task. It exists to make the task safe to hand directly to an implementation agent.

### 25.1 Fixed application identity

Use these names consistently in source, desktop integration, AppStream metadata, icon resources, polkit policy, logs, and packaging:

| Item | Required value |
|---|---|
| Application ID | `io.github.ami3go.UbuntuHibernateWizard` |
| Executable | `ubuntu-hibernate-wizard` |
| Python package | `ubuntu_hibernate_wizard` |
| Helper executable | `ubuntu-hibernate-wizard-helper` |
| Helper install path | `/usr/libexec/ubuntu-hibernate-wizard/ubuntu-hibernate-wizard-helper` |
| Desktop file | `io.github.ami3go.UbuntuHibernateWizard.desktop` |
| AppStream file | `io.github.ami3go.UbuntuHibernateWizard.metainfo.xml` |
| Polkit action prefix | `io.github.ami3go.UbuntuHibernateWizard` |
| State directory | `/var/lib/ubuntu-hibernate-wizard/` |
| Log directory | `/var/log/ubuntu-hibernate-wizard/` |
| User cache/runtime directory | `$XDG_RUNTIME_DIR/ubuntu-hibernate-wizard/` |

If the project owner later changes the GitHub owner or application ID, update all of these locations in one commit.

### 25.2 Final build-system decision

Use **GTK Builder XML** for this implementation. Do not use Blueprint in v0.42.

Required build/resource rules:

- Keep UI files as `.ui` GTK Builder XML files under `ubuntu_hibernate_wizard/ui/`.
- Keep custom CSS under `ubuntu_hibernate_wizard/css/app.css`.
- Keep SVG icons under `ubuntu_hibernate_wizard/assets/icons/`.
- Compile icons, UI files, and CSS into one GResource bundle using `glib-compile-resources`.
- Validate UI files in CI using `gtk4-builder-tool validate` where available.
- Use `pyproject.toml` with setuptools or hatchling for Python packaging.
- Debian packaging must call the resource build step before installation.

### 25.3 Mandatory runtime modes

The implementation must support three runtime modes:

| Mode | CLI flag | Root required | Purpose |
|---|---|---:|---|
| Real system mode | default | No for GUI, yes only through helper during apply | Normal use |
| Dry-run mode | `--dry-run` | No | Generate and execute a simulated plan without modifying system files |
| Fake-system mode | `--fake-system tests/fixtures/system_profiles/<name>.json` | No | Render/test UI and planner from deterministic system fixtures |

Rules:

- `--dry-run` must never write to `/etc`, `/boot`, `/var/lib`, or `/var/log`.
- `--fake-system` must not execute real probing commands.
- `--fake-system` may be combined with `--dry-run` and must be used for screenshot tests.
- The Review & Apply page must clearly show a “Dry run” badge when dry-run mode is active.
- The helper must have its own `--dry-run` option and must return the same event schema as real apply.

Minimum fixture files to add:

```text
tests/fixtures/system_profiles/
├── no_swap.json
├── zram_only.json
├── valid_swap_partition.json
├── small_swap_partition.json
├── valid_ext4_swap_file.json
├── unsupported_swap_file_fs.json
├── partition_and_swap_file.json
├── encrypted_random_swap.json
└── secure_boot_warning.json
```

### 25.4 Exact probe data sources

The System Check service must use explicit probes and preserve raw command output in diagnostics.

Required probes:

| Information | Preferred source | Fallback |
|---|---|---|
| RAM size | `/proc/meminfo` `MemTotal` | `free --bytes` |
| Active swap | `swapon --show --bytes --noheadings --output NAME,TYPE,SIZE,USED,PRIO` | `/proc/swaps` |
| Block devices | `lsblk --json --bytes --output NAME,KNAME,PATH,TYPE,FSTYPE,SIZE,UUID,PARTUUID,MOUNTPOINTS` | `blkid -o export` |
| Filesystem for swap file | `findmnt -T <swapfile> --json --output SOURCE,FSTYPE,UUID,TARGET,OPTIONS` | `stat` + `lsblk` lookup |
| Swap file offset | supported resolver per filesystem | blocked if resolver fails |
| Kernel | `uname -r` | Python `platform.release()` |
| Secure Boot | `mokutil --sb-state` if installed | mark unknown, non-blocking |
| Lockdown | `/sys/kernel/security/lockdown` if readable | mark unknown, non-blocking |
| GRUB tooling | `command -v update-grub` and `command -v grub-mkconfig` | mark unavailable |
| Initramfs tooling | `command -v update-initramfs` | mark unavailable |
| Timeshift | `command -v timeshift` | fallback to file backup |

Do not parse localized human output when a machine-readable option exists.

### 25.5 Swap target decision table

The planner must classify every detected swap target using this table. Use these result classes:

- `recommended`: best default target.
- `valid_option`: usable but not the first recommendation.
- `warning_option`: visible but not selected automatically.
- `blocked`: cannot be used by the wizard.

| Scenario | Classification | Required behavior |
|---|---|---|
| Active plain swap partition, UUID/PARTUUID available, size >= RAM | `recommended` | Select automatically unless a better explicit user choice exists. |
| Active plain swap partition, size < RAM | `warning_option` by display, apply blocked by default | Explain that safe hibernation normally needs swap at least as large as RAM. Do not auto-select. |
| Inactive swap partition listed in fstab, valid UUID, size >= RAM | `valid_option` | Offer only if enabling it is in current project scope. Otherwise show as detected but not selectable. |
| Swap partition encrypted with stable LUKS mapping and already available in initramfs | `warning_option` | Require explicit user selection and show encryption/resume warning. |
| Swap partition encrypted with random key or unknown crypttab behavior | `blocked` | Explain that random-key encrypted swap cannot resume after reboot. |
| Active ext4 swap file, non-sparse, offset resolver succeeds, backing device UUID available, size >= RAM | `recommended` only if no valid partition exists | Show resume offset and backing filesystem UUID. |
| Active swap file on supported filesystem, size < RAM | `warning_option` by display, apply blocked by default | Show size warning and do not auto-select. |
| Swap file offset cannot be detected reliably | `blocked` | Do not allow apply. |
| Swap file is sparse, has holes, or is on unstable/unsupported storage | `blocked` | Explain that the resume location is not reliable. |
| Btrfs swap file | `valid_option` only when `btrfs inspect-internal map-swapfile -r <file>` succeeds | Otherwise block. |
| Swap file on unknown filesystem | `blocked` | Explain unsupported filesystem. |
| zram only | `blocked` | Display zram as detected swap but not a hibernation target. |
| zram plus valid disk swap | Disk swap classified normally, zram `blocked` | Ignore zram for recommendation. |
| Valid partition and valid swap file | Best valid partition `recommended`, file `valid_option` | Let user override to file if valid. |
| No swap | `blocked` unless create-swap-file feature is in scope | Offer create swap file only if the implementation includes it. |
| Multiple valid partitions | Largest active valid partition `recommended` | Display all candidates with size and UUID. |
| Swap on removable/USB media | `blocked` by default | Avoid resume target that may disappear before resume. |

Default policy: do not allow apply when the selected target is smaller than RAM. A later task may add an advanced override, but v0.42 must not.

### 25.6 Supported swap-file offset resolvers

Implement swap-file support only when one of these resolvers succeeds:

| Filesystem | Resolver | Notes |
|---|---|---|
| ext4 | `filefrag -v <swapfile>` and parse first physical extent | Reject if parse fails or file appears sparse. |
| btrfs | `btrfs inspect-internal map-swapfile -r <swapfile>` | Use only when command exists and returns a numeric resume offset. |

Other filesystems must be blocked until explicitly supported by a later task.

### 25.7 Exact privileged helper protocol

The GTK process must never run privileged commands directly. It must call the helper only through a narrow protocol.

Helper invocation model:

```text
pkexec /usr/libexec/ubuntu-hibernate-wizard/ubuntu-hibernate-wizard-helper --action apply-plan --stdin-json
```

The GUI sends one JSON request on stdin. The helper returns newline-delimited JSON events on stdout. Stderr is reserved for fatal helper startup errors only.

Required helper actions:

| Action | Privileged? | Description |
|---|---:|---|
| `validate-plan` | yes via helper | Re-check target and planned files before apply. |
| `apply-plan` | yes via helper | Execute the approved plan. |
| `rollback-files` | yes via helper | Restore files from a wizard backup set. |
| `helper-version` | no escalation if callable directly, otherwise yes | Return helper version and protocol version. |

Request schema:

```json
{
  "protocol_version": 1,
  "request_id": "2026-07-06T10-30-00Z-abcdef",
  "action": "apply-plan",
  "dry_run": false,
  "app_version": "0.42.0",
  "selected_target": {
    "kind": "partition",
    "path": "/dev/nvme0n1p3",
    "uuid": "3f2c-example-7b9e",
    "partuuid": null,
    "filesystem": null,
    "size_bytes": 17179869184,
    "resume_offset": null
  },
  "rollback": {
    "mode": "timeshift_or_file_backup",
    "timeshift_allowed": true
  },
  "planned_files": [
    "/etc/initramfs-tools/conf.d/resume",
    "/etc/default/grub.d/hibernate-wizard.cfg"
  ],
  "steps": [
    "validate_target",
    "create_rollback",
    "write_resume_config",
    "write_grub_config",
    "update_initramfs",
    "update_grub"
  ]
}
```

Response event schema:

```json
{
  "protocol_version": 1,
  "request_id": "2026-07-06T10-30-00Z-abcdef",
  "event": "step",
  "step_id": "update_initramfs",
  "status": "running",
  "message": "Running update-initramfs -u",
  "progress": 0.75,
  "stdout_tail": "",
  "stderr_tail": "",
  "timestamp": "2026-07-06T10:30:12Z"
}
```

Required event types:

| Event | Meaning |
|---|---|
| `hello` | Helper version and protocol version. |
| `plan-valid` | Plan validation succeeded. |
| `step` | A step changed state. |
| `command` | A command started or finished. |
| `warning` | Non-fatal issue occurred. |
| `error` | Fatal failure occurred. |
| `complete` | Apply completed successfully. |
| `rollback-ready` | Backup/rollback metadata was created. |

Required step statuses:

```text
pending | running | success | warning | error | skipped
```

Helper safety rules:

- Validate request schema before doing any privileged work.
- Reject unknown actions, unknown step IDs, unknown target kinds, and unexpected file paths.
- Never execute command strings through `shell=True`.
- Use fixed command allowlists and argument arrays.
- Redact private data before emitting diagnostics.
- Return structured failure before exiting non-zero when possible.

### 25.8 Exact managed files and forbidden actions

Allowed managed files:

```text
/etc/initramfs-tools/conf.d/resume
/etc/default/grub.d/hibernate-wizard.cfg
/etc/fstab                         # only for wizard-created swap file, inside managed section
/var/lib/ubuntu-hibernate-wizard/backups/*
/var/lib/ubuntu-hibernate-wizard/plans/*
/var/log/ubuntu-hibernate-wizard/*
```

Allowed commands through helper:

```text
update-initramfs -u
update-grub
grub-mkconfig -o /boot/grub/grub.cfg        # fallback only when update-grub is unavailable and path is verified
timeshift --create --comments <comment>     # only when user selected Timeshift rollback
systemctl daemon-reload                     # only if fstab/systemd swap unit change requires it
```

Forbidden actions:

- Running the whole GUI as root.
- Blindly rewriting `/etc/default/grub`.
- Removing or reordering unrelated GRUB options.
- Formatting, repartitioning, shrinking, or moving partitions.
- Editing bootloader files outside the allowed managed-file list.
- Changing Secure Boot settings.
- Creating or modifying encrypted volumes.
- Adding a reboot button or calling `reboot`/`systemctl reboot`.
- Using network access during apply.
- Downloading icon packs or external assets during build.

File-writing rules:

- Every modified file must be backed up before the first write.
- Backups must include SHA-256 hash, file mode, owner, group, original path, backup path, and timestamp.
- Writes must use temporary files in the same directory followed by `fsync` where practical and atomic rename.
- Managed sections must use clear markers, for example:

```text
# BEGIN UBUNTU HIBERNATE WIZARD
# Managed by Ubuntu Hibernate Wizard. Manual edits inside this block may be overwritten.
...
# END UBUNTU HIBERNATE WIZARD
```

### 25.9 Generated configuration policy

For a swap partition target, generated configuration must include:

- initramfs resume file pointing to the stable resume identifier, preferably `UUID=<uuid>`.
- GRUB kernel command-line fragment with `resume=UUID=<uuid>` or another explicitly justified stable identifier.

For a swap file target, generated configuration must include:

- backing block-device UUID or other stable identifier required for resume.
- `resume_offset=<offset>` when the selected distribution/initramfs path requires it.
- a visible warning when the filesystem or offset method is not supported.

The exact generated syntax must be covered by unit tests using golden expected files. Do not generate config syntax only from UI text.

### 25.10 Navigation state transition table

Use this exact flow for the first implementation:

| Current page | Required condition for Next | Next page |
|---|---|---|
| Introduction | User presses Continue | System Check |
| System Check | Checks completed and no blocking issue | Configuration |
| Configuration | Valid target selected | Planned Modifications |
| Planned Modifications | Plan generated and valid | Review & Apply |
| Review & Apply | Apply completed successfully | Finish |
| Finish | none | none |

Back behavior:

- Back is enabled on System Check, Configuration, Planned Modifications, Review & Apply before apply starts, Help, and About.
- Back is disabled while helper apply is running.
- After apply success, Configuration and Review & Apply become read-only views of the applied plan.

### 25.11 Required Debian/runtime dependencies

Minimum runtime dependencies to declare in Debian packaging:

```text
python3
python3-gi
gir1.2-gtk-4.0
gir1.2-adw-1
initramfs-tools
grub-common
util-linux
coreutils
findutils
mount
polkitd | policykit-1
```

Recommended dependencies:

```text
mokutil
btrfs-progs
```

Suggested dependency:

```text
timeshift
```

Build/test dependencies:

```text
python3-pytest
python3-build
glib2.0-bin
desktop-file-utils
appstream
```

The package must check for command availability at runtime and show actionable warnings instead of crashing when optional tools are absent.

### 25.12 Expanded tests required before real apply is enabled

Real apply must be behind tests. Do not enable a non-dry-run Apply button until these pass:

- Planner tests for every fixture in `tests/fixtures/system_profiles/`.
- Golden-file tests for generated `/etc/initramfs-tools/conf.d/resume` content.
- Golden-file tests for generated `/etc/default/grub.d/hibernate-wizard.cfg` content.
- Helper schema validation tests with valid and invalid JSON.
- Helper path allowlist tests proving unexpected paths are rejected.
- Dry-run apply test proving no `/etc`, `/boot`, `/var/lib`, or `/var/log` writes occur.
- Fake-system UI test proving every page can render from fixture data.
- Failure test where `update-initramfs` returns non-zero and GUI shows exact failed step.

### 25.13 Implementation phase gates

Use these gates to avoid unsafe partial implementation:

| Gate | May be merged when |
|---|---|
| Gate A: GUI shell | App launches unprivileged, pages render, icons load. |
| Gate B: planner | Fake-system fixtures classify all swap scenarios correctly. |
| Gate C: dry-run apply | Review & Apply streams helper-style events with no privileged writes. |
| Gate D: helper validation | Helper rejects bad plans and unexpected paths. |
| Gate E: real apply | Real apply works only in a disposable Ubuntu VM and all tests above pass. |

Do not ship Gate E behavior from untested development machines.

## 26. Deliverables

Deliver these files or changes:

- Updated GTK4/libadwaita GUI source code.
- Bundled SVG icon resources.
- Updated packaging files.
- Updated README screenshots using the provided menu screenshots or new real app screenshots.
- Updated user documentation.
- Test suite additions.
- Diagnostic export implementation.
- Release notes for this GUI redesign.

---

## Rev B production/public-use hardening alignment

The v0.42.8 implementation is aligned with the production/public-use correction task.

### UI structure decision

The GTK/libadwaita UI may be built programmatically in Python. GTK Builder XML is optional, not required. Programmatic UI construction is acceptable when widgets are grouped into testable methods/classes, business logic stays in service/controller modules, and critical widgets have stable object names for smoke tests and future UI automation.

Required stable object names are documented in `docs/gui-object-names.md` and verified by GTK smoke tests.

### Diagnostic export

The public diagnostic export format is a ZIP bundle, not a standalone `.txt` file. The bundle must include a manifest, summary, structured swap detection JSON, bounded command snapshots, redacted config snapshots, rollback context, and UI state. Redaction must avoid usernames, hostnames, machine-id, private keys, tokens, unrelated serials, and arbitrary home-directory scans.

### Encrypted swap policy

Encrypted swap is conservatively blocked from automatic hibernation configuration unless a future release implements and fixture-tests a safe path for the exact encryption model. Random-key crypttab swap, `swap` crypttab options, active unknown `/dev/mapper/*` swap, and ambiguous mapper devices are release-blocking for automatic Apply.

### Legacy scope

v0.42.8 can create/resize the managed `/swap.img` file and manage its `/etc/fstab` entry only through the reviewed helper/plan/rollback path; it still does not format partitions, repartition disks, or reboot automatically. Direct protected-file writes and dangerous command execution must remain behind the reviewed helper/plan/rollback path.
