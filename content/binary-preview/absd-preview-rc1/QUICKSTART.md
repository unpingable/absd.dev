# Try ABSD absd-preview-rc1

Developer preview for a local Linux x86-64 host with QEMU 8.2, Python 3.11+,
OpenSSH, curl, xz and sha256sum. No Rust, Clang, GRUB or source checkout is
needed. Profile: QEMU 8.2, x86-64, TCG, one CPU, 256 MiB minimum, SeaBIOS, e1000, primary IDE disk. Use TCG for this guide; KVM and other hosts are
separate qualification cases. Kernel d208b61bcd4826181bf9f401551ab620d4eabba0; platform
0fada7ed031bd84e3a469e717c1d0be5dbefedd6. Artifact standing when sealed: built.
Check https://absd.dev/releases/absd-preview-rc1/ for subsequent qualification,
availability and withdrawal notices before using these files.

## Download and verify

Run in a new empty directory on your host. Every URL names this exact tag.
These files are unsigned. A checksum downloaded beside a file detects
corruption; it does not prove who produced it.

```sh
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/MANIFEST.toml
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/NOTICES.md
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/QUICKSTART.md
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-boot-corresponding-source.tar
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-c12c-20261018t161241z.fvcgzh-disk.img.xz
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-c12c-20261018t161241z.fvcgzh-enroll.iso
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-c12c-20261018t161241z.fvcgzh-operator.iso
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-third-party-notices.tar.gz
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-try.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd_fs.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd_image.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/served_ram.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-rc1/SHA256SUMS
sha256sum -c SHA256SUMS
python3 absd-try.py verify .
```

Stop if either verification fails. Do not run an unverified helper.
Download all helper modules listed above beside absd-try.py.

## Create your machine

Generate a fresh key at a new path; keep the private file on this host.
The helper receives only its .pub file. It decompresses a fresh writable
disk and runs the release's enrollment image. The serial enrollment channel
is trusted only inside this local QEMU environment. It is not an unattended
remote enrollment service. Downloaded media carries no reusable host key or
login identity. Copies initially share the filesystem id; SSH identities are
generated for each machine.

```sh
ssh-keygen -t ed25519 -N '' -f ./absd-key
python3 absd-try.py create ./machine --assets . --key ./absd-key.pub --accel tcg
python3 absd-try.py boot ./machine --port 2222 --accel tcg
```

Leave boot running in that terminal. It records the host key from the local
VM console in machine/known_hosts and prints READY. In a second terminal in
the same directory, use that file and the exact key:

```sh
ssh -F /dev/null -p 2222 -i ./absd-key -o IdentitiesOnly=yes -o IdentityAgent=none -o ForwardAgent=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=./machine/known_hosts operator@127.0.0.1
```

In ABSD, read the manual, exercise commands and write a file:

```text
man intro
uptime
cd /home/operator
echo release-check > release-check.txt
cat release-check.txt
shutdown
```

The helper should report HALTED cleanly. Boot the same machine again, SSH
using the same command, then run `cat /home/operator/release-check.txt` and
`shutdown`. The file should contain `release-check`. Keep machine/disk.img
for your state; do not run create again or replace it to reboot. The manual
installed in this image is for platform 0fada7ed031bd84e3a469e717c1d0be5dbefedd6; the
site's older milestone manual describes its own earlier revision.

## Troubleshooting

- Checksum failure: stop and re-download the exact tagged files into a fresh directory.
- Enrollment refusal: read machine/enroll-console.log; use a plain ssh-ed25519 .pub file and leave the guest stopped while enrolling.
- Port 2222 busy: stop your other guest, or choose a different --port and use that same SSH port.
- No READY: inspect machine/console.log and machine/qemu.log. Use --accel tcg and the recorded files. Do not switch device models.
- Login refused: use the enrolled private key and machine/known_hosts. A changed host key requires diagnosis; do not disable verification.
- Ctrl-C stops QEMU abruptly. Use shutdown inside ABSD for the documented clean stop. Never run two guests on one writable disk.

## Limits and provenance

- Physical hardware qualification is not yet established.
- RC1 candidate 12c preview built locally; no public release, outsider acceptance or endurance claim.
- No source release is bound to these assets (no release source_commit).
- Exact GRUB and GNU Unifont corresponding source and the third-party binary notices are attached (absd-rc1-boot-corresponding-source.tar, absd-rc1-third-party-notices.tar.gz, NOTICES.md); they are not the first-party ABSD source release.
- A 64 MiB disk cannot take a second staged release under the current layout; staged upgrade and rollback are not supported in this preview.

This rehearsal is separate from long-running U1 qualification, release
authorization, publication and a reader's successful download from public
URLs. The release manifest, SHA256SUMS and NOTICES.md travel with the files.

## Updating to a new preview

This preview supports replacement, not in-place upgrade. Staged upgrade
and rollback are not supported: a 64 MiB disk cannot take a second staged
release under the current layout. Do not stage a second release inside the
guest.

To move to a newer preview:

1. While the old machine is running, copy anything you need out of it over
   SSH. Moving data between machines is not part of the qualified workflow.
   Then run `shutdown` inside ABSD.
2. In a new empty directory, download the newer preview's release set and
   verify it with `sha256sum -c SHA256SUMS` and `python3 absd-try.py verify .`,
   as in "Download and verify" above.
3. Create and enroll a new machine directory with `python3 absd-try.py create`,
   then boot it with `python3 absd-try.py boot`, exactly as in "Create your
   machine" above. Do not reuse or overwrite the old machine directory.

In this preview's qualification, an over-capacity staging attempt stopped
partway without changing the installed release. That is a bounded
observation, not a supported recovery procedure.

## Third-party notices and boot-component source

Third-party licences and corresponding source

Keep third-party-notices/ (or absd-rc1-third-party-notices.tar.gz) and grub-source/ beside these media. Read third-party-notices/NOTICES.md and UPSTREAM-TEXTS.md for component notices and the supplemental upstream licence texts. grub-source/ contains the exact GRUB and GNU Unifont corresponding-source packages. Verify these files against the distribution manifest before using or redistributing the bundle.

The kernel-third-party-notices/ directory supplies the kernel toolchain, console-font and Intel driver notices. Keep it with the platform notice directory.
