"""GTK4 + libadwaita wizard window (spec SS4.1, SS25).

Every step page has a bottom action bar with Back and Next buttons.
Long operations run in worker threads; UI updates via GLib.idle_add.
"""
from __future__ import annotations

import datetime
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib  # noqa: E402

APP_ID = "io.github.example.UbuntuHibernateWizard"
HIBERNATE_STATUS_EXTENSION_URL = "https://extensions.gnome.org/extension/755/hibernate-status-button/"
SYSTEM_ACTION_HIBERNATE_EXTENSION_URL = "https://extensions.gnome.org/extension/3814/system-action-hibernate/"

SIZES = [("Minimum", 1.0, "Equal to RAM"),
         ("Recommended", None, "RAM + 2 GB safety margin"),
         ("Conservative", 2.0, "2 x RAM")]


def _bytes_gb(n: float) -> str:
    return f"{n / (1024**3):.0f} GB"


class WizardWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, controller) -> None:
        super().__init__(application=app, title="Hibernate Wizard",
                         default_width=680, default_height=640)
        self.controller = controller
        self.detect_info = None
        self.swap_size_mb = 18 * 1024
        self._apply_log_lines: list[str] = []
        self._apply_log_path: str | None = None
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)

        self.nav = Adw.NavigationView()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self.nav)
        self.set_content(toolbar)
        self.nav.push(self._welcome_page())

    # =================================================================
    # Page scaffold: content + Back/Next action bar on EVERY page
    # =================================================================
    def _page(self, title: str, content: Gtk.Widget, *,
              show_back: bool = True, next_label: str = "Next",
              next_cb=None, next_sensitive: bool = True,
              caption: str = "") -> tuple[Adw.NavigationPage, Gtk.Button]:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow(vexpand=True, child=content)
        outer.append(scroll)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                      margin_start=24, margin_end=24,
                      margin_top=10, margin_bottom=10)
        back = Gtk.Button(label="Back")
        back.add_css_class("pill")
        back.connect("clicked", lambda *_: self.nav.pop())
        back.set_visible(show_back)
        bar.append(back)
        bar.append(Gtk.Box(hexpand=True))                # spacer
        nxt = Gtk.Button(label=next_label)
        nxt.add_css_class("suggested-action")
        nxt.add_css_class("pill")
        nxt.set_sensitive(next_sensitive)
        if next_cb:
            nxt.connect("clicked", next_cb)
        bar.append(nxt)
        outer.append(bar)
        if caption:
            lbl = Gtk.Label(label=caption, margin_bottom=8)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("caption")
            outer.append(lbl)
        return Adw.NavigationPage(title=title, child=outer), nxt

    # ============================== Step 1: Welcome
    def _welcome_page(self) -> Adw.NavigationPage:
        status = Adw.StatusPage(icon_name="weather-clear-night-symbolic",
                                title="Enable Hibernation",
                                description="Save your session to disk and "
                                            "power off completely.")
        group = Adw.PreferencesGroup(margin_start=24, margin_end=24)
        for icon, t, s in [
            ("document-edit-symbolic", "System files will be modified",
             "GRUB, fstab, initramfs, systemd sleep and polkit settings"),
            ("folder-symbolic", "Backups are created first",
             "Every change can be rolled back"),
            ("view-refresh-symbolic", "A reboot will be required",
             "Verification continues after restart")]:
            row = Adw.ActionRow(title=t, subtitle=s)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            group.add(row)
        consent = Gtk.CheckButton(
            label="I understand this tool changes boot and power settings",
            halign=Gtk.Align.CENTER, margin_top=8)
        verify_btn = Gtk.Button(
            label="Verify existing configuration",
            halign=Gtk.Align.CENTER, margin_top=4)
        verify_btn.add_css_class("pill")
        verify_btn.connect(
            "clicked", lambda *_: self.nav.push(self._verify_page()))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        status.set_child(Gtk.Box())          # keep StatusPage compact
        box.append(status); box.append(group); box.append(consent)
        box.append(verify_btn)

        page, nxt = self._page("Welcome", box, show_back=False,
                               next_label="Continue", next_sensitive=False,
                               next_cb=lambda *_: self.nav.push(
                                   self._check_page()),
                               caption="Step 1 of 7 - nothing is changed "
                                       "until you approve the plan")
        consent.connect("toggled", lambda b: nxt.set_sensitive(b.get_active()))
        return page

    # ============================== Step 2: System check
    def _check_page(self) -> Adw.NavigationPage:
        pref = Adw.PreferencesPage()
        self._check_group = Adw.PreferencesGroup(
            title="Compatibility",
            description="Checking whether this system is supported")
        pref.add(self._check_group)
        self._sb_banner = Adw.Banner(
            title="Secure Boot is enabled - hibernation may be blocked")
        self._sb_banner.set_revealed(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self._sb_banner); box.append(pref)

        page, nxt = self._page("System Check", box,
                               next_sensitive=False,
                               next_cb=lambda *_: self.nav.push(
                                   self._swap_page()),
                               caption="Step 2 of 7")
        self._check_next = nxt
        spinner = Adw.ActionRow(title="Detecting system...")
        sp = Gtk.Spinner(spinning=True); spinner.add_prefix(sp)
        self._check_group.add(spinner)
        self._check_spinner_row = spinner
        threading.Thread(target=self._detect_worker, daemon=True).start()
        return page

    def _detect_worker(self) -> None:
        try:
            info = self.controller.detect()
            err = None
        except Exception as e:                              # noqa: BLE001
            info, err = None, str(e)
        GLib.idle_add(self._detect_done, info, err)

    def _detect_done(self, info, err) -> bool:
        self._check_group.remove(self._check_spinner_row)
        if err or info is None:
            row = Adw.ActionRow(
                title="Could not run detection",
                subtitle=(err or "unknown error") +
                         " - you can go Back and retry")
            row.add_prefix(Gtk.Image.new_from_icon_name(
                "dialog-error-symbolic"))
            self._check_group.add(row)
            return False                     # Back still works: no dead end
        self.detect_info = info
        hard_stop = False
        for name, sub, cls, status in info.rows:
            row = Adw.ActionRow(title=name, subtitle=sub)
            lbl = Gtk.Label(label=status)
            lbl.add_css_class(cls)
            row.add_suffix(lbl)
            self._check_group.add(row)
            if cls == "error":
                hard_stop = True
        self._sb_banner.set_revealed(info.secure_boot)
        if hard_stop:
            self._check_next.set_label("Unsupported")
        else:
            if info.secure_boot:
                self._check_next.set_label("Continue Anyway")
            self._check_next.set_sensitive(True)
        return False

    # ============================== Step 3: Swap size
    def _swap_page(self) -> Adw.NavigationPage:
        ram = getattr(self.detect_info, "ram_bytes", 16 * 1024**3)
        gb = 1024 ** 3
        min_b = ram                      # hibernation needs >= RAM
        rec_b = ram + 2 * gb
        dbl_b = 2 * ram
        max_b = int(2.5 * ram)
        max_custom_gb = max(max_b / gb, 256)
        self.swap_size_mb = int(rec_b / 2**20)
        self._syncing_swap_widgets = False

        pref = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Swap File Size",
            description=f"Detected RAM: {_bytes_gb(ram)} - hibernation "
                        f"needs disk swap at least this large")
        pref.add(group)

        # ---- value readout
        self._size_label = Gtk.Label()
        self._size_label.add_css_class("title-2")

        # ---- slider with mapped marks
        adj = Gtk.Adjustment(lower=min_b / gb, upper=max_b / gb,
                             value=rec_b / gb, step_increment=1,
                             page_increment=4)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                          adjustment=adj, hexpand=True,
                          margin_start=4, margin_end=4)
        scale.set_digits(0)
        scale.set_size_request(-1, 88)   # wide GNOME-Disks-style track area
        # Recommended on TOP, Minimum / Double RAM on BOTTOM -> no overlap
        scale.add_mark(rec_b / gb, Gtk.PositionType.TOP,
                       f"Recommended {_bytes_gb(rec_b)}")
        scale.add_mark(min_b / gb, Gtk.PositionType.BOTTOM,
                       f"Minimum {_bytes_gb(min_b)}")
        scale.add_mark(dbl_b / gb, Gtk.PositionType.BOTTOM,
                       f"Double RAM {_bytes_gb(dbl_b)}")
        # unlabeled ticks every 4 GB, GNOME Disks style
        t = int(min_b / gb) + 4 - int(min_b / gb) % 4
        while t < max_b / gb:
            if all(abs(t - m / gb) > 0.9 for m in (min_b, rec_b, dbl_b)):
                scale.add_mark(t, Gtk.PositionType.BOTTOM, None)
            t += 4
        self._swap_scale = scale

        # ---- custom size text field / spin button
        custom_adj = Gtk.Adjustment(lower=min_b / gb, upper=max_custom_gb,
                                    value=rec_b / gb, step_increment=1,
                                    page_increment=4)
        custom_spin = Gtk.SpinButton(adjustment=custom_adj, climb_rate=1,
                                     digits=1, numeric=True, hexpand=False)
        custom_spin.set_width_chars(8)
        custom_spin.set_tooltip_text("Custom swap size in GB")
        self._custom_swap_spin = custom_spin

        self._preset_rbs = []

        def set_swap_gb(v_gb: float, *, update_scale: bool,
                        update_spin: bool) -> None:
            self.swap_size_mb = int(round(v_gb * 1024))
            self._size_label.set_label(f"{v_gb:.1f} GB")
            if update_scale:
                scale_adj = self._swap_scale.get_adjustment()
                if v_gb > scale_adj.get_upper():
                    scale_adj.set_upper(v_gb)
                self._swap_scale.set_value(v_gb)
            if update_spin:
                self._custom_swap_spin.set_value(v_gb)
            for rb, b in self._preset_rbs:
                rb.handler_block(rb._h)
                rb.set_active(abs(v_gb - b / gb) < 0.5)
                rb.handler_unblock(rb._h)

        def on_scale(sc):
            if self._syncing_swap_widgets:
                return
            self._syncing_swap_widgets = True
            try:
                set_swap_gb(sc.get_value(), update_scale=False, update_spin=True)
            finally:
                self._syncing_swap_widgets = False

        def on_custom_size(spin):
            if self._syncing_swap_widgets:
                return
            self._syncing_swap_widgets = True
            try:
                set_swap_gb(spin.get_value(), update_scale=True, update_spin=False)
            finally:
                self._syncing_swap_widgets = False

        scale.connect("value-changed", on_scale)
        custom_spin.connect("value-changed", on_custom_size)

        srow = Adw.PreferencesGroup()
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                         margin_top=6, margin_bottom=10)
        holder.append(self._size_label)
        holder.append(scale)
        srow.add(holder)
        pref.add(srow)

        # ---- preset rows (quick select -> snap slider)
        first = None
        presets = [
            (f"Minimum - {_bytes_gb(min_b)}", "Equal to RAM", min_b),
            (f"Recommended - {_bytes_gb(rec_b)}", "RAM + 2 GB safety margin",
             rec_b),
            (f"Double RAM - {_bytes_gb(dbl_b)}",
             "Extra headroom for heavy memory use", dbl_b)]
        for idx, (label, sub, b) in enumerate(presets):
            row = Adw.ActionRow(title=label, subtitle=sub)
            rb = Gtk.CheckButton()
            if first is None:
                first = rb
            else:
                rb.set_group(first)
            rb._h = rb.connect(
                "toggled",
                lambda btn, v=b / gb: btn.get_active()
                and self._swap_scale.set_value(v))
            if idx == 1:
                rb.set_active(True)
            row.add_prefix(rb)
            row.set_activatable_widget(rb)
            group.add(row)
            self._preset_rbs.append((rb, b))

        custom_group = Adw.PreferencesGroup(
            title="Custom size",
            description="Type an exact swap size in GB if the presets are not suitable.")
        custom_row = Adw.ActionRow(
            title="Custom swap size",
            subtitle="Values below detected RAM are not allowed")
        custom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                             valign=Gtk.Align.CENTER)
        custom_box.append(custom_spin)
        custom_box.append(Gtk.Label(label="GB"))
        custom_row.add_suffix(custom_box)
        custom_row.set_activatable_widget(custom_spin)
        custom_group.add(custom_row)
        pref.add(custom_group)

        set_swap_gb(rec_b / gb, update_scale=False, update_spin=True)

        page, _ = self._page("Swap File", pref,
                             next_cb=lambda *_: self.nav.push(
                                 self._plan_page()),
                             caption="Step 3 of 7 - drag the slider, pick "
                                     "a preset, or type a custom size")
        return page

    # ============================== Step 4: Plan review
    def _plan_page(self) -> Adw.NavigationPage:
        pref = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Review Planned Changes",
            description="Nothing has been changed yet. These steps run "
                        "only after you press Apply.")
        pref.add(group)
        steps = self.controller.build_plan(self.swap_size_mb)
        for i, step in enumerate(steps, 1):
            group.add(Adw.ActionRow(title=f"{i}. {step}"))

        page, _ = self._page("Plan", pref, next_label="Apply Changes",
                             next_cb=lambda *_: self.nav.push(
                                 self._apply_page()),
                             caption="Step 4 of 7 - you will be asked for "
                                     "your password once")
        return page

    # ============================== Step 5: Apply (threaded, progress)
    def _apply_page(self) -> Adw.NavigationPage:
        self._apply_log_lines = []
        self._apply_log_path = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_start=24, margin_end=24, margin_top=24,
                      margin_bottom=12)
        self._progress = Gtk.ProgressBar(show_text=True, text="Starting...")

        self._log_buffer = Gtk.TextBuffer()
        self._log_view = Gtk.TextView(buffer=self._log_buffer,
                                      editable=False, cursor_visible=False,
                                      monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self._log_view.add_css_class("monospace")
        log_scroll = Gtk.ScrolledWindow(child=self._log_view,
                                        min_content_height=220,
                                        vexpand=True, hexpand=True)
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._log_expander = Gtk.Expander(label="Live log", expanded=True)
        self._log_expander.set_child(log_scroll)

        self._log_saved_label = Gtk.Label(label="", xalign=0, wrap=True)
        self._log_saved_label.add_css_class("dim-label")
        self._log_saved_label.add_css_class("caption")

        self._reboot_now_button = Gtk.Button(label="Reboot Now", halign=Gtk.Align.END)
        self._reboot_now_button.add_css_class("destructive-action")
        self._reboot_now_button.add_css_class("pill")
        self._reboot_now_button.set_visible(False)
        self._reboot_now_button.connect("clicked", self._on_reboot_now_clicked)

        box.append(self._progress)
        box.append(self._log_expander)
        box.append(self._log_saved_label)
        box.append(self._reboot_now_button)

        page, nxt = self._page("Applying Changes", box,
                               next_label="Working...",
                               next_sensitive=False,
                               caption="Step 5 of 7")
        self._apply_next = nxt
        self._append_apply_log("Starting hibernation configuration")
        threading.Thread(target=self._apply_worker, daemon=True).start()
        return page

    def _append_apply_log(self, line: str) -> None:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{stamp}] {line or ''}"
        self._apply_log_lines.append(entry)
        if hasattr(self, "_log_buffer"):
            end = self._log_buffer.get_end_iter()
            self._log_buffer.insert(end, entry + "\n")
            mark = self._log_buffer.create_mark(None,
                                                self._log_buffer.get_end_iter(),
                                                False)
            self._log_view.scroll_mark_onscreen(mark)

    def _save_apply_log(self) -> str:
        downloads = Path.home() / "Downloads"
        try:
            downloads.mkdir(parents=True, exist_ok=True)
        except OSError:
            downloads = Path.home()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = downloads / f"hibernation_wizard_{stamp}.log"
        path.write_text("\n".join(self._apply_log_lines) + "\n",
                        encoding="utf-8")
        self._apply_log_path = str(path)
        return self._apply_log_path

    def _apply_worker(self) -> None:
        def prog(pct, line):
            GLib.idle_add(self._apply_progress, pct, line)
        try:
            ok, message = self.controller.apply(self.swap_size_mb, prog)
        except Exception as e:                              # noqa: BLE001
            ok, message = False, str(e)
        GLib.idle_add(self._apply_finished, ok, message)

    def _apply_progress(self, pct, line) -> bool:
        if pct is not None:
            self._progress.set_fraction(min(pct, 100) / 100)
        self._progress.set_text(line or "")
        if line:
            self._append_apply_log(line)
        return False

    def _apply_finished(self, ok: bool, message: str) -> bool:
        if ok:
            self._progress.set_fraction(1.0)
            self._progress.set_text("Done - reboot required")
            self._append_apply_log("Finished successfully - reboot required")
            log_path = self._save_apply_log()
            self._append_apply_log(f"Full log saved to {log_path}")
            # Write again so the saved file also contains the saved-path line.
            Path(log_path).write_text("\n".join(self._apply_log_lines) + "\n",
                                     encoding="utf-8")
            self._log_saved_label.set_label(f"Full log saved to: {log_path}")
            self._reboot_now_button.set_visible(True)
            self._apply_next.set_label("Reboot Later")
            self._apply_next.connect(
                "clicked",
                lambda *_: self.nav.push(self._done_page(rebooted=False)))
        else:
            self._progress.set_text("Failed")
            self._append_apply_log(f"Failed: {message}")
            log_path = self._save_apply_log()
            self._append_apply_log(f"Full log saved to {log_path}")
            Path(log_path).write_text("\n".join(self._apply_log_lines) + "\n",
                                     encoding="utf-8")
            self._log_saved_label.set_label(f"Full log saved to: {log_path}")
            self._apply_next.set_label("Back to Plan")
            self._apply_next.connect("clicked", lambda *_: self.nav.pop())
        self._apply_next.set_sensitive(True)
        return False

    def _on_reboot_now_clicked(self, *_args) -> None:
        self._reboot_now_button.set_sensitive(False)
        self._apply_next.set_sensitive(False)
        self._append_apply_log("Reboot Now clicked")
        self._progress.set_text("Requesting reboot...")
        threading.Thread(target=self._reboot_now_worker, daemon=True).start()

    def _reboot_now_worker(self) -> None:
        try:
            ok, message = self.controller.reboot_now()
        except Exception as e:                              # noqa: BLE001
            ok, message = False, str(e)
        GLib.idle_add(self._reboot_now_done, ok, message)

    def _reboot_now_done(self, ok: bool, message: str) -> bool:
        if ok:
            self._append_apply_log("Reboot command accepted")
            self._progress.set_text("Reboot command accepted")
        else:
            self._append_apply_log(f"Reboot failed: {message}")
            self._progress.set_text("Reboot failed")
            self._reboot_now_button.set_sensitive(True)
            self._apply_next.set_sensitive(True)
        if self._apply_log_path:
            Path(self._apply_log_path).write_text(
                "\n".join(self._apply_log_lines) + "\n", encoding="utf-8")
        return False

    # ============================== Step 6: Verify
    def _verify_page(self) -> Adw.NavigationPage:
        pref = Adw.PreferencesPage()
        self._verify_group = Adw.PreferencesGroup(
            title="Verification",
            description="Comparing what the kernel uses with reality")
        pref.add(self._verify_group)
        page, nxt = self._page("Verify", pref, next_label="...",
                               next_sensitive=False,
                               caption="Step 6 of 7")
        self._verify_next = nxt
        threading.Thread(target=self._verify_worker, daemon=True).start()
        return page

    def _verify_worker(self) -> None:
        try:
            res = self.controller.verify()
            err = None
        except Exception as e:                              # noqa: BLE001
            res, err = None, str(e)
        GLib.idle_add(self._verify_done, res, err)

    def _verify_done(self, res, err) -> bool:
        if err or res is None:
            self._verify_group.add(Adw.ActionRow(
                title="Verification failed to run", subtitle=err or ""))
            return False
        names = {"swap": "Active swap file", "uuid": "Resume UUID",
                 "offset": "Resume offset", "initramfs": "initramfs config"}
        for key, label in names.items():
            ok = res["checks"].get(key)
            row = Adw.ActionRow(title=label)
            mark = Gtk.Label(label="Pass" if ok else "Fail")
            mark.add_css_class("success" if ok else "error")
            row.add_suffix(mark)
            self._verify_group.add(row)
        if res["all_ok"]:
            self._verify_next.set_label("Finish")
            self._verify_next.connect(
                "clicked", lambda *_: self.nav.push(
                    self._done_page(rebooted=True)))
        else:
            for e in res["errors"]:
                self._verify_group.add(Adw.ActionRow(title=e))
            self._verify_next.set_label("Repair and Reboot")
            self._verify_next.connect(
                "clicked", lambda *_: self.controller.repair())
        self._verify_next.set_sensitive(True)
        return False

    # ============================== Done
    def _done_page(self, rebooted: bool) -> Adw.NavigationPage:
        if rebooted:
            title = "Hibernation Is Configured"
            description = "Test it from the power menu, or with: systemctl hibernate"
            icon = "emblem-ok-symbolic"
        else:
            title = "Reboot Required"
            description = ("Restart your computer, then open Hibernate Wizard again "
                           "to verify the configuration.")
            icon = "view-refresh-symbolic"

        st = Adw.StatusPage(icon_name=icon, title=title, description=description)
        st.set_child(Gtk.Box())

        group = Adw.PreferencesGroup(
            title="Optional GNOME power-menu buttons",
            description="After hibernation works, install one of these GNOME Shell "
                        "extensions to expose Hibernate in the shell power menu.",
            margin_start=24, margin_end=24)

        row = Adw.ActionRow(
            title="Hibernate Status Button",
            subtitle="Adds Hibernate and Hybrid Sleep actions to the GNOME status menu")
        link = Gtk.LinkButton.new_with_label(
            HIBERNATE_STATUS_EXTENSION_URL, "Open Extension")
        row.add_suffix(link)
        row.set_activatable_widget(link)
        group.add(row)

        row2 = Adw.ActionRow(
            title="System Action - Hibernate",
            subtitle="Adds Hibernate among GNOME system actions")
        link2 = Gtk.LinkButton.new_with_label(
            SYSTEM_ACTION_HIBERNATE_EXTENSION_URL, "Open Extension")
        row2.add_suffix(link2)
        row2.set_activatable_widget(link2)
        group.add(row2)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(st)
        box.append(group)

        page, _ = self._page("Next Steps", box, next_label="Close",
                             next_cb=lambda *_: self.close(),
                             caption="Step 7 of 7")
        return page


class WizardApp(Adw.Application):
    def __init__(self, controller) -> None:
        super().__init__(application_id=APP_ID)
        self.controller = controller

    def do_activate(self) -> None:
        win = self.props.active_window or WizardWindow(self, self.controller)
        win.present()
