PKG      := ubuntu-hibernate-wizard
VERSION  := 0.3.2-1
DEST     := dist/pkgroot

.PHONY: test deb clean

test:
	python3 -m pytest tests/ -v

deb: clean
	mkdir -p $(DEST)/DEBIAN \
	  $(DEST)/usr/bin \
	  $(DEST)/usr/libexec/$(PKG) \
	  $(DEST)/usr/lib/python3/dist-packages \
	  $(DEST)/usr/lib/systemd/system \
	  $(DEST)/etc/xdg/autostart \
	  $(DEST)/usr/share/applications \
	  $(DEST)/usr/share/polkit-1/actions \
	  $(DEST)/usr/share/icons/hicolor/scalable/apps \
	  $(DEST)/usr/share/doc/$(PKG)
	cp -r ubuntu_hibernate_wizard $(DEST)/usr/lib/python3/dist-packages/
	find $(DEST) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	install -m 755 packaging/launcher $(DEST)/usr/bin/$(PKG)
	install -m 755 ubuntu_hibernate_wizard/backend/privileged_helper.py \
	  $(DEST)/usr/libexec/$(PKG)/privileged-helper
	install -m 644 data/io.github.example.UbuntuHibernateWizard.desktop $(DEST)/usr/share/applications/
	install -m 644 data/io.github.example.UbuntuHibernateWizard.policy $(DEST)/usr/share/polkit-1/actions/
	install -m 644 data/icons/io.github.example.UbuntuHibernateWizard.svg \
	  $(DEST)/usr/share/icons/hicolor/scalable/apps/
	install -m 644 data/ubuntu-hibernate-guard.service data/ubuntu-hibernate-guard.timer \
	  $(DEST)/usr/lib/systemd/system/
	install -m 644 data/ubuntu-hibernate-guard-notify.desktop $(DEST)/etc/xdg/autostart/
	sed "s/@VERSION@/$(VERSION)/" packaging/control.in > $(DEST)/DEBIAN/control
	install -m 755 packaging/postinst packaging/postrm $(DEST)/DEBIAN/
	install -m 644 packaging/conffiles $(DEST)/DEBIAN/conffiles
	gzip -9 -n -c packaging/changelog.Debian > $(DEST)/usr/share/doc/$(PKG)/changelog.gz
	install -m 644 packaging/copyright $(DEST)/usr/share/doc/$(PKG)/copyright
	dpkg-deb --build --root-owner-group $(DEST) dist/$(PKG)_$(VERSION)_all.deb
	@echo "Built dist/$(PKG)_$(VERSION)_all.deb"

clean:
	rm -rf dist
