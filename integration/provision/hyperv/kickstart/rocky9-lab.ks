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

# Root login disabled entirely; the lab admin account is the only way in, and
# it authenticates by key. A password-less root account on a LAN-visible VM is
# not acceptable even in a lab.
rootpw --lock
user --name=labadmin --groups=wheel --lock
sshkey --username=labadmin "@KEY@"

# Passwordless sudo for the lab account. Ansible needs to escalate without an
# interactive prompt, and storing a sudo password in the inventory would be
# worse. This is a lab-only affordance and is called out as such in
# docs/INTEGRATION-INVENTORY.md.
%post --erroronfail
echo 'labadmin ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-labadmin
chmod 0440 /etc/sudoers.d/90-labadmin

# Predictable hostname, so the Ansible inventory and any log correlation have
# something stable to key on.
hostnamectl set-hostname fm-rocky9-01 || true
%end

# --- services --------------------------------------------------------------
services --enabled=sshd,chronyd

# No graphical target: this is a headless service host, and the GUI stack is
# both a large attack surface and several hundred megabytes of packages whose
# updates would slow every rebuild.
skipx
