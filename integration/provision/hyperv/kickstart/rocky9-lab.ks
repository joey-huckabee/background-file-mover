# Rocky 9 unattended install for the file-mover integration lab.
#
# Delivered on a second ISO whose volume label is OEMDRV. Anaconda scans for
# that label at boot and loads ks.cfg from it automatically, which is what makes
# this unattended WITHOUT editing kernel boot parameters -- the alternative
# needs a console session driven by hand or by screen-scraping, and neither is
# something to build a test suite on.
#
# This file installs a MINIMUM viable host and stops. Everything else is
# Ansible's job (layer 2). The rule that keeps the split honest: if a setting
# could be applied over SSH after first boot, it does not belong here. What is
# left is only what must exist before SSH works at all.
#
# @KEY@ is replaced with the lab SSH public key by New-KickstartIso.ps1.

text
eula --agreed
reboot --eject

# --- locale and time -------------------------------------------------------
# UTC deliberately. Every timestamp this service emits is UTC (see
# format_event in cpp/src/event_log.cpp), and a guest in local time makes
# correlating a test failure against the service log an exercise in arithmetic.
keyboard --vckeymap=us --xlayouts='us'
lang en_US.UTF-8
timezone UTC --utc

# --- network ---------------------------------------------------------------
# Explicit, and not optional. With `cdrom` as the install source Anaconda never
# needs to bring an interface up, so with no network line here the installed
# system's connectivity depends entirely on NetworkManager's auto-default
# behaviour on first boot. When that does not fire the VM installs perfectly and
# is simply unreachable -- which presents as "the build worked but SSH times
# out", and costs an hour to trace back to a line that is not in this file.
#
# --device=link  : the first interface with a carrier. The VM has one NIC; this
#                  avoids naming it, since predictable-interface-names on
#                  Hyper-V gives eth0 or ens-something depending on the guest.
# --activate     : brings it up during the install as well as after it.
# --onboot=yes   : the part that matters -- the connection comes up at boot.
# --hostname     : written to /etc/hostname by Anaconda directly. This replaces
#                  a `hostnamectl` call in %post, which could not have worked:
#                  %post is chrooted with no dbus, so there is no hostnamed to
#                  answer, and the `|| true` on it swallowed the failure.
network --bootproto=dhcp --device=link --activate --onboot=yes --hostname=fm-rocky9-01

# --- installation source ---------------------------------------------------
# cdrom: the minimal ISO carries the base packages, so the install does not
# depend on a mirror being reachable at that moment. Package installs AFTER
# first boot do use the network, which is why the lab uses an external switch.
cdrom
%packages
@^minimal-environment
openssh-server
# python3 is required by Ansible on the managed host. Installing it here rather
# than bootstrapping it later avoids the chicken-and-egg where the first
# playbook cannot run because the interpreter it needs is missing.
python3
%end

# --- disk ------------------------------------------------------------------
# The whole (virtual) disk, no LVM. LVM is what a production build would use;
# here it adds a layer between a test and the filesystem it is asserting about,
# and this lab tests file movement rather than volume management.
ignoredisk --only-use=sda
clearpart --all --initlabel --drives=sda
autopart --type=plain --nohome

# --- security --------------------------------------------------------------
# SELinux ENFORCING. This is the single most important line in the file.
# The whole reason for a RHEL 9 host is that the container tiers cannot tell us
# whether the service runs under SELinux, and a lab in permissive mode would
# answer that question wrongly and confidently. Expect denials on the first run;
# those are the finding, not a failure.
selinux --enforcing

# The firewall stays ON, with the control-plane port opened by Ansible rather
# than here. A lab with the firewall off cannot tell "the service is not
# listening" from "the port is blocked", and that is a distinction an operator
# will have to make on a real deployment.
firewall --enabled --service=ssh

# Root login disabled entirely. A password-less root account on a LAN-visible VM
# is not acceptable even in a lab.
rootpw --lock

# labadmin has a password for the CONSOLE only, and a key for the network.
#
# The first build of this lab locked labadmin's password too, on the reasoning
# that key-only is stricter. It is, and it also meant that if sshd had failed to
# start there would have been no way into the machine at all -- the exact
# "a VM with no console" problem this file's other comments keep warning about,
# applied to ourselves. A lab that cannot be rescued has to be rebuilt to be
# diagnosed, and a 15-minute rebuild destroys the evidence you wanted.
#
# @CONSOLEPW@ is replaced by New-KickstartIso.ps1 with a generated password,
# which it writes to the lab key directory next to the SSH private key. It is
# NOT in this repository and is not the same on two machines.
#
# --plaintext because the password is substituted at ISO-build time on Windows,
# which has no crypt(3) to pre-hash it with. The ISO carrying it lives in the
# same directory as the SSH private key, so it is inside a boundary the lab
# already treats as secret.
user --name=labadmin --groups=wheel --password=@CONSOLEPW@ --plaintext
sshkey --username=labadmin "@KEY@"

# Passwordless sudo for the lab account. Ansible needs to escalate without an
# interactive prompt, and storing a sudo password in the inventory would be
# worse. This is a lab-only affordance and is called out as such in
# docs/INTEGRATION-INVENTORY.md.
%post --erroronfail
echo 'labadmin ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-labadmin
chmod 0440 /etc/sudoers.d/90-labadmin

# Keep SSH key-only now that labadmin has a password.
#
# The password above exists for the console and nothing else. Left alone, sshd
# would happily accept it over the network, which would quietly undo the
# key-only decision -- the account would go from "unreachable without the key"
# to "guessable from the LAN" without a single line saying so.
#
# This is in the kickstart rather than in Ansible, despite the rule at the top
# of this file, because it has to be true at FIRST BOOT. Applying it in the
# playbook leaves a window between install and configuration during which the
# VM is on the LAN accepting passwords, and the length of that window depends on
# when someone gets round to running Ansible.
#
# RHEL 9's sshd_config begins with Include /etc/ssh/sshd_config.d/*.conf, and
# first-obtained-value-wins means a drop-in read early overrides the main file.
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-lab-keyonly.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
chmod 0600 /etc/ssh/sshd_config.d/99-lab-keyonly.conf
%end

# --- services --------------------------------------------------------------
services --enabled=sshd,chronyd

# No graphical target: this is a headless service host, and the GUI stack is
# both a large attack surface and several hundred megabytes of packages whose
# updates would slow every rebuild.
skipx
