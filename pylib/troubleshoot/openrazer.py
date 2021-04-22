#!/usr/bin/python3
#
# Polychromatic is licensed under the GPLv3.
# Copyright (C) 2020-2021 Luke Horwell <code@horwell.me>
#
"""
Troubleshooter for OpenRazer >2.0 and 3.x series.

Users occasionally may end up with installation problems due to the nature of
having a driver module and requirement of being in the 'plugdev' group.

Troubleshooting this aims to inform the user and prompt some guidelines to
get the system up and running again.

The future of OpenRazer aims to move to userspace, which will eliminate
a lot of the common driver issues.
"""

import glob
import requests
import os
import subprocess
import shutil

try:
    from openrazer import client as rclient
    PYTHON_LIB_PRESENT = True
except Exception:
    PYTHON_LIB_PRESENT = False


def troubleshoot(_):
    """
    See: _backend.Backend.troubleshoot()
    """
    results = []

    try:
        # Troubleshooting only supported on Linux.
        uname = os.uname()
        if uname.sysname != "Linux":
            return None

        # Gather info about OpenRazer Daemon
        try:
            daemon_pid_file = os.path.join(os.environ["XDG_RUNTIME_DIR"], "openrazer-daemon.pid")
        except KeyError:
            daemon_pid_file = os.path.join("/run/user/", str(os.getuid()), "openrazer-daemon.pid")

        # Can openrazer-daemon be found?
        results.append({
            "test_name": _("Daemon is installed"),
            "suggestions": [
                _("Install the 'openrazer-meta' package for your distribution.")
            ],
            "passed": True if shutil.which("openrazer-daemon") != None else False
        })

        # Is openrazer-daemon running?
        daemon_running = False
        if os.path.exists(daemon_pid_file):
            with open(daemon_pid_file) as f:
                daemon_pid = int(f.readline())
            if os.path.exists("/proc/" + str(daemon_pid)):
                daemon_running = True

        results.append({
            "test_name": _("Daemon is running"),
            "suggestions": [
                _("Start the daemon from the terminal. Run this command and look for errors:"),
                "$ openrazer-daemon -Fv",
            ],
            "passed": daemon_running
        })

        # Are the Python libraries working?
        results.append({
            "test_name": _("Python library is installed"),
            "suggestions": [
                _("Install the 'python3-openrazer' package for your distribution."),
                _("Check the PYTHONPATH environment variable is correct."),
            ],
            "passed": PYTHON_LIB_PRESENT
        })

        # Gather info about DKMS
        dkms_installed_src = None
        dkms_installed_built = None

        if PYTHON_LIB_PRESENT:
            dkms_version = rclient.__version__
            kernel_version = uname.release
            expected_dkms_src = "/var/lib/dkms/openrazer-driver/{0}".format(dkms_version)
            expected_dkms_build = "/var/lib/dkms/openrazer-driver/kernel-{0}-{1}".format(uname.release, uname.machine)

            # Is the OpenRazer DKMS module installed?
            dkms_installed_src = True if os.path.exists(expected_dkms_src) else False
            dkms_installed_built = True if os.path.exists(expected_dkms_build) else False

            results.append({
                "test_name": _("DKMS sources are installed"),
                "suggestions": [
                    _("Install the 'openrazer-driver-dkms' package for your distribution."),
                ],
                "passed": dkms_installed_src
            })

            results.append({
                "test_name": _("DKMS module has been built for this kernel version"),
                "suggestions": [
                    _("Ensure you have the correct Linux kernel headers package installed for your distribution."),
                    _("Your distro's package system might not have rebuilt the DKMS module (this can happen with kernel or OpenRazer updates). Try running:"),
                    "$ sudo dkms install -m openrazer-driver/x.x.x".replace("x.x.x", dkms_version),
                ],
                "passed": dkms_installed_built
            })

        # Can the DKMS module be loaded?
        modprobe = subprocess.Popen(["modprobe", "-n", "razerkbd"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        output = modprobe.communicate()[0].decode("utf-8")
        code = modprobe.returncode

        results.append({
            "test_name": _("DKMS module can be probed"),
            "suggestions": [
                _("For full error details, run:"),
                "$ sudo modprobe razerkbd",
            ],
            "passed": True if code == 0 else False
        })

        # Is a Razer DKMS module loaded right now?
        lsmod = subprocess.Popen(["lsmod"], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        output = lsmod.communicate()[0].decode("utf-8")

        results.append({
            "test_name": _("DKMS module is currently loaded"),
            "suggestions": [
                _("For full error details, run:"),
                "$ sudo modprobe razerkbd"
            ],
            "passed": True if output.find("razer") != -1 else False
        })

        # Is secure boot the problem?
        if os.path.exists("/sys/firmware/efi"):
            sb_sysfile = glob.glob("/sys/firmware/efi/efivars/SecureBoot*")

            sb_reason = _("Secure Boot prevents the driver from loading, as OpenRazer's kernel modules built by DKMS are usually unsigned.")

            if len(sb_sysfile) > 0:
                # The last digit of this sysfs file indicates whether secure boot is enabled
                secureboot = subprocess.Popen(["od", "--address-radix=n", "--format=u1", sb_sysfile[0]], stdout=subprocess.PIPE)
                status = secureboot.communicate()[0].decode("utf-8").split(" ")[-1].strip()

                results.append({
                    "test_name": _("Check Secure Boot (EFI) status"),
                    "suggestions": [
                        _("Secure boot is enabled. Turn it off in the system's EFI settings or sign the modules yourself."),
                        sb_reason,
                    ],
                    "passed": True if int(status) == 0 else False
                })

            else:
                # Possibly "invalid argument". Can't be sure if it's on or off.
                results.append({
                    "test_name": _("Check Secure Boot (EFI) status"),
                    "suggestions": [
                        _("Unable to automatically check. If it's enabled, turn it off in the system's EFI settings or sign the modules yourself."),
                        sb_reason,
                    ],
                    "passed": None
                })

        # Is user in plugdev group?
        groups = subprocess.Popen(["groups"], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        results.append({
            "test_name": _("User account has been added to the 'plugdev' group"),
            "suggestions": [
                _("Run this command, log out, then log back in to the computer:"),
                "$ sudo gpasswd -a $USER plugdev",
                _("If you've recently installed, you may need to restart the computer."),
            ],
            "passed": True if groups.find("plugdev") != -1 else False
        })

        # Does plugdev have permission to read the files in /sys/?
        log_path = os.path.join(os.path.expanduser("~"), ".local/share/openrazer/logs/razer.log")
        if os.path.exists(log_path):
            with open(log_path) as f:
                log = f.readlines()

            results.append({
                "test_name": _("Check OpenRazer log for plugdev permission errors"),
                "suggestions": [
                    _("Restarting (or replugging) usually fixes the problem."),
                    _("To reset this error, clear the log:") + ' ' + log_path,
                ],
                "passed": True if "".join(log).find("Could not access /sys/") == -1 else False
            })

        # Supported device in lsusb?
        def _get_filtered_lsusb_list():
            """
            A copy of pylib/backends/openrazer._get_filtered_lsusb_list so the troubleshooter
            can run independently.

            Uses 'lsusb' to parse the devices and identify VID:PIDs that are not registered
            by the daemon, usually because they are not compatible yet.
            """
            all_usb_ids = []
            reg_ids = []
            unreg_ids = []

            # Strip lsusb to just get VIDs and PIDs
            try:
                lsusb = subprocess.Popen("lsusb", stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            except FileNotFoundError:
                print("'lsusb' not available, unable to determine if product is connected.")
                return None

            for usb in lsusb.split("\n"):
                if len(usb) > 0:
                    try:
                        vidpid = usb.split(" ")[5].split(":")
                        all_usb_ids.append([vidpid[0].upper(), vidpid[1].upper()])
                    except AttributeError:
                        pass

            # Get VIDs and PIDs of current devices to exclude them.
            devices = rclient.DeviceManager().devices
            for device in devices:
                try:
                    vid = str(hex(device._vid))[2:].upper().rjust(4, '0')
                    pid = str(hex(device._pid))[2:].upper().rjust(4, '0')
                except Exception as e:
                    print("Got exception parsing VID/PID: " + str(e))
                    continue

                reg_ids.append([vid, pid])

            # Identify Razer VIDs that are not registered in the daemon
            for usb in all_usb_ids:
                if usb[0] != "1532":
                    continue

                if usb in reg_ids:
                    continue

                unreg_ids.append(usb)

            return unreg_ids

        if PYTHON_LIB_PRESENT and dkms_installed_built:
            unsupported_devices = _get_filtered_lsusb_list()
            if type(unsupported_devices) == list:
                results.append({
                    "test_name": _("Check for unsupported hardware"),
                    "suggestions": [
                        _("Ensure the latest version is installed (your version is x.x.x).").replace("x.x.x", dkms_version),
                        _("Check the OpenRazer repository to confirm your device is listed as supported."),
                    ],
                    "passed": len(unsupported_devices) == 0
                })

        if PYTHON_LIB_PRESENT:
            local_version = rclient.__version__
            remote_version = None
            remote_get_url = "https://openrazer.github.io/api/latest_version.txt"
            try:
                request = requests.get(remote_get_url)

                # Response should be 3 digits, e.g. 3.0.1
                if request.status_code == 200 and len(request.text.strip().split(".")) == 3:
                    remote_version = request.text.strip()
            except Exception as e:
                # Gracefully ignore connection errors
                print("Could not retrieve OpenRazer data: {0}\n{1}".format(str(e), remote_get_url))
                request = None

            def _is_version_newer_then(verA, verB):
                verA = verA.split(".")
                verB = verB.split(".")
                is_new = False

                if int(verA[0]) > int(verB[0]):
                    is_new = True

                if float(verA[1] + '.' + verA[2]) > float(verB[1] + '.' + verB[2]):
                    is_new = True

                return is_new

            if remote_version:
                results.append({
                    "test_name": _("OpenRazer is the latest version"),
                    "suggestions": [
                        _("There is a new version of OpenRazer available."),
                        _("New versions add support for more devices and address device-specific issues."),
                        _("Your version: 0.0.0").replace("0.0.0", local_version),
                        _("Latest version: 0.0.0").replace("0.0.0", remote_version),
                    ],
                    "passed": _is_version_newer_then(remote_version, local_version) is not True
                })
            else:
                results.append({
                    "test_name": _("OpenRazer is the latest version"),
                    "suggestions": [
                        _("Unable to retrieve this data from OpenRazer's website."),
                        _("Check the OpenRazer website to confirm your device is listed as supported."),
                        _("If you're checking the GitHub repository, check the 'stable' branch."),
                    ],
                    "passed": None
                })

    except Exception as e:
        print("Troubleshooter failed to complete!")
        from .. import common
        return common.get_exception_as_string(e)

    return results
