# Try ABSD absd-preview-2

Developer preview for a local Linux x86-64 host with QEMU 8.2, Python 3.11+,
OpenSSH, curl, xz and sha256sum. No Rust, Clang, GRUB or source checkout is
needed. Profile: QEMU 8.2, x86-64, TCG, one CPU, 256 MiB minimum, SeaBIOS, e1000, primary IDE disk. Use TCG for this guide; KVM and other hosts are
separate qualification cases. Kernel 919f0676eacbdd06bfa17e1da9d951fb374e3a1b; platform
0b002f732b1d11ec503868d99896c6bd5db80757. Artifact standing when sealed: built.
Check https://absd.dev/releases/absd-preview-2/ for subsequent qualification,
availability and withdrawal notices before using these files.

## Download and verify

Run in a new empty directory on your host. Every URL names this exact tag.
These files are unsigned. A checksum downloaded beside a file detects
corruption; it does not prove who produced it.

```sh
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/BUILD-INPUTS.json
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/MANIFEST.toml
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/NOTICES.md
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/QUICKSTART-INPUT.json
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/QUICKSTART.md
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/absd-try.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/absd_fs.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/absd_image.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/boot-corresponding-source.tar
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/disk.img.xz
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/enroll.iso
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/operator.iso
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/served_ram.py
curl --fail --location --remote-name https://github.com/unpingable/absd/releases/download/absd-preview-2/SHA256SUMS
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
python3 absd-try.py boot ./machine --port 2222 --accel tcg --login-key ./absd-key
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
installed in this image is for platform 0b002f732b1d11ec503868d99896c6bd5db80757; the
site's older milestone manual describes its own earlier revision.

## Troubleshooting

- Checksum failure: stop and re-download the exact tagged files into a fresh directory.
- Enrollment refusal: read machine/enroll-console.log; use a plain ssh-ed25519 .pub file and leave the guest stopped while enrolling.
- Port 2222 busy: stop your other guest, or choose a different --port and use that same SSH port.
- No READY: inspect machine/console.log and machine/qemu.log. Use --accel tcg and the recorded files. Do not switch device models.
- Login refused: use the enrolled private key and machine/known_hosts. A changed host key requires diagnosis; do not disable verification.
- Ctrl-C in the boot terminal asks the machine to shut down cleanly, using --login-key. If it cannot confirm the shutdown, it leaves the machine running and prints the command to try again; your files are kept. A second Ctrl-C forces a stop, and the next boot may need recovery. Never run two guests on one writable disk.

## Limits and provenance

- Physical hardware qualification is not yet established.
- Experimental absd-preview-2; outsider acceptance and endurance qualification are not established.
- Matching curated first-party source records this kernel/platform pair separately; this binary manifest does not record a source_commit field.
- Notice texts accompany this preview; actual build/media correspondence and the remaining recorded release obligations require their stated checks.
- The documented preview boot path uses local QEMU TCG, SeaBIOS and an IDE disk.
- An unclean shutdown fences writable restart; recovery requires an explicit supported operator procedure.
- This product includes software developed at Cygnus Support, Inc.
- This product includes software developed by the University of California, Berkeley.
- This product includes software developed by the University of California, Berkeley and its contributors
- Naming an organisation acknowledges its work; it does not imply that it endorses ABSD.

This rehearsal is separate from long-running U1 qualification, release
authorization, publication and a reader's successful download from public
URLs. The release manifest, SHA256SUMS and NOTICES.md travel with the files.
