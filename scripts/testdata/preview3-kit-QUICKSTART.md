# ABSD Developer Preview 3 quickstart

ABSD Developer Preview 3 runs as a QEMU guest on an x86-64 Linux host.
This guide takes you from the downloaded files to an SSH session in the
guest, an edited file that survives a reboot, and a clean removal.
It needs no ABSD build tools.

## Check the host and the files

Use an Ubuntu 24.04 x86-64 host with QEMU 8.2, Python 3.11 or newer,
the OpenSSH client and GNU coreutils. The Ubuntu packages are
`qemu-system-x86`, `python3`, `openssh-client` and `coreutils`.
The guest has one CPU, 256 MiB of memory, an e1000 network card and an
IDE disk. The commands below select QEMU's software emulation (TCG),
which is what this kit was tested with. It is slower than KVM.

You need four downloaded files in one directory: `SHA256SUMS`,
`SHA256SUMS.source`, `QUICKSTART.md` (this guide) and
`absd-preview-3-operator.tar.gz`.

The checksum lists show that the files match the lists. They cannot
show who wrote the lists. You were given a SHA-256 value for
`SHA256SUMS` along with the download. In the download directory, put
that value in place of `DIGEST` and run:

```sh
echo "DIGEST  SHA256SUMS" | sha256sum -c --strict - &&
sha256sum -c --strict SHA256SUMS &&
mkdir preview3-operator &&
tar -xzf absd-preview-3-operator.tar.gz -C preview3-operator &&
cd preview3-operator &&
sha256sum -c --strict SHA256SUMS &&
python3 absd-try.py verify .
```

Each step runs only if the one before it succeeded, so nothing is
unpacked or run from a download that failed its check. The last line of
output must begin `absd-try: VERIFIED release=absd-preview-3`. If it
does not, stop and download the files again.

The first `SHA256SUMS` covers the kit, this guide and
`SHA256SUMS.source`. The second, inside the kit, covers the boot media,
the disk, the manifest and the helper scripts. The kit carries a copy of
this guide. That copy is for use after the steps above. Do not start
from an unpacked kit whose download you have not checked this way.

The source and notice archives are not needed to run the preview. They
total about 81 MB. If you download them, put them in the download
directory and check them there with:

```sh
sha256sum -c --strict SHA256SUMS.source
```

`SHA256SUMS` lists `SHA256SUMS.source`, so the first check also vouches
for the list the source archives are checked against.

## Enroll and connect

Stay in the kit directory, on the machine that will run QEMU. Make a new
key for this guest and create a machine from the kit. The helper is
given only the public key. It writes that key to a fresh copy of the
disk and checks that nothing else on the disk changed.

```sh
ssh-keygen -t ed25519 -N '' -f ./absd-key
python3 absd-try.py create ./machine --assets . --key ./absd-key.pub --accel tcg
python3 absd-try.py boot ./machine --port 2222 --accel tcg
```

Leave this boot terminal running and wait for these two lines:

```text
absd-try: HOST KEY LOADED SHA256:... (read from the VM console, recorded in machine/known_hosts)
absd-try: READY ssh -tt -F /dev/null -p 2222 -i ...
```

The guest printed its SSH host key on its serial console, which only
this host can read. The helper copied the key from there to
`machine/known_hosts`. Open a second terminal in the kit directory and
print the fingerprint of the recorded key:

```sh
ssh-keygen -lf ./machine/known_hosts
```

The `SHA256:...` value it prints must be the one in the `HOST KEY` line
of the boot terminal. The fingerprint is what you check. The word before
it is `LOADED` on every boot, the first included, and tells you nothing
about the key. If the fingerprints differ, stop. If they match, log in with
the command printed after `READY`. It names the key and the recorded
host key by their full paths. Run from the kit directory, this is the
same command:

```sh
ssh -tt -F /dev/null -p 2222 -i "$PWD/absd-key" -o IdentitiesOnly=yes -o IdentityAgent=none -o ForwardAgent=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$PWD/machine/known_hosts" -o GlobalKnownHostsFile=/dev/null operator@127.0.0.1
```

