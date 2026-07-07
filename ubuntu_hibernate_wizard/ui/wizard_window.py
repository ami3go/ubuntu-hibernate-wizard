"""GTK4/libadwaita wizard window for Ubuntu Hibernate Wizard v0.42.

The UI follows the approved GTK4 sidebar mockups and the v0.42 safety scope:
existing active swap partition/file targets plus the controlled managed
swap-file create/resize flow; no automatic reboot button.
"""
from __future__ import annotations

import datetime as _dt
import threading
from pathlib import Path


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from ubuntu_hibernate_wizard.constants import APP_ID, APP_NAME, APP_VERSION, RESUME_FILE, GRUB_FRAGMENT
from ubuntu_hibernate_wizard.services.hibernate_planner import SwapFileRequest, suggested_swap_sizes, swapfile_slider_marks, DEFAULT_SWAPFILE_PATH, GIB
from ubuntu_hibernate_wizard.services.swap_target_model import SwapTarget, format_bytes_gib

HIBERNATE_STATUS_EXTENSION_URL = "https://extensions.gnome.org/extension/755/hibernate-status-button/"
SYSTEM_ACTION_HIBERNATE_EXTENSION_URL = "https://extensions.gnome.org/extension/3814/system-action-hibernate/"


class WizardWindow(Adw.ApplicationWindow):
    STEP_KEYS = ["intro", "check", "config", "plan", "apply", "finish", "help", "about"]
    STEP_TITLES = {
        "intro": "Introduction",
        "check": "System Check",
        "config": "Configuration",
        "plan": "Planned Modifications",
        "apply": "Review & Apply",
        "finish": "Finish",
        "help": "Help",
        "about": "About",
    }

    def __init__(self, app: Adw.Application, controller) -> None:
        super().__init__(application=app, title=APP_NAME, default_width=1080, default_height=720)
        self.set_icon_name(APP_ID)
        self.set_name("app_window")
        self.controller = controller
        self.detect_info = None
        self.profile = None
        self.selected_target: SwapTarget | None = None
        self.swap_file_request: SwapFileRequest | None = None
        self._swapfile_size_bytes: int = 0
        self.plan = None
        self._step_rows: dict[str, Gtk.ListBoxRow] = {}
        self._step_state: dict[str, str] = {k: "pending" for k in self.STEP_KEYS}
        self._log_buffer: Gtk.TextBuffer | None = None
        self._apply_running = False

        self._load_css()
        self.set_content(self._build_shell())
        self._show_page("intro")

    # ---------------------------------------------------------------- shell
    def _load_css(self) -> None:
        css = Gtk.CssProvider()
        css_path = Path(__file__).resolve().parents[1] / "css" / "app.css"
        if css_path.exists():
            css.load_from_path(str(css_path))
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    @staticmethod
    def _icon_path(name: str) -> str:
        clean = name[:-4] if name.endswith(".svg") else name[:-4] if name.endswith(".png") else name
        icons_dir = Path(__file__).resolve().parents[1] / "assets" / "icons"
        for ext in (".png", ".svg"):
            path = icons_dir / f"{clean}{ext}"
            if path.exists():
                return str(path)
        return str(icons_dir / "info-note.svg")

    @staticmethod
    def _banner_path() -> str:
        assets_dir = Path(__file__).resolve().parents[1] / "assets"
        for ext in (".png", ".svg"):
            path = assets_dir / f"banner{ext}"
            if path.exists():
                return str(path)
        return str(assets_dir / "icons" / "info-note.svg")

    @staticmethod
    def _runtime_diagram_path() -> str:
        assets_dir = Path(__file__).resolve().parents[1] / "assets"
        path = assets_dir / "runtime-hibernation-resume.png"
        if path.exists():
            return str(path)
        return str(assets_dir / "icons" / "info-note.svg")

    def _runtime_diagram_picture(self) -> Gtk.Widget:
        picture = Gtk.Picture.new_for_filename(self._runtime_diagram_path())
        picture.set_can_shrink(True)
        picture.set_keep_aspect_ratio(True)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_name("runtime_hibernation_resume_diagram")
        picture.set_size_request(-1, 420)
        return picture

    def _img(self, name: str, pixel_size: int = 24) -> Gtk.Image:
        if name.startswith("themed:"):
            img = Gtk.Image.new_from_icon_name(name.split(":", 1)[1])
        else:
            img = Gtk.Image.new_from_file(self._icon_path(name))
        img.set_pixel_size(pixel_size)
        return img

    def _set_img(self, img: Gtk.Image, name: str, pixel_size: int = 24) -> None:
        if name.startswith("themed:"):
            img.set_from_icon_name(name.split(":", 1)[1])
        else:
            img.set_from_file(self._icon_path(name))
        img.set_pixel_size(pixel_size)

    def _banner_picture(self) -> Gtk.Widget:
        picture = Gtk.Picture.new_for_filename(self._banner_path())
        picture.set_can_shrink(True)
        picture.set_keep_aspect_ratio(True)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_name("hero_banner")
        picture.set_size_request(-1, 260)
        return picture

    def _build_shell(self) -> Gtk.Widget:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=APP_NAME, subtitle="Safe hibernation setup for Ubuntu"))
        toolbar.add_top_bar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.add_css_class("uhw-root")
        root.append(self._build_sidebar())
        self.stack = Gtk.Stack(hexpand=True, vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        root.append(self.stack)
        toolbar.set_content(root)
        return toolbar

    def _build_sidebar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=280,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=8)
        box.add_css_class("uhw-sidebar")
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand_icon = self._img("app-icon", 40)
        brand_icon.set_name("sidebar_brand_icon")
        brand_icon.set_valign(Gtk.Align.CENTER)
        brand.append(brand_icon)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, vexpand=False)
        title = Gtk.Label(label="Hibernate Wizard", xalign=0)
        title.add_css_class("title-3")
        subtitle = Gtk.Label(label="v0.42 · swap target + managed /swap.img", xalign=0)
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        brand_text.append(title)
        brand_text.append(subtitle)
        brand.append(brand_text)
        box.append(brand)

        self.step_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.step_list.add_css_class("boxed-list")
        for key in self.STEP_KEYS[:6]:
            row = self._sidebar_row(key)
            self.step_list.append(row)
        box.append(self.step_list)
        box.append(Gtk.Box(vexpand=True))

        secondary = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        secondary.add_css_class("boxed-list")
        for key in ("help", "about"):
            secondary.append(self._sidebar_row(key))
        box.append(secondary)
        return box

    def _sidebar_row(self, key: str) -> Gtk.ListBoxRow:
        """Build a sidebar row with an explicit label.

        v0.42.20 keeps explicit labels and explicit click activation to avoid GTK/libadwaita title rendering regressions here.
        The Review & Apply step previously appeared as an icon-only row on some
        GTK/libadwaita combinations, so the visible navigation text is now a
        normal Gtk.Label with a stable object name.
        """
        title = self.STEP_TITLES[key]
        row = Gtk.ListBoxRow(activatable=True, selectable=False)
        row.set_name(f"nav_{key}")
        row.set_tooltip_text(title)
        row.add_css_class("uhw-nav-row")

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                       margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
        img = self._img(self._icon_for_state("pending"), 18)
        label = Gtk.Label(label=title, xalign=0, hexpand=True)
        label.set_name(f"nav_label_{key}")
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_tooltip_text(title)
        body.append(img)
        body.append(label)
        row.set_child(body)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("released", lambda _gesture, _n_press, _x, _y, k=key: self._maybe_open(k))
        body.add_controller(click)

        row._uhw_state_icon = img
        row._uhw_title_label = label
        row.connect("activate", lambda *_k, k=key: self._maybe_open(k))
        self._step_rows[key] = row
        return row

    def _maybe_open(self, key: str) -> None:
        if key in {"help", "about"}:
            self._show_page(key)
            return
        if self._apply_running:
            return
        order = self.STEP_KEYS[:6]
        max_allowed = 0
        if self.detect_info is not None:
            max_allowed = 2
        if self.selected_target is not None or self.swap_file_request is not None:
            max_allowed = 3
        if self.plan is not None:
            max_allowed = 4
        if self._step_state.get("finish") in {"active", "passed"}:
            max_allowed = 5
        if order.index(key) <= max_allowed:
            self._show_page(key)

    def _show_page(self, key: str) -> None:
        if not self.stack.get_child_by_name(key):
            page = self._page_widget_for(key)
            page.set_name({
                "intro": "page_discovery",
                "check": "page_discovery",
                "config": "page_swap_target",
                "plan": "page_plan",
                "apply": "page_apply",
                "finish": "page_verify",
                "help": "page_diagnostics",
                "about": "page_about",
            }.get(key, f"page_{key}"))
            self.stack.add_named(page, key)
        self.stack.set_visible_child_name(key)
        for k in self.STEP_KEYS:
            if self._step_state.get(k) == "active":
                self._step_state[k] = "passed" if k not in {"help", "about"} else "pending"
        self._step_state[key] = "active"
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        for key, row in self._step_rows.items():
            state = self._step_state.get(key, "pending")
            icon = getattr(row, "_uhw_state_icon", None)
            if icon is not None:
                self._set_img(icon, self._icon_for_state(state), 18)
            if state == "active":
                row.add_css_class("accent")
            else:
                row.remove_css_class("accent")

    @staticmethod
    def _icon_for_state(state: str) -> str:
        return {
            "passed": "success-check",
            "warning": "warning",
            "error": "error",
            "active": "next",
            "pending": "status-pending",
        }.get(state, "status-pending")

    # ---------------------------------------------------------------- pages
    def _page_widget_for(self, key: str) -> Gtk.Widget:
        return {
            "intro": self._intro_page,
            "check": self._check_page,
            "config": self._config_page,
            "plan": self._plan_page,
            "apply": self._apply_page,
            "finish": self._finish_page,
            "help": self._help_page,
            "about": self._about_page,
        }[key]()

    def _scrolled(self, child: Gtk.Widget) -> Gtk.Widget:
        """Return a page scroller that prevents bottom controls from covering content."""
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(False)
        scroller.set_child(child)
        return scroller

    def _content_box(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20,
                      margin_top=28, margin_bottom=36, margin_start=32, margin_end=32)
        box.set_size_request(680, -1)
        box.set_hexpand(True)
        box.set_vexpand(False)
        return box

    def _label(self, text: str, *, css: str | None = None, xalign: float = 0,
               justify: Gtk.Justification = Gtk.Justification.LEFT, monospace: bool = False) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=xalign, wrap=True, hexpand=True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_justify(justify)
        label.set_valign(Gtk.Align.START)
        label.set_selectable(False)
        if monospace:
            label.add_css_class("monospace")
        if css:
            label.add_css_class(css)
        return label

    def _card(self, title: str, subtitle: str = "", icon: str | None = None) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=2, margin_bottom=2, margin_start=2, margin_end=2)
        card.set_hexpand(True)
        card.add_css_class("uhw-card")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        head.set_hexpand(True)
        head.set_valign(Gtk.Align.START)
        if icon:
            image = self._img(icon, 30)
            image.set_valign(Gtk.Align.START)
            head.append(image)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        t = self._label(title, css="heading")
        labels.append(t)
        if subtitle:
            labels.append(self._label(subtitle, css="dim-label"))
        head.append(labels)
        card.append(head)
        return card

    def _button_row(self, *buttons: Gtk.Button) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        row.add_css_class("uhw-button-row")
        row.set_hexpand(True)
        for b in buttons:
            row.append(b)
        return row

    def _status_pill(self, text: str, kind: str = "neutral") -> Gtk.Label:
        pill = Gtk.Label(label=text, xalign=0.5)
        pill.set_valign(Gtk.Align.CENTER)
        pill.add_css_class("uhw-pill")
        if kind in {"success", "warning", "error", "active"}:
            pill.add_css_class(f"uhw-pill-{kind}")
        return pill

    def _row_card(self, title: str, detail: str = "", icon: str = "info-note",
                  status: str | None = None, kind: str = "neutral",
                  prefix_widget: Gtk.Widget | None = None, suffix_widget: Gtk.Widget | None = None,
                  disabled: bool = False) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                      margin_top=2, margin_bottom=2)
        row.set_hexpand(True)
        row.add_css_class("uhw-row")
        if disabled:
            row.set_sensitive(False)
            row.add_css_class("uhw-row-disabled")
        if prefix_widget is not None:
            prefix_widget.set_valign(Gtk.Align.CENTER)
            row.append(prefix_widget)
        else:
            image = self._img(icon, 22)
            image.set_valign(Gtk.Align.START if detail else Gtk.Align.CENTER)
            row.append(image)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.append(self._label(title, css="uhw-row-title"))
        if detail:
            text_box.append(self._label(detail, css="dim-label"))
        row.append(text_box)
        if suffix_widget is not None:
            suffix_widget.set_valign(Gtk.Align.CENTER)
            row.append(suffix_widget)
        elif status:
            row.append(self._status_pill(status, kind))
        return row

    def _plain_row(self, text: str, icon: str = "success-check") -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin_top=4, margin_bottom=4)
        image = self._img(icon, 18)
        image.set_valign(Gtk.Align.START)
        row.append(image)
        row.append(self._label(text))
        return row

    def _key_value_row(self, key: str, value: str) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=4, margin_bottom=4)
        label = Gtk.Label(label=key, xalign=0)
        label.add_css_class("uhw-kv-key")
        label.set_size_request(140, -1)
        label.set_valign(Gtk.Align.START)
        row.append(label)
        val = self._label(value, css="dim-label", monospace=True)
        val.set_selectable(True)
        row.append(val)
        return row

    def _process_diagram(self, title: str, subtitle: str, steps: list[tuple[str, str] | tuple[str, str, int]], *, object_name: str | None = None) -> Gtk.Box:
        card = self._card(title, subtitle, "runtime-cycle")
        if object_name:
            card.set_name(object_name)
        flow = Gtk.FlowBox()
        flow.add_css_class("uhw-diagram")
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_min_children_per_line(2)
        flow.set_max_children_per_line(6)
        flow.set_column_spacing(10)
        flow.set_row_spacing(10)
        flow.set_homogeneous(True)
        for idx, step in enumerate(steps, start=1):
            if len(step) == 3:
                label, icon, icon_size = step
            else:
                label, icon = step
                icon_size = 62 if icon == "app-icon" else 56
            step_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            step_box.set_size_request(124, -1)
            step_box.add_css_class("uhw-diagram-step")

            overlay = Gtk.Overlay()
            overlay.set_hexpand(True)
            overlay.set_halign(Gtk.Align.FILL)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            content.set_hexpand(True)
            content.set_halign(Gtk.Align.FILL)
            image = self._img(icon, icon_size)
            image.add_css_class("uhw-diagram-icon")
            image.set_halign(Gtk.Align.CENTER)
            content.append(image)
            content.append(self._label(label, css="uhw-diagram-label", xalign=0.5, justify=Gtk.Justification.CENTER))

            overlay.set_child(content)
            badge = self._status_pill(str(idx), "active")
            badge.add_css_class("uhw-diagram-badge")
            badge.set_halign(Gtk.Align.START)
            badge.set_valign(Gtk.Align.START)
            overlay.add_overlay(badge)

            step_box.append(overlay)
            flow.append(step_box)
        card.append(flow)
        return card

    def _intro_page(self) -> Gtk.Widget:
        box = self._content_box()
        banner_card = self._card("Ubuntu Hibernate Wizard", "Enable · Verify · Repair", "app-icon")
        banner_card.append(self._banner_picture())
        banner_card.append(self._label("The wizard checks your system, lets you choose a target, shows every planned file change, applies through a privileged helper, then asks you to reboot manually."))
        box.append(banner_card)

        can = self._card("What this wizard can do", "Use an existing swap target or prepare a managed /swap.img file.", "disk")
        for text in ["Detect GRUB + initramfs-tools support", "Classify swap partitions, swap files, zram, size, UUID and resume offset", "Optionally create or resize managed /swap.img", "Write managed resume and GRUB fragment files", "Create rollback metadata before changing files"]:
            can.append(self._plain_row(text))
        box.append(can)

        cont = Gtk.Button(label="Continue to System Check")
        cont.add_css_class("suggested-action")
        cont.connect("clicked", lambda *_: self._show_page("check"))
        box.append(self._button_row(cont))
        return self._scrolled(box)

    def _check_page(self) -> Gtk.Widget:
        box = self._content_box()
        self._check_summary = self._card("System check", "Press Refresh checks to inspect this machine.", "themed:utilities-system-monitor-symbolic")
        self._check_summary.set_name("status_banner")
        self._check_summary_label = self._label("Summary: Not checked yet", css="uhw-row-title")
        self._check_summary.append(self._check_summary_label)
        box.append(self._check_summary)
        self._check_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._check_group.set_name("blocker_list")
        box.append(self._check_group)
        refresh = Gtk.Button(label="Refresh checks")
        refresh.set_name("btn_analyze")
        refresh.add_css_class("suggested-action")
        refresh.connect("clicked", self._start_detect)
        export = Gtk.Button(label="Export diagnostic ZIP")
        export.set_name("btn_export_diagnostics")
        export.connect("clicked", self._export_report)
        next_btn = Gtk.Button(label="Continue to Configuration")
        next_btn.set_name("btn_continue_configuration")
        next_btn.connect("clicked", lambda *_: self._show_page("config"))
        self._check_next_btn = next_btn
        next_btn.set_sensitive(self.detect_info is not None and not self.detect_info.hard_stop)
        box.append(self._button_row(refresh, export, next_btn))
        if self.detect_info is None:
            GLib.idle_add(lambda: (self._start_detect(), False)[1])
        else:
            self._render_detect_info()
        return self._scrolled(box)

    def _export_report(self, *_args) -> None:
        try:
            path = self.controller.export_diagnostics()
            self._append_check_row("Export", f"Diagnostic report saved to {path}", "success", "Saved")
        except Exception as exc:  # noqa: BLE001
            self._append_check_row("Export failed", str(exc), "error", "Failed")

    def _start_detect(self, *_args) -> None:
        for child in list(self._check_group):
            self._check_group.remove(child)
        self._append_check_row("Detecting system...", "Reading swap, GRUB, initramfs, Secure Boot and resume configuration", "pending", "Running")
        self._check_next_btn.set_sensitive(False)
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self) -> None:
        try:
            info = self.controller.detect()
            err = None
        except Exception as exc:  # noqa: BLE001
            info, err = None, str(exc)
        GLib.idle_add(self._detect_done, info, err)

    def _detect_done(self, info, err) -> bool:
        if err or info is None:
            self.detect_info = None
            self._step_state["check"] = "error"
            self._render_check_error(err or "Unknown detection error")
        else:
            self.detect_info = info
            self.profile = info.profile
            self.selected_target = info.recommended_target
            self.swap_file_request = None
            if info.recommended_target is None and info.profile is not None:
                self._swapfile_size_bytes = suggested_swap_sizes(info.profile.ram_bytes)[1][1]
                self.swap_file_request = SwapFileRequest(DEFAULT_SWAPFILE_PATH, self._swapfile_size_bytes)
            self._step_state["check"] = "error" if info.hard_stop else "warning" if any(r[2] == "warning" for r in info.rows) else "passed"
            self._render_detect_info()
        self._refresh_sidebar()
        return False

    def _render_check_error(self, message: str) -> None:
        for child in list(self._check_group):
            self._check_group.remove(child)
        if hasattr(self, "_check_summary_label"):
            self._check_summary_label.set_label("Summary: Blocked")
            self._check_summary_label.set_tooltip_text(message)
        self._append_check_row("System check failed", message, "error", "Blocked")
        self._check_next_btn.set_sensitive(False)

    def _render_detect_info(self) -> None:
        for child in list(self._check_group):
            self._check_group.remove(child)
        assert self.detect_info is not None
        title = "Ready" if not self.detect_info.hard_stop else "Blocked"
        if not self.detect_info.hard_stop and any(r[2] == "warning" for r in self.detect_info.rows):
            title = "Ready with warnings"
        if hasattr(self, "_check_summary_label"):
            self._check_summary_label.set_label(f"Summary: {title}")
            self._check_summary_label.set_tooltip_text(None)
        for title_, detail, cls, status in self.detect_info.rows:
            self._append_check_row(title_, detail, cls, status)
        self._check_next_btn.set_sensitive(not self.detect_info.hard_stop)

    def _append_check_row(self, title: str, detail: str, cls: str, status: str) -> None:
        icon = {"success": "success-check", "warning": "warning", "error": "error"}.get(cls, "status-pending")
        kind = cls if cls in {"success", "warning", "error"} else "neutral"
        self._check_group.append(self._row_card(title, detail, icon, status, kind))

    def _config_page(self) -> Gtk.Widget:
        box = self._content_box()
        box.append(self._card("Configuration", "Select an existing hibernation target, or create/resize the managed /swap.img file using the controls below.", "configuration"))
        self._target_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._target_group.set_name("swap_target_list")
        box.append(self._target_group)
        self._render_targets()
        box.append(self._swapfile_controls_card())
        next_btn = Gtk.Button(label="Continue to Planned Modifications")
        next_btn.add_css_class("suggested-action")
        next_btn.set_sensitive(self._config_can_continue())
        self._config_next_btn = next_btn
        next_btn.connect("clicked", lambda *_: self._go_plan())
        box.append(self._button_row(next_btn))
        return self._scrolled(box)

    def _render_targets(self) -> None:
        for child in list(self._target_group):
            self._target_group.remove(child)
        if not self.profile or not self.profile.candidates:
            self._target_group.append(self._row_card(
                "No usable existing disk swap",
                "Use the managed /swap.img controls below to create or resize a swap file, or enable an existing swap target manually and refresh checks.",
                "warning", "Blocked", "error"))
            return
        first = None
        for cand in self.profile.candidates:
            radio = Gtk.CheckButton()
            if first is None:
                first = radio
            else:
                radio.set_group(first)
            radio.set_sensitive(cand.selectable)
            radio.set_active(self.selected_target is not None and cand.id == self.selected_target.id)
            radio.connect("toggled", self._target_toggled, cand)
            status = cand.status.replace("_", " ").title()
            kind = "success" if cand.status == "recommended" else "warning" if cand.selectable else "error"
            row = self._row_card(cand.title, self._candidate_subtitle(cand), "swap-target", status, kind,
                                 prefix_widget=radio, disabled=not cand.selectable)
            click = Gtk.GestureClick()
            click.connect("released", lambda _g, _n, _x, _y, b=radio, c=cand: b.set_active(True) if c.selectable else None)
            row.add_controller(click)
            self._target_group.append(row)

    def _candidate_subtitle(self, cand: SwapTarget) -> str:
        parts = [cand.detail]
        if cand.uuid:
            parts.append(f"UUID {cand.uuid}")
        if cand.resume_offset:
            parts.append(f"resume_offset {cand.resume_offset}")
        parts.extend(cand.warnings)
        parts.extend(cand.reasons)
        return " — ".join(p for p in parts if p)

    def _target_toggled(self, button: Gtk.CheckButton, cand: SwapTarget) -> None:
        if button.get_active() and cand.selectable:
            self.selected_target = cand
            self.swap_file_request = None
            if hasattr(self, "_swapfile_toggle"):
                self._swapfile_toggle.set_active(False)
            if hasattr(self, "_config_next_btn"):
                self._config_next_btn.set_sensitive(self._config_can_continue())

    def _default_swapfile_size_bytes(self) -> int:
        if self._swapfile_size_bytes:
            return self._swapfile_size_bytes
        ram = self.profile.ram_bytes if self.profile else 8 * GIB
        self._swapfile_size_bytes = suggested_swap_sizes(ram)[1][1]
        return self._swapfile_size_bytes

    def _swapfile_controls_card(self) -> Gtk.Box:
        card = self._card("Managed swap file", "Create or resize /swap.img using a RAM-marked slider, presets, or manual GiB input. The actual UUID and resume_offset are detected after creation.", "swap-file")
        toggle = Gtk.CheckButton(label="Create or resize managed /swap.img and use it for hibernation")
        toggle.set_name("toggle_managed_swapfile")
        toggle.set_active(self.swap_file_request is not None)
        self._swapfile_toggle = toggle
        card.append(toggle)

        current = self._default_swapfile_size_bytes() // GIB
        max_gib = max(16, int((self.profile.ram_bytes if self.profile else 8 * GIB) / GIB * 2), 64)
        max_gib = min(max_gib, 128)
        adjustment = Gtk.Adjustment(value=current, lower=1, upper=max_gib, step_increment=1, page_increment=4)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale.set_name("swapfile_size_slider")
        scale.set_digits(0)
        scale.set_hexpand(True)
        for mark_label, mark_gib in swapfile_slider_marks(self.profile.ram_bytes if self.profile else 8 * GIB):
            if 1 <= mark_gib <= max_gib:
                mark_position = Gtk.PositionType.TOP if mark_label == "Recommended" else Gtk.PositionType.BOTTOM
                scale.add_mark(mark_gib, mark_position, f"{mark_label}\n{mark_gib} GiB")
        self._swapfile_scale = scale
        card.append(self._label("Swap file size slider (GiB): Recommended is shown above the slider; Minimum and 2× RAM are below.", css="caption"))
        card.append(scale)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._swapfile_preset_buttons = []
        for label, size in suggested_swap_sizes(self.profile.ram_bytes if self.profile else 8 * GIB):
            button = Gtk.Button(label=f"{label}: {int(size / GIB)} GiB")
            button.set_name("btn_swapfile_preset_" + label.lower().replace(" ", "_").replace("+", "plus").replace("×", "x"))
            button.connect("clicked", self._swapfile_preset_clicked, size)
            self._swapfile_preset_buttons.append(button)
            preset_row.append(button)
        card.append(preset_row)

        manual_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        manual_row.append(self._label("Manual size (GiB)", css="caption"))
        spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=0)
        spin.set_name("swapfile_size_manual_input")
        self._swapfile_spin = spin
        manual_row.append(spin)
        card.append(manual_row)

        self._swapfile_status = self._label("", css="dim-label")
        card.append(self._swapfile_status)

        toggle.connect("toggled", self._swapfile_toggle_changed)
        adjustment.connect("value-changed", self._swapfile_size_changed)
        self._update_swapfile_status()
        return card

    def _swapfile_preset_clicked(self, _button: Gtk.Button, size_bytes: int) -> None:
        if hasattr(self, "_swapfile_scale"):
            self._swapfile_scale.get_adjustment().set_value(max(1, int(round(size_bytes / GIB))))
        if hasattr(self, "_swapfile_toggle"):
            self._swapfile_toggle.set_active(True)
        self._set_swapfile_request(size_bytes)

    def _swapfile_toggle_changed(self, button: Gtk.CheckButton) -> None:
        if button.get_active():
            self.selected_target = None
            self._set_swapfile_request(self._default_swapfile_size_bytes())
        else:
            self.swap_file_request = None
            self._update_swapfile_status()
        if hasattr(self, "_config_next_btn"):
            self._config_next_btn.set_sensitive(self._config_can_continue())

    def _swapfile_size_changed(self, adjustment: Gtk.Adjustment) -> None:
        size_bytes = int(round(adjustment.get_value())) * GIB
        self._swapfile_size_bytes = size_bytes
        if hasattr(self, "_swapfile_toggle") and self._swapfile_toggle.get_active():
            self._set_swapfile_request(size_bytes)
        else:
            self._update_swapfile_status()

    def _set_swapfile_request(self, size_bytes: int) -> None:
        self._swapfile_size_bytes = size_bytes
        self.swap_file_request = SwapFileRequest(DEFAULT_SWAPFILE_PATH, size_bytes)
        if hasattr(self, "_swapfile_toggle") and not self._swapfile_toggle.get_active():
            self._swapfile_toggle.set_active(True)
        self._update_swapfile_status()
        if hasattr(self, "_config_next_btn"):
            self._config_next_btn.set_sensitive(self._config_can_continue())

    def _update_swapfile_status(self) -> None:
        if not hasattr(self, "_swapfile_status"):
            return
        size_gib = int(round(self._default_swapfile_size_bytes() / GIB))
        if self.swap_file_request is not None:
            self._swapfile_status.set_label(f"Selected: create or resize /swap.img to {size_gib} GiB. This will be shown in Planned Modifications before Apply.")
        else:
            self._swapfile_status.set_label(f"Not selected. Current prepared size value: {size_gib} GiB.")

    def _config_can_continue(self) -> bool:
        return self.swap_file_request is not None or (self.selected_target is not None and self.selected_target.selectable)

    def _config_selection(self):
        return self.swap_file_request if self.swap_file_request is not None else self.selected_target

    def _go_plan(self) -> None:
        self._step_state["config"] = "passed"
        self._show_page("plan")

    def _plan_page(self) -> Gtk.Widget:
        box = self._content_box()
        plan_summary = self._card(
            "Planned Modifications",
            "Compact review of current state, safety, and exact planned changes before Apply.",
            "planned-modifications",
        )
        plan_summary.set_name("plan_summary")
        box.append(plan_summary)

        status = self._card("Status summary", "Current target and boot configuration in one view.", "themed:computer-symbolic")
        status.set_name("plan_status_summary")
        self._plan_status_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status.append(self._plan_status_group)
        box.append(status)

        changes = self._card("Planned changes", "Short helper action list. Full details are collapsed below.", "review-apply")
        changes.set_name("plan_changes_compact")
        self._plan_changes_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        changes.append(self._plan_changes_group)
        box.append(changes)

        details = Gtk.Expander(label="Technical details")
        details.set_name("plan_technical_details")
        details.set_margin_top(2)
        details.set_expanded(False)
        self._plan_details_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        self._plan_details_group.add_css_class("uhw-card")
        details.set_child(self._plan_details_group)
        box.append(details)

        self._render_plan()
        back_btn = Gtk.Button(label="Back to Configuration")
        back_btn.set_name("btn_back_config")
        back_btn.connect("clicked", lambda *_: self._show_page("config"))
        next_btn = Gtk.Button(label="Continue to Review & Apply")
        next_btn.add_css_class("suggested-action")
        next_btn.set_sensitive(self.plan is not None and self.plan.can_apply)
        next_btn.connect("clicked", lambda *_: self._show_page("apply"))
        box.append(self._button_row(back_btn, next_btn))
        return self._scrolled(box)

    def _clear_box(self, box: Gtk.Box) -> None:
        for child in list(box):
            box.remove(child)

    def _compact_status_table(self, items: list[tuple[str, str]], *, pairs_per_row: int = 2) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, hexpand=True)
        grid.set_name("compact_status_table")
        grid.add_css_class("uhw-status-table")

        for pair_idx in range(pairs_per_row):
            key_head = Gtk.Label(label="Field", xalign=0)
            key_head.add_css_class("caption")
            key_head.add_css_class("dim-label")
            value_head = Gtk.Label(label="Value", xalign=0)
            value_head.add_css_class("caption")
            value_head.add_css_class("dim-label")
            col = pair_idx * 2
            grid.attach(key_head, col, 0, 1, 1)
            grid.attach(value_head, col + 1, 0, 1, 1)

        for idx, (key, value) in enumerate(items):
            pair = idx % pairs_per_row
            row = (idx // pairs_per_row) + 1
            col = pair * 2

            key_label = Gtk.Label(label=key, xalign=0)
            key_label.add_css_class("dim-label")
            key_label.set_hexpand(False)
            key_label.set_valign(Gtk.Align.START)

            value_label = Gtk.Label(label=value, xalign=0, wrap=True, selectable=True)
            value_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            value_label.add_css_class("uhw-row-title")
            value_label.set_hexpand(True)
            value_label.set_valign(Gtk.Align.START)

            grid.attach(key_label, col, row, 1, 1)
            grid.attach(value_label, col + 1, row, 1, 1)
        return grid

    def _plan_status_text(self) -> tuple[str, str]:
        if self.plan is None:
            return "Not ready", "neutral"
        if self.plan.blocking_reasons:
            return "Blocked", "error"
        if self.plan.warnings:
            return "Warnings", "warning"
        return "Ready", "success"

    def _plan_status_items(self) -> list[tuple[str, str]]:
        profile = self.detect_info.profile if self.detect_info and self.detect_info.profile else None
        target = self.plan.selected_target if self.plan is not None else self.selected_target
        selection = self._config_selection()
        items: list[tuple[str, str]] = []

        if isinstance(selection, SwapFileRequest) or (self.plan is not None and self.plan.swap_file_request is not None):
            request = self.plan.swap_file_request if self.plan is not None and self.plan.swap_file_request else selection
            items.extend([
                ("Operation", f"Create/resize {request.path}"),
                ("Requested swap", format_bytes_gib(request.size_bytes)),
                ("Type", "managed swap file"),
                ("Resume UUID", "detect after creation"),
                ("Resume offset", "detect after creation"),
            ])
        elif target is not None:
            items.extend([
                ("Target", target.path),
                ("Swap", format_bytes_gib(target.size_bytes)),
                ("Type", target.kind),
                ("Filesystem", target.filesystem or "unknown"),
                ("Resume UUID", "known" if target.uuid else "missing"),
            ])
            if target.kind == "file":
                items.append(("Resume offset", "known" if target.resume_offset is not None else "missing"))
        else:
            items.append(("Target", "not selected"))

        if profile is not None:
            items.extend([
                ("RAM", format_bytes_gib(profile.ram_bytes)),
                ("Boot", profile.bootloader or "unknown"),
                ("Initramfs", profile.initramfs or "unknown"),
                ("Secure Boot", profile.secure_boot or "unknown"),
            ])
        status, _kind = self._plan_status_text()
        items.insert(0, ("Status", status))
        return items

    def _plan_add_status_summary(self) -> None:
        self._plan_status_group.append(self._compact_status_table(self._plan_status_items(), pairs_per_row=2))

    def _plan_step_badge(self, step) -> tuple[str, str]:
        if step.id == "create_rollback":
            return "Backup", "success"
        if step.id == "validate_target":
            return "Check", "success"
        if step.id.startswith("update_"):
            return "Command", "warning"
        if step.id == "ensure_swap_file":
            return "Disk", "warning"
        if step.id.startswith("write_"):
            return "Write", "warning"
        return "Step", "neutral"

    def _compact_planned_changes_table(self) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=12, row_spacing=5, hexpand=True)
        grid.set_name("compact_planned_changes_table")
        grid.add_css_class("uhw-status-table")

        headers = ["#", "Action", "Type"]
        for col, header in enumerate(headers):
            label = Gtk.Label(label=header, xalign=0)
            label.add_css_class("caption")
            label.add_css_class("dim-label")
            grid.attach(label, col, 0, 1, 1)

        if self.plan is None:
            grid.attach(self._label("—", css="dim-label"), 0, 1, 1, 1)
            grid.attach(self._label("No plan available.", css="dim-label"), 1, 1, 1, 1)
            grid.attach(self._status_pill("Missing", "warning"), 2, 1, 1, 1)
            return grid

        for idx, step in enumerate(self.plan.steps, start=1):
            number = Gtk.Label(label=str(idx), xalign=0)
            number.add_css_class("dim-label")
            number.set_valign(Gtk.Align.START)

            title = step.title
            if len(title) > 78:
                title = title[:75].rstrip() + "..."
            action = Gtk.Label(label=title, xalign=0, wrap=True)
            action.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            action.add_css_class("uhw-row-title")
            action.set_valign(Gtk.Align.START)
            action.set_hexpand(True)

            status, kind = self._plan_step_badge(step)
            badge = self._status_pill(status, kind)
            badge.set_valign(Gtk.Align.START)

            grid.attach(number, 0, idx, 1, 1)
            grid.attach(action, 1, idx, 1, 1)
            grid.attach(badge, 2, idx, 1, 1)
        return grid

    def _plan_add_short_changes(self) -> None:
        self._plan_changes_group.append(self._compact_planned_changes_table())

    def _plan_step_change_impact(self, step) -> str:
        if step.id == "create_rollback":
            return "Creates rollback metadata and file backups before any managed system file is changed."
        if step.id == "ensure_swap_file":
            return "Creates or resizes the managed swap file, activates it, and ensures the required fstab entry."
        if step.id == "validate_target":
            return "Re-probes the live swap target, UUID, and resume offset immediately before writes; apply aborts if validation fails."
        if step.id == "write_resume_config":
            return f"Writes {RESUME_FILE}; this is the initramfs resume source used during early boot."
        if step.id == "write_grub_config":
            return f"Writes {GRUB_FRAGMENT}; adds managed resume kernel parameters without directly rewriting /etc/default/grub."
        if step.id == "update_initramfs":
            return "Runs update-initramfs -u so the generated initramfs contains the selected resume configuration."
        if step.id == "update_grub":
            return "Runs update-grub so GRUB boot entries include the managed resume kernel parameters."
        return step.detail or "Helper step included in the generated apply request."

    def _plan_file_change_detail(self, path: str) -> str:
        if path == RESUME_FILE:
            return "Initramfs resume configuration. Expected content uses RESUME=UUID=... and resume_offset=... for swap files."
        if path == GRUB_FRAGMENT:
            return "Managed GRUB defaults fragment. It adds resume=UUID=... and resume_offset=... while preserving the main GRUB defaults file."
        if path == "/etc/fstab":
            return "Only touched for managed swap-file create/resize so the selected swap file remains available after reboot."
        return "Managed file listed in the helper request."

    def _plan_generated_config_preview(self) -> str:
        if self.plan is None:
            return "No plan."
        if self.plan.swap_file_request is not None:
            return (
                "Resume config preview is generated after live swap-file creation because UUID and resume_offset "
                "are only trusted after the helper re-probes the active file."
            )
        target = self.plan.selected_target
        if not target.uuid:
            return "Resume config preview unavailable because the selected target has no UUID."
        lines = [f"RESUME=UUID={target.uuid}"]
        if target.kind == "file":
            if target.resume_offset is None:
                lines.append("resume_offset=<missing>")
            else:
                lines.append(f"resume_offset={target.resume_offset}")
        grub_params = [f"resume=UUID={target.uuid}"]
        if target.kind == "file" and target.resume_offset is not None:
            grub_params.append(f"resume_offset={target.resume_offset}")
        return (
            "Resume file preview:\n"
            + " ".join(lines)
            + "\n\nGRUB kernel parameters preview:\n"
            + " ".join(grub_params)
        )

    def _plan_change_impact_table(self) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, hexpand=True)
        grid.set_name("technical_change_impact_table")
        grid.add_css_class("uhw-status-table")
        headers = ["#", "Step ID", "Type", "Technical impact"]
        for col, header in enumerate(headers):
            label = Gtk.Label(label=header, xalign=0)
            label.add_css_class("caption")
            label.add_css_class("dim-label")
            grid.attach(label, col, 0, 1, 1)
        if self.plan is None:
            return grid
        for idx, step in enumerate(self.plan.steps, start=1):
            number = Gtk.Label(label=str(idx), xalign=0)
            number.add_css_class("dim-label")
            step_id = Gtk.Label(label=step.id, xalign=0, selectable=True)
            step_id.add_css_class("dim-label")
            step_type, step_kind = self._plan_step_badge(step)
            badge = self._status_pill(step_type, step_kind)
            impact = Gtk.Label(label=self._plan_step_change_impact(step), xalign=0, wrap=True, selectable=True)
            impact.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            impact.set_hexpand(True)
            impact.set_valign(Gtk.Align.START)
            grid.attach(number, 0, idx, 1, 1)
            grid.attach(step_id, 1, idx, 1, 1)
            grid.attach(badge, 2, idx, 1, 1)
            grid.attach(impact, 3, idx, 1, 1)
        return grid

    def _plan_add_technical_details(self) -> None:
        if self.plan is None:
            self._plan_details_group.append(self._row_card("Plan unavailable", "No technical details are available.", "warning"))
            return

        target_detail = self._format_plan_target_detail()
        self._plan_details_group.append(self._row_card("Selected target details", target_detail, "swap-target", "Review"))

        if self.plan.blocking_reasons:
            for reason in self.plan.blocking_reasons:
                self._plan_details_group.append(self._row_card("Blocking reason", reason, "error", "Blocked", "error"))
        if self.plan.warnings:
            for warning in self.plan.warnings:
                self._plan_details_group.append(self._row_card("Warning", warning, "warning", "Review", "warning"))

        self._plan_details_group.append(self._row_card("Generated configuration preview", self._plan_generated_config_preview(), "config-file", "Preview"))
        self._plan_details_group.append(self._row_card("Change impact details", "Each helper step, internal step ID, change type, and technical effect.", "review-apply", "Expanded"))
        self._plan_details_group.append(self._plan_change_impact_table())

        for idx, step in enumerate(self.plan.steps, start=1):
            icon = "warning" if step.destructive else "arrow-right"
            detail = step.detail or self._plan_step_change_impact(step)
            self._plan_details_group.append(self._row_card(f"{idx}. {step.title}", f"Step ID: {step.id}\n{detail}", icon))

        if self.plan.planned_files:
            for path in self.plan.planned_files:
                self._plan_details_group.append(self._row_card("Managed file", f"{path}\n{self._plan_file_change_detail(path)}", "config-file", "May change", "warning"))
        self._plan_details_group.append(self._row_card("Rollback scope", "Backs up managed files before writes and records a manifest for rollback.", "rollback-snapshot", "Before writes", "success"))
        self._plan_details_group.append(self._row_card("Rollback backup location", "/var/backups/ubuntu-hibernate-wizard/<backup_id>/manifest.json", "rollback-snapshot", "Before writes", "success"))

    def _render_plan(self) -> None:
        for group_name in ("_plan_status_group", "_plan_changes_group", "_plan_details_group"):
            group = getattr(self, group_name, None)
            if group is not None:
                self._clear_box(group)
        try:
            self.plan = self.controller.build_plan(self._config_selection())
        except Exception as exc:  # noqa: BLE001
            if hasattr(self, "_plan_details_group"):
                self._plan_details_group.append(self._row_card("Could not build plan", str(exc), "error", "Failed", "error"))
            self._step_state["plan"] = "error"
            return
        if self.plan.blocking_reasons:
            self._step_state["plan"] = "error"
        self._plan_add_status_summary()
        self._plan_add_short_changes()
        self._plan_add_technical_details()

    def _format_plan_target_detail(self) -> str:
        target = self.plan.selected_target if self.plan is not None else self.selected_target
        selection = self._config_selection()
        if isinstance(selection, SwapFileRequest):
            return (
                f"Managed swap file: {selection.path}\n"
                f"Requested size: {format_bytes_gib(selection.size_bytes)}\n"
                "Mode: create or resize before final live validation"
            )
        if target is None:
            return "No target selected yet."
        parts = [
            f"Target: {target.title or target.path}",
            f"Path: {target.path}",
            f"Type: {target.kind}",
            f"Size: {format_bytes_gib(target.size_bytes)}",
            f"Status: {target.status}",
        ]
        if target.filesystem:
            parts.append(f"Filesystem: {target.filesystem}")
        if target.uuid:
            parts.append(f"Resume UUID: {target.uuid}")
        if target.resume_offset:
            parts.append(f"Resume offset: {target.resume_offset}")
        return "\n".join(parts)

    def _append_apply_review(self, box: Gtk.Box) -> None:
        if self.plan is None:
            try:
                self.plan = self.controller.build_plan(self._config_selection())
            except Exception as exc:  # noqa: BLE001
                card = self._card("Review unavailable", "The plan could not be regenerated for review.", "error")
                card.append(self._row_card("Plan error", str(exc), "error", "Blocked", "error"))
                box.append(card)
                return

        plan_card = self._card(
            "Review planned changes",
            "Plain numbered summary of the helper actions before live Apply starts.",
            "planned-modifications",
        )
        plan_card.set_name("apply_review_plan")
        lines: list[str] = []
        for idx, step in enumerate(self.plan.steps, start=1):
            detail = f" — {step.detail}" if step.detail else ""
            lines.append(f"{idx}. {step.title}{detail}")

        if self.plan.blocking_reasons:
            lines.append("")
            lines.append("Blocking reasons:")
            for reason in self.plan.blocking_reasons:
                lines.append(f"- {reason}")
        if self.plan.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.plan.warnings:
                lines.append(f"- {warning}")
        if self.plan.planned_files:
            lines.append("")
            lines.append("Managed files:")
            for path in self.plan.planned_files:
                lines.append(f"- {path}")

        review_text = "\n".join(lines) if lines else "No planned helper actions."
        plan_card.append(self._label(review_text, monospace=True))
        box.append(plan_card)

    def _apply_page(self) -> Gtk.Widget:
        box = self._content_box()
        box.append(self._card("Review & Apply", "Review the target and exact planned changes before starting the privileged helper.", "review-apply"))
        self._append_apply_review(box)
        self._confirm = Gtk.CheckButton(label="I reviewed the selected target and planned managed files")
        dry = Gtk.CheckButton(label="Dry-run only: simulate apply without changing system files")
        dry.set_active(getattr(self.controller, "dry_run", False) or getattr(self.controller, "fake_system", None) is not None)
        self._dry_apply = dry
        box.append(self._confirm)
        box.append(dry)
        self._progress = Gtk.ProgressBar(show_text=True, text="Waiting")
        box.append(self._progress)
        self._log_buffer = Gtk.TextBuffer()
        log = Gtk.TextView(buffer=self._log_buffer, editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(child=log, min_content_height=280, vexpand=True)
        box.append(scroll)
        apply_btn = Gtk.Button(label="Apply Plan")
        apply_btn.set_name("btn_apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_sensitive(False)
        self._apply_button = apply_btn
        self._confirm.connect("toggled", lambda b: apply_btn.set_sensitive(b.get_active() and self.plan is not None and self.plan.can_apply))
        apply_btn.connect("clicked", self._start_apply)
        finish_btn = Gtk.Button(label="Continue to Finish")
        finish_btn.set_name("btn_continue_finish")
        finish_btn.set_sensitive(False)
        finish_btn.connect("clicked", lambda *_: self._show_page("finish"))
        self._apply_finish_button = finish_btn
        back_btn = Gtk.Button(label="Back to Planned Modifications")
        back_btn.set_name("btn_back_plan")
        back_btn.connect("clicked", lambda *_: self._show_page("plan"))
        box.append(self._button_row(back_btn, apply_btn, finish_btn))
        return self._scrolled(box)

    def _start_apply(self, *_args) -> None:
        if self._apply_running:
            return
        self._apply_running = True
        self._apply_button.set_sensitive(False)
        if hasattr(self, "_apply_finish_button"):
            self._apply_finish_button.set_sensitive(False)
        self._append_log("Apply started")
        threading.Thread(target=self._apply_worker, daemon=True).start()

    def _apply_worker(self) -> None:
        def progress(pct, line):
            GLib.idle_add(self._apply_progress, pct, line)
        try:
            ok, msg = self.controller.apply(self._config_selection(), progress, dry_run=self._dry_apply.get_active())
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        GLib.idle_add(self._apply_done, ok, msg)

    def _apply_progress(self, pct, line) -> bool:
        try:
            frac = max(0.0, min(1.0, float(pct) / 100.0))
            self._progress.set_fraction(frac)
            self._progress.set_text(f"{int(frac * 100)}%")
        except Exception:  # noqa: BLE001
            pass
        self._append_log(str(line))
        return False

    def _append_log(self, line: str) -> None:
        if not self._log_buffer:
            return
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        end = self._log_buffer.get_end_iter()
        self._log_buffer.insert(end, f"[{ts}] {line}\n")

    def _get_apply_log_text(self) -> str:
        if not self._log_buffer:
            return "No apply log was captured in this session.\n"
        start = self._log_buffer.get_start_iter()
        end = self._log_buffer.get_end_iter()
        text = self._log_buffer.get_text(start, end, False)
        return text if text.strip() else "No apply log was captured in this session.\n"

    def _default_log_export_path(self) -> Path:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = Path.home() / "Documents"
        if not base.exists():
            base = Path.home()
        return base / f"ubuntu-hibernate-wizard-apply-log-{stamp}.txt"

    def _export_apply_log(self, *_args) -> None:
        try:
            path = self._default_log_export_path()
            path.write_text(self._get_apply_log_text(), encoding="utf-8")
            message = f"Apply log exported to {path}"
            if hasattr(self, "_finish_export_status"):
                self._finish_export_status.set_label(message)
            self._append_log(message)
        except Exception as exc:  # noqa: BLE001
            message = f"Failed to export apply log: {exc}"
            if hasattr(self, "_finish_export_status"):
                self._finish_export_status.set_label(message)
            self._append_log(message)

    def _clear_finish_verify_log(self) -> None:
        if hasattr(self, "_finish_verify_log_buffer") and self._finish_verify_log_buffer is not None:
            self._finish_verify_log_buffer.set_text("")

    def _append_finish_verify_log(self, line: str) -> bool:
        if not hasattr(self, "_finish_verify_log_buffer") or self._finish_verify_log_buffer is None:
            return False
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        end = self._finish_verify_log_buffer.get_end_iter()
        self._finish_verify_log_buffer.insert(end, f"[{ts}] {line}\n")
        return False

    def _start_post_restart_verify(self, *_args) -> None:
        if hasattr(self, "_finish_verify_status"):
            self._finish_verify_status.set_label("Running read-only verification...")
        self._clear_finish_verify_log()
        self._append_finish_verify_log("Starting post-restart verification.")
        self._append_finish_verify_log("Mode: read-only. No system files will be changed.")
        self._append_finish_verify_log("Checking active swap target, resume UUID, resume offset, GRUB and initramfs state...")
        if hasattr(self, "_finish_verify_button"):
            self._finish_verify_button.set_sensitive(False)
        threading.Thread(target=self._post_restart_verify_worker, daemon=True).start()

    def _post_restart_verify_worker(self) -> None:
        GLib.idle_add(self._append_finish_verify_log, "Reading current system state...")
        try:
            info = self.controller.detect()
            err = None
            GLib.idle_add(self._append_finish_verify_log, "System probe completed.")
        except Exception as exc:  # noqa: BLE001
            info, err = None, str(exc)
            GLib.idle_add(self._append_finish_verify_log, f"System probe failed: {err}")
        GLib.idle_add(self._post_restart_verify_done, info, err)

    def _post_restart_verify_done(self, info, err) -> bool:
        if hasattr(self, "_finish_verify_button"):
            self._finish_verify_button.set_sensitive(True)
        if err or info is None:
            message = f"Verification failed: {err or 'unknown error'}"
            self._append_finish_verify_log(message)
        else:
            self._append_finish_verify_log("Detailed check results:")
            for title, detail, cls, status in info.rows:
                icon = "OK" if cls == "success" else "WARNING" if cls == "warning" else "BLOCKED"
                self._append_finish_verify_log(f"{icon}: {title} [{status}] — {detail}")
            if info.hard_stop:
                blockers = []
                if info.profile is not None:
                    blockers = list(info.profile.blocking_reasons)
                message = "Verification blocked: " + ("; ".join(blockers) if blockers else "system check reported a blocker")
            elif any(row[2] == "warning" for row in info.rows):
                message = "Verification completed with warnings. Review System Check details if hibernation does not resume."
            else:
                message = "Verification passed: hibernation configuration looks ready after restart."
            self._append_finish_verify_log(message)
        if hasattr(self, "_finish_verify_status"):
            self._finish_verify_status.set_label(message)
        self._append_log(message)
        return False

    def _apply_done(self, ok: bool, msg: str) -> bool:
        self._apply_running = False
        self._append_log(msg)
        self._progress.set_fraction(1.0)
        self._progress.set_text("Completed" if ok else "Failed")
        self._step_state["apply"] = "passed" if ok else "error"
        self._refresh_sidebar()
        if ok:
            self._append_log("Review the live log above. Continue to Finish when you are ready.")
            if hasattr(self, "_apply_finish_button"):
                self._apply_finish_button.set_sensitive(True)
        else:
            self._apply_button.set_sensitive(True)
            if hasattr(self, "_apply_finish_button"):
                self._apply_finish_button.set_sensitive(False)
        return False

    def _finish_page(self) -> Gtk.Widget:
        box = self._content_box()
        done = self._card("Finish", "Reboot manually from the system menu, then test hibernation. The app never calls reboot automatically.", "success-check")
        done.append(self._label("After reboot, run the wizard again or use the verification section below to confirm resume configuration."))
        box.append(done)

        verify_card = self._card("Verification after restart", "After rebooting, open this wizard again and run this read-only verification before testing hibernation.", "magnifier")
        for text in [
            "Reboot manually from the system menu.",
            "Open Ubuntu Hibernate Wizard again after the desktop returns.",
            "Press Run verification after restart to check active swap, resume UUID, resume offset, GRUB, and initramfs configuration.",
            "Only test hibernation after this verification is passed or the warnings are understood.",
        ]:
            verify_card.append(self._plain_row(text, "success-check"))
        self._finish_verify_status = self._label("Verification has not been run in this session.", css="dim-label")
        verify_card.append(self._finish_verify_status)
        self._finish_verify_log_buffer = Gtk.TextBuffer()
        self._finish_verify_log_buffer.set_text("Press Run verification after restart to see live read-only checks here.\n")
        verify_log = Gtk.TextView(
            buffer=self._finish_verify_log_buffer,
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
        )
        verify_log.set_name("verification_live_log")
        verify_log_scroll = Gtk.ScrolledWindow(child=verify_log, min_content_height=190, vexpand=False)
        verify_log_scroll.set_name("verification_live_status_window")
        verify_card.append(verify_log_scroll)
        box.append(verify_card)

        ext = self._card("Optional GNOME power-menu buttons", "Install after hibernation works. These links are optional and do not affect the wizard apply path.", "desktop-return")
        link1 = Gtk.LinkButton.new_with_label(HIBERNATE_STATUS_EXTENSION_URL, "Open Extension")
        ext.append(self._row_card(
            "Hibernate Status Button",
            "Adds Hibernate and Hybrid Sleep actions to the GNOME status menu.",
            "desktop-return", suffix_widget=link1))
        link2 = Gtk.LinkButton.new_with_label(SYSTEM_ACTION_HIBERNATE_EXTENSION_URL, "Open Extension")
        ext.append(self._row_card(
            "System Action - Hibernate",
            "Adds Hibernate among GNOME system actions.",
            "hibernate-power", suffix_widget=link2))
        box.append(ext)

        export_card = self._card("Export log", "Save the live Apply log from this session as a text file for your records or GitHub issue reports.", "save-plan")
        export_log_btn = Gtk.Button(label="Export log")
        export_log_btn.set_name("btn_export_log")
        export_log_btn.connect("clicked", self._export_apply_log)
        self._finish_export_status = self._label("No log file exported yet.", css="dim-label")
        export_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        export_row.set_hexpand(True)
        export_row.append(self._finish_export_status)
        export_row.append(export_log_btn)
        export_card.append(export_row)
        box.append(export_card)

        verify_btn = Gtk.Button(label="Run verification after restart")
        verify_btn.set_name("btn_verify")
        verify_btn.connect("clicked", self._start_post_restart_verify)
        self._finish_verify_button = verify_btn
        rollback_btn = Gtk.Button(label="Rollback is available from CLI")
        rollback_btn.set_name("btn_rollback")
        rollback_btn.set_sensitive(False)
        box.append(self._button_row(verify_btn, rollback_btn))
        return self._scrolled(box)

    def _help_page(self) -> Gtk.Widget:
        box = self._content_box()
        card = self._card("Help", "Common blocked states and what to do next.", "help")
        for text in [
            "zram-only systems need a real disk swap target before hibernation can work.",
            "Swap smaller than RAM is shown but Apply is blocked in v0.42.",
            "Non-GRUB or non-initramfs-tools systems are out of scope for this release.",
            "Swap-file offset must be detected by filefrag on ext4 or btrfs map-swapfile on btrfs.",
            "Gate E real Apply must be tested only inside a disposable Ubuntu VM, then Gate F must validate the manual hibernate/resume evidence.",
        ]:
            card.append(self._plain_row(text))
        box.append(card)

        flow = self._card("Troubleshooting flow", "Use fake-system and dry-run first, then VM validation.", "info-note")
        for title, detail, icon in [
            ("Fake-system", "Render and test pages using fixture data without touching the host.", "themed:utilities-system-monitor-symbolic"),
            ("Dry-run", "Build the same plan and progress events without writing files.", "review-apply"),
            ("Validate plan", "Ask the helper to re-probe and reject unsafe or stale plans.", "magnifier"),
            ("Disposable VM apply", "Run real Apply only after acknowledging the Gate E VM guard.", "warning"),
            ("Gate F evidence", "Record manual hibernate/resume result and generate a release-candidate manifest.", "save-plan"),
        ]:
            flow.append(self._row_card(title, detail, icon))
        box.append(flow)
        return self._scrolled(box)

    def _about_page(self) -> Gtk.Widget:
        box = self._content_box()
        card = self._card("About", f"{APP_NAME} {APP_VERSION}", "about")
        card.append(self._label("Native GTK4/libadwaita wizard for safer Ubuntu hibernation configuration."))
        card.append(self._label("Application branding uses the bundled project banner and icon assets included with this package for the welcome screen, app icon, and documentation.", css="dim-label"))
        box.append(card)

        ident = self._card("Application identity", APP_ID, "app-icon")
        ident.append(self._key_value_row("Executable", "ubuntu-hibernate-wizard"))
        ident.append(self._key_value_row("Helper", "/usr/libexec/ubuntu-hibernate-wizard/ubuntu-hibernate-wizard-helper"))
        ident.append(self._key_value_row("Managed files", f"{RESUME_FILE}; {GRUB_FRAGMENT}"))
        box.append(ident)

        links = self._card("Project links", "Documentation, releases, source code, and issue tracker.", "help")
        docs_link = Gtk.LinkButton.new_with_label(
            "https://ami3go.github.io/ubuntu-hibernate-wizard/",
            "Open GitHub Pages documentation",
        )
        repo_link = Gtk.LinkButton.new_with_label(
            "https://github.com/ami3go/ubuntu-hibernate-wizard",
            "Open GitHub repository",
        )
        links.append(self._row_card(
            "GitHub Pages",
            "User guide, installation notes, screenshots, troubleshooting, and project documentation.",
            "help",
            suffix_widget=docs_link,
        ))
        links.append(self._row_card(
            "GitHub repository",
            "Source code, releases, issue tracker, and contribution workflow.",
            "config-file",
            suffix_widget=repo_link,
        ))
        box.append(links)
        return self._scrolled(box)


class WizardApp(Adw.Application):
    def __init__(self, controller) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.controller = controller
        self._register_optional_gresource()

    def _register_optional_gresource(self) -> None:
        resource_path = Path(__file__).resolve().parents[1] / "ubuntu_hibernate_wizard.gresource"
        if not resource_path.exists():
            return
        try:
            Gio.resources_register(Gio.Resource.load(str(resource_path)))
        except Exception:  # noqa: BLE001 - package-data fallback remains available
            pass

    def do_activate(self) -> None:
        win = self.props.active_window or WizardWindow(self, self.controller)
        win.present()
