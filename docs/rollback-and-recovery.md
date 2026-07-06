---
title: Rollback and recovery
description: Understand Ubuntu Hibernate Wizard rollback metadata, managed files, safe restore rules, and conservative recovery behavior.
---

# Rollback and recovery

Ubuntu Hibernate Wizard creates rollback metadata before writing managed files.

Version 0.42.8 writes only:

```text
/etc/initramfs-tools/conf.d/resume
/etc/default/grub.d/hibernate-wizard.cfg
```

Rollback restores or removes wizard-managed files only when the manifest and hashes prove the action is safe. The wizard does not delete pre-existing swap files or partitions.

## Preview rollback

```bash
ubuntu-hibernate-wizard --list-rollbacks
ubuntu-hibernate-wizard --preview-rollback 20260705-180000-a1b2c3
```

## Conservative behavior

Rollback skips a file when:

- the file was modified after the wizard wrote it;
- the rollback manifest is incomplete;
- the target path is not one of the managed files;
- the hash comparison does not prove the action is safe.

This avoids overwriting unrelated user changes.