It ignores your SSH configuration and agent and the system's list of
known hosts, offers only the new key, and accepts only the host key you
just checked. The guest's SSH port is
forwarded to port 2222 on this host's loopback address, so run the
command on the QEMU host. If that host is remote, log in to it first.

The guest greets you with a banner. Its last two lines are
`Release: absd-preview-3`, the same release name `verify` printed, and
`Authority is not ambient.`

## Edit a file and reopen it after shutdown

In the guest, run `pwd` and `env` to see the working directory and
`HOME`. The operator home is `/home/operator`. Try `man intro`, `man ed`
and `man more`. `man` shows one page at a time: Space shows the next
page, Enter shows one more line, and `q` returns to the prompt.

At the shell prompt, Ctrl-K erases from the cursor to the end of the
line. It also works at a continuation prompt. `man absd-sh` lists the
other editing keys.

Run the following commands. After `ed preview-run.sh`, the remaining
lines are typed to the editor. The line containing only a period ends
the replacement text.

```text
cd /home/operator
echo 'echo previous-program' > preview-run.sh
ed preview-run.sh
1c
echo preview3-edited-program
.
w
q
```

Run `/bin/absd-sh preview-run.sh` and check that it prints
`preview3-edited-program`. Run `sync`, then `shutdown`. Wait for
`POWERED OFF cleanly (ACPI S5)` in the boot terminal.

Run the same boot command again, then the same fingerprint check and
login command. The `HOST KEY` line must show the same fingerprint as
before. In the guest, run
`cd /home/operator && /bin/absd-sh preview-run.sh` and check for the
same output. End with `shutdown`.

## Remove the machine and the key

When you have finished, and the boot terminal shows `POWERED OFF`, run
this in the kit directory:

```sh
rm -r ./machine
rm ./absd-key ./absd-key.pub
```

`machine/` holds the working disk with your public key on it, the
recorded host key and the logs. The key pair was made for this guest
only. The login command wrote nothing under `~/.ssh`, so nothing else on
the host refers to the guest. To come back to the same disk later, keep
`machine/` and both key files instead. The unpacked kit can make any
number of new machines.

## Recover from a setup or session error

- `qemu_unavailable`: install `qemu-system-x86`, or set `ABSD_TRY_QEMU`
  to your QEMU executable. Nothing was created.
- Enrollment refusal: check `machine/enroll-console.log`. Use a plain
  Ed25519 public-key file. Keep the failed directory for diagnosis and
  use a new directory for a new attempt.
- Busy SSH port: choose another port in the boot command and use the
  command from the new `READY` line.
- No `READY` line: check `machine/qemu.log`. `machine/console.log` is
  the guest's console in the helper's framed format.
- `host_key_changed`, or SSH reports a changed host key: stop. Do not
  delete `machine/known_hosts` or turn off host-key checking to get in.
- Dropped session: log in again while the boot terminal is still
  running. Write the file (`w`) before leaving `ed`.
- Ctrl-C in the boot terminal stops QEMU without a clean shutdown. Use
  `shutdown` in the guest. If the next boot refuses the disk, keep
  `machine/` and its logs for diagnosis and create a new machine in
  another directory.
- `ssh_path_unsupported`: the kit directory's full path contains `%`,
  `${`, a quote, a backslash or a control character. Move the kit to a
  plainer path. The login command above also needs a path without
  spaces; the `READY` command works with them.
- A very long working directory path is fine. The helper then puts its
  enrollment socket in a private directory under `/tmp`.

## Limits of this preview

This kit has no C compiler in the guest (`/bin/cc` is absent) and no
host C development kit. It has been tested under QEMU with TCG only.
KVM, physical hardware, recovery after a crash, and full Unix
compatibility are outside what this guide covers.

As shipped, the guest opens no outbound connections. An HTTPS fetch
client, `https-fetch`, is installed, but this disk has no network grant
and no trusted server for it, so it refuses every URL. `man https-fetch`
describes what an image built from source needs before it will fetch.
