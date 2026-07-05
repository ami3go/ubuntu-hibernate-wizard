# How Hibernation Works

Hibernation writes all RAM into swap space and powers off. On resume, the kernel must find that image **before** the filesystem is mounted, so it needs two coordinates on its command line:

- `resume=UUID=<fs-uuid>` — which filesystem holds the swap file
- `resume_offset=<blocks>` — where inside that filesystem the swap file physically starts (first extent, from `filefrag -v`)

## Why it breaks

The offset is a property of the *current* file's placement on disk. Delete and recreate the swap file — even at the same path and size — and the offset almost certainly changes, while GRUB still carries the old number. Result: the machine cold-boots and the hibernated session is lost. This is the single most common hibernation failure on Ubuntu, and the reason this wizard re-measures and verifies instead of assuming.
