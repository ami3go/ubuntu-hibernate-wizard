"""Shared application constants for Ubuntu Hibernate Wizard."""

APP_ID = "io.github.ami3go.UbuntuHibernateWizard"
APP_NAME = "Ubuntu Hibernate Wizard"
APP_VERSION = "0.4.3-rc1"
EXECUTABLE_NAME = "ubuntu-hibernate-wizard"
HELPER_EXECUTABLE = "ubuntu-hibernate-wizard-helper"
HELPER_PATH = "/usr/libexec/ubuntu-hibernate-wizard/ubuntu-hibernate-wizard-helper"
POLKIT_ACTION_PREFIX = APP_ID
STATE_DIR = "/var/lib/ubuntu-hibernate-wizard"
LOG_DIR = "/var/log/ubuntu-hibernate-wizard"
USER_RUNTIME_DIR_NAME = "ubuntu-hibernate-wizard"
PROTOCOL_VERSION = 1

RESUME_FILE = "/etc/initramfs-tools/conf.d/resume"
GRUB_FRAGMENT = "/etc/default/grub.d/hibernate-wizard.cfg"
MANAGED_FILES = {RESUME_FILE, GRUB_FRAGMENT}
MANAGED_SECTION_BEGIN = "# BEGIN UBUNTU HIBERNATE WIZARD"
MANAGED_SECTION_END = "# END UBUNTU HIBERNATE WIZARD"
