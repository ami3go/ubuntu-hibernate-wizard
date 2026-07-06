PKG      := ubuntu-hibernate-wizard
VERSION  := 0.4.3~rc1-1
DEST     := dist/pkgroot

.PHONY: test resources deb clean

test:
	python3 -m pytest tests/ -v

resources:
	@if command -v glib-compile-resources >/dev/null 2>&1; then \
	  (cd ubuntu_hibernate_wizard/ui && glib-compile-resources --target=../ubuntu_hibernate_wizard.gresource resources.gresource.xml); \
	  echo "Built ubuntu_hibernate_wizard/ubuntu_hibernate_wizard.gresource"; \
	else \
	  echo "glib-compile-resources not installed; using package-data SVG/CSS fallback"; \
	fi

deb: clean resources
	mkdir -p $(DEST)/DEBIAN \
	  $(DEST)/usr/bin \
	  $(DEST)/usr/libexec/$(PKG) \
	  $(DEST)/usr/lib/python3/dist-packages \
	  $(DEST)/usr/lib/systemd/system \
	  $(DEST)/etc/xdg/autostart \
	  $(DEST)/usr/share/applications \
	  $(DEST)/usr/share/metainfo \
	  $(DEST)/usr/share/polkit-1/actions \
	  $(DEST)/usr/share/icons/hicolor/scalable/apps \
  $(DEST)/usr/share/icons/hicolor/512x512/apps \
	  $(DEST)/usr/share/doc/$(PKG) \
	  $(DEST)/usr/share/doc/$(PKG)/examples
	cp -r ubuntu_hibernate_wizard $(DEST)/usr/lib/python3/dist-packages/
	find $(DEST) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	install -m 755 packaging/launcher $(DEST)/usr/bin/$(PKG)
	install -m 755 ubuntu_hibernate_wizard/backend/privileged_helper.py \
	  $(DEST)/usr/libexec/$(PKG)/ubuntu-hibernate-wizard-helper
	install -m 644 data/io.github.ami3go.UbuntuHibernateWizard.desktop $(DEST)/usr/share/applications/
	install -m 644 data/io.github.ami3go.UbuntuHibernateWizard.metainfo.xml $(DEST)/usr/share/metainfo/
	install -m 644 data/io.github.ami3go.UbuntuHibernateWizard.policy $(DEST)/usr/share/polkit-1/actions/
	install -m 644 data/icons/io.github.ami3go.UbuntuHibernateWizard.svg \
	  $(DEST)/usr/share/icons/hicolor/scalable/apps/
	install -m 644 data/icons/io.github.ami3go.UbuntuHibernateWizard.png \
	  $(DEST)/usr/share/icons/hicolor/512x512/apps/
	install -m 644 data/ubuntu-hibernate-guard.service data/ubuntu-hibernate-guard.timer \
	  $(DEST)/usr/lib/systemd/system/
	install -m 644 data/ubuntu-hibernate-guard-notify.desktop $(DEST)/etc/xdg/autostart/
	sed "s/@VERSION@/$(VERSION)/" packaging/control.in > $(DEST)/DEBIAN/control
	install -m 755 packaging/postinst packaging/postrm $(DEST)/DEBIAN/
	install -m 644 packaging/conffiles $(DEST)/DEBIAN/conffiles
	gzip -9 -n -c packaging/changelog.Debian > $(DEST)/usr/share/doc/$(PKG)/changelog.gz
	install -m 644 packaging/copyright $(DEST)/usr/share/doc/$(PKG)/copyright
	install -m 644 docs/gate-e-vm-validation.md $(DEST)/usr/share/doc/$(PKG)/gate-e-vm-validation.md
	install -m 644 docs/gate-f-release-candidate.md $(DEST)/usr/share/doc/$(PKG)/gate-f-release-candidate.md
	install -m 755 tools/gate_e_vm_validate.sh $(DEST)/usr/share/doc/$(PKG)/examples/gate_e_vm_validate.sh
	dpkg-deb --build --root-owner-group $(DEST) dist/$(PKG)_$(VERSION)_all.deb
	@echo "Built dist/$(PKG)_$(VERSION)_all.deb"

clean:
	rm -rf dist
