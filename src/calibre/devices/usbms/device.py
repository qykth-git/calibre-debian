__license__   = 'GPL v3'
__copyright__ = ('2009, John Schember <john at nachtimwald.com> '
                 '2009, Kovid Goyal <kovid@kovidgoyal.net>')
__docformat__ = 'restructuredtext en'

'''
Generic device driver. This is not a complete stand alone driver. It is
intended to be subclassed with the relevant parts implemented for a particular
device. This class handles device detection.
'''

import glob
import os
import re
import subprocess
import sys
import time
from collections import namedtuple
from contextlib import suppress
from itertools import repeat

from calibre import prints
from calibre.constants import is_debugging, isfreebsd, islinux, ismacos, iswindows
from calibre.devices.errors import DeviceError
from calibre.devices.interface import FAKE_DEVICE_SERIAL, DevicePlugin, ModelMetadata
from calibre.devices.usbms.deviceconfig import DeviceConfig
from calibre.utils.filenames import ascii_filename as sanitize
from polyglot.builtins import iteritems, string_or_bytes

if ismacos:
    osx_sanitize_name_pat = re.compile(r'[.-]')

if iswindows:
    usb_info_cache = {}


def eject_exe():
    base = sys.extensions_location if hasattr(sys, 'new_app_layout') else os.path.dirname(sys.executable)
    return os.path.join(base, 'calibre-eject.exe')


class USBDevice:

    def __init__(self, dev):
        self.idVendor = dev[0]
        self.idProduct = dev[1]
        self.bcdDevice = dev[2]
        if iswindows:
            # Getting this information requires communicating with the device
            # we only do that in the can_handle_windows() method, if needed.
            self.manufacturer = self.serial = self.product = None
        else:
            self.manufacturer = dev[3]
            self.product = dev[4]
            self.serial = dev[5]

    def match_serial(self, serial):
        return self.serial and self.serial == serial

    def match_numbers(self, vid, pid, bcd):
        return self.idVendor == vid and self.idProduct == pid and self.bcdDevice == bcd

    def match_strings(self, vid, pid, bcd, man, prod):
        if not self.match_numbers(vid, pid, bcd):
            return False
        if man == self.manufacturer and prod == self.product:
            return True
        # As of macOS 10.11.4 Apple started mangling the names returned via the
        # IOKit registry. See
        # https://www.mobileread.com/forums/showthread.php?t=273213
        m = osx_sanitize_name_pat.sub('_', (self.manufacturer or ''))
        p = osx_sanitize_name_pat.sub('_', (self.product or ''))
        return m == man and p == prod


class Device(DeviceConfig, DevicePlugin):
    '''
    This class provides logic common to all drivers for devices that export themselves
    as USB Mass Storage devices. Provides implementations for mounting/ejecting
    of USBMS devices on all platforms.
    '''

    VENDOR_ID   = 0x0
    PRODUCT_ID  = 0x0
    BCD         = None

    VENDOR_NAME = None

    #: String identifying the main memory of the device in the Windows PnP id
    #: strings
    #: This can be None, string, list of strings or compiled regex
    WINDOWS_MAIN_MEM = None

    #: String identifying the first card of the device in the Windows PnP id
    #: strings
    #: This can be None, string, list of strings or compiled regex
    WINDOWS_CARD_A_MEM = None

    #: String identifying the second card of the device in the Windows PnP id
    #: strings
    #: This can be None, string, list of strings or compiled regex
    WINDOWS_CARD_B_MEM = None

    #: Used by the new driver detection to disambiguate main memory from
    #: storage cards. Should be a regular expression that matches the
    #: main memory mount point assigned by macOS
    OSX_MAIN_MEM_VOL_PAT = None
    OSX_EJECT_COMMAND = ['diskutil', 'eject']

    MAIN_MEMORY_VOLUME_LABEL  = ''
    STORAGE_CARD_VOLUME_LABEL = ''
    STORAGE_CARD2_VOLUME_LABEL = None

    EBOOK_DIR_MAIN = ''
    EBOOK_DIR_CARD_A = ''
    EBOOK_DIR_CARD_B = ''
    DELETE_EXTS = []

    # USB disk-based devices can see the book files on the device, so can
    # copy these back to the library
    BACKLOADING_ERROR_MESSAGE = None

    #: The maximum length of paths created on the device
    MAX_PATH_LEN = 250

    #: Put news in its own folder
    NEWS_IN_FOLDER = True

    connected_folder_path = ''  # used internally for fake folder device
    eject_connected_folder = False

    @classmethod
    def model_metadata(cls) -> tuple[ModelMetadata, ...]:
        def get_representative_ids() -> tuple[int, int, int]:
            vid = pid = bcd = 0
            if isinstance(cls.VENDOR_ID, dict):
                for vid, pid_map in cls.VENDOR_ID.items():
                    for pid, bcds in pid_map.items():
                        if isinstance(bcds, int):
                            bcds = (bcds,)
                        for bcd in bcds:
                            return vid or 0, pid or 0, bcd or 0
            elif isinstance(cls.VENDOR_ID, (list, tuple)):
                vid = cls.VENDOR_ID[-1]
            else:
                vid = cls.VENDOR_ID
            if isinstance(cls.PRODUCT_ID, (list, tuple)):
                pid = cls.PRODUCT_ID[-1]
            else:
                pid = cls.PRODUCT_ID
            if isinstance(cls.BCD, (list, tuple)):
                bcd = cls.BCD[-1]
            else:
                bcd = cls.BCD
            return vid or 0, pid or 0, bcd or 0
        vid, pid, bcd = get_representative_ids()
        try:
            model_name = cls.get_gui_name()
        except TypeError:  # The WAYTEQ driver implements this as non classmethod
            return ()
        parts = model_name.split(' ', 1)
        manufacturer = ''
        if len(parts) > 1:
            manufacturer, model_name = parts
        else:
            manufacturer = _('Miscellaneous')
        return (
            ModelMetadata(manufacturer, model_name, vid, pid, bcd, cls),
        )

    def reset(self, key='-1', log_packets=False, report_progress=None,
            detected_device=None):
        self._main_prefix = self._card_a_prefix = self._card_b_prefix = None
        self.detected_device = None if detected_device is None else USBDevice(detected_device)
        self.set_progress_reporter(report_progress)

    def set_progress_reporter(self, report_progress):
        self.report_progress = report_progress
        self.report_progress = report_progress
        if self.report_progress is None:
            self.report_progress = lambda x, y: x

    def card_prefix(self, end_session=True):
        return (self._card_a_prefix, self._card_b_prefix)

    @classmethod
    def _windows_space(cls, prefix):
        if not prefix:
            return 0, 0
        prefix = prefix[:-1]
        from calibre_extensions import winutil
        try:
            available_space, total_space, free_space = winutil.get_disk_free_space(prefix)
        except OSError as err:
            if err.winerror == winutil.ERROR_NOT_READY:
                # Disk not ready
                time.sleep(3)
                available_space, total_space, free_space = winutil.get_disk_free_space(prefix)
            else:
                raise
        return total_space, available_space

    def total_space(self, end_session=True):
        msz = casz = cbsz = 0
        if not iswindows:
            if self._main_prefix is not None:
                stats = os.statvfs(self._main_prefix)
                msz = stats.f_frsize * (stats.f_blocks + stats.f_bavail - stats.f_bfree)
            if self._card_a_prefix is not None:
                stats = os.statvfs(self._card_a_prefix)
                casz = stats.f_frsize * (stats.f_blocks + stats.f_bavail - stats.f_bfree)
            if self._card_b_prefix is not None:
                stats = os.statvfs(self._card_b_prefix)
                cbsz = stats.f_frsize * (stats.f_blocks + stats.f_bavail - stats.f_bfree)
        else:
            msz = self._windows_space(self._main_prefix)[0]
            casz = self._windows_space(self._card_a_prefix)[0]
            cbsz = self._windows_space(self._card_b_prefix)[0]

        return msz, casz, cbsz

    def free_space(self, end_session=True):
        msz = casz = cbsz = 0
        if not iswindows:
            if self._main_prefix is not None:
                stats = os.statvfs(self._main_prefix)
                msz = stats.f_frsize * stats.f_bavail
            if self._card_a_prefix is not None:
                stats = os.statvfs(self._card_a_prefix)
                casz = stats.f_frsize * stats.f_bavail
            if self._card_b_prefix is not None:
                stats = os.statvfs(self._card_b_prefix)
                cbsz = stats.f_frsize * stats.f_bavail
        else:
            msz = self._windows_space(self._main_prefix)[1]
            casz = self._windows_space(self._card_a_prefix)[1]
            cbsz = self._windows_space(self._card_b_prefix)[1]

        return msz, casz, cbsz

    def windows_filter_pnp_id(self, pnp_id):
        return False

    def windows_sort_drives(self, drives):
        '''
        Called to disambiguate main memory and storage card for devices that
        do not distinguish between them on the basis of `WINDOWS_CARD_NAME`.
        For example: The EB600
        '''
        return drives

    def can_handle_windows(self, usbdevice, debug=False):
        if hasattr(self.can_handle, 'is_base_class_implementation'):
            # No custom can_handle implementation
            return True
        # Delegate to the unix can_handle function, creating a unix like
        # USBDevice object
        from calibre.devices.winusb import get_usb_info
        dev = usb_info_cache.get(usbdevice)
        if dev is None:
            try:
                data = get_usb_info(usbdevice, debug=debug)
            except Exception:
                time.sleep(0.1)
                try:
                    data = get_usb_info(usbdevice, debug=debug)
                except Exception:
                    data = {}
            dev = usb_info_cache[usbdevice] = namedtuple(
                'USBDevice', 'vendor_id product_id bcd manufacturer product serial')(
                usbdevice.vendor_id, usbdevice.product_id, usbdevice.bcd,
                data.get('manufacturer') or '', data.get('product') or '', data.get('serial_number') or '')
            if debug:
                prints(f'USB Info for device: {dev}')
        return self.can_handle(dev, debug=debug)

    def open_windows(self):
        from calibre.devices.scanner import drive_is_ok
        from calibre.devices.winusb import get_drive_letters_for_device
        usbdev = self.device_being_opened
        debug = is_debugging() or getattr(self, 'do_device_debug', False)
        try:
            dlmap = get_drive_letters_for_device(usbdev, debug=debug)
        except Exception:
            dlmap = {}

        if not dlmap.get('drive_letters'):
            time.sleep(7)
            dlmap = get_drive_letters_for_device(usbdev, debug=debug)

        if debug:
            from pprint import pformat
            prints(f'Drive letters for {usbdev}')
            prints(pformat(dlmap))

        filtered = set()
        for dl in dlmap['drive_letters']:
            pnp_id = dlmap['pnp_id_map'][dl].upper()
            if dl in dlmap['readonly_drives']:
                filtered.add(dl)
                if debug:
                    prints(f'Ignoring the drive {dl} as it is readonly')
            elif self.windows_filter_pnp_id(pnp_id):
                filtered.add(dl)
                if debug:
                    prints(f'Ignoring the drive {dl} because of a PNP filter on {pnp_id}')
            elif not drive_is_ok(dl, debug=debug):
                filtered.add(dl)
                if debug:
                    prints(f'Ignoring the drive {dl} because failed to get free space for it')
        dlmap['drive_letters'] = [dl for dl in dlmap['drive_letters'] if dl not in filtered]

        if not dlmap['drive_letters']:
            raise DeviceError(_('Unable to detect any disk drives for the device: %s. Try rebooting') % self.get_gui_name())

        drives = {}

        for drive_letter, which in zip(dlmap['drive_letters'], 'main carda cardb'.split()):
            drives[which] = drive_letter + ':\\'

        drives = self.windows_sort_drives(drives)
        self._main_prefix = drives.get('main')
        self._card_a_prefix = drives.get('carda', None)
        self._card_b_prefix = drives.get('cardb', None)

    @classmethod
    def run_ioreg(cls, raw=None):
        if raw is not None:
            return raw
        ioreg = '/usr/sbin/ioreg'
        if not os.access(ioreg, os.X_OK):
            ioreg = 'ioreg'
        cmd = (ioreg+' -w 0 -S -c IOMedia').split()
        for i in range(3):
            try:
                return subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE).communicate()[0]
            except OSError:  # Probably an interrupted system call
                if i == 2:
                    raise
            time.sleep(2)

    def osx_sort_names(self, names):
        return names

    @classmethod
    def osx_run_mount(cls):
        for i in range(3):
            try:
                return subprocess.Popen('mount', stdout=subprocess.PIPE).communicate()[0].decode('utf-8', 'replace')
            except OSError:  # Probably an interrupted system call
                if i == 2:
                    raise
            time.sleep(2)

    @classmethod
    def osx_get_usb_drives(cls):
        from calibre_extensions.usbobserver import get_usb_drives
        return get_usb_drives()

    def _osx_bsd_names(self):
        drives = self.osx_get_usb_drives()
        matches = []
        d = self.detected_device
        if d.serial:
            for path, vid, pid, bcd, ven, prod, serial in drives:
                if d.match_serial(serial):
                    matches.append(path)
        if not matches and d.manufacturer and d.product:
            for path, vid, pid, bcd, man, prod, serial in drives:
                if d.match_strings(vid, pid, bcd, man, prod):
                    matches.append(path)
        if not matches:
            # Since Apple started mangling the names stored in the IOKit
            # registry, we cannot trust match_strings() so fallback to matching
            # on just numbers. See http://www.mobileread.com/forums/showthread.php?t=273213
            for path, vid, pid, bcd, man, prod, serial in drives:
                if d.match_numbers(vid, pid, bcd):
                    matches.append(path)
        if not matches:
            from pprint import pformat
            raise DeviceError(
                f'Could not detect BSD names for {self.name}. Try rebooting.\nOutput from osx_get_usb_drives():\n{pformat(drives)}')

        pat = re.compile(r'(?P<m>\d+)([a-z]+(?P<p>\d+)){0,1}')

        def nums(x):
            'Return (disk num, partition number)'
            m = pat.search(x)
            if m is None:
                return (10000, -1)
            g = m.groupdict()
            if g['p'] is None:
                g['p'] = 0
            return list(map(int, (g.get('m'), g.get('p'))))

        def cmp_key(x):
            '''
            Sorting based on the following scheme:
                - disks without partitions are first
                  - sub sorted based on disk number
                - disks with partitions are sorted first on
                  disk number, then on partition number
            '''
            x = x.rpartition('/')[-1]
            disk_num, part_num = nums(x)
            has_part = 1 if part_num > 0 else 0
            return has_part, disk_num, part_num

        matches.sort(key=cmp_key)
        drives = {'main':matches[0]}
        if len(matches) > 1:
            drives['carda'] = matches[1]
        if len(matches) > 2:
            drives['cardb'] = matches[2]

        return drives

    def osx_bsd_names(self):
        drives = {}
        for i in range(3):
            try:
                drives = self._osx_bsd_names()
                if len(drives) > 1:  # wait for device to settle and SD card (if any) to become available
                    return drives
            except Exception:
                if i == 2:
                    raise
            time.sleep(3)
        return drives

    def open_osx(self):
        from calibre_extensions.usbobserver import get_mounted_filesystems
        bsd_drives = self.osx_bsd_names()
        drives = self.osx_sort_names(bsd_drives.copy())
        mount_map = get_mounted_filesystems()
        # macOS 13 Ventura uses a weird scheme for mounted FAT devices of the
        # form fat://basename_of_bsd_name/basename_of_mountpoint
        # see https://www.mobileread.com/forums/showthread.php?t=347294
        for dev_node in tuple(mount_map):
            if ':' in dev_node and '//' in dev_node:
                val = mount_map[dev_node]
                dev_node = dev_node.split('/')[-2]
                dev_node = f'/dev/{dev_node}'
                if dev_node not in mount_map:
                    mount_map[dev_node] = val
        drives = {k: mount_map.get(v) for k, v in iteritems(drives)}
        if is_debugging():
            print()
            from pprint import pprint
            pprint({'bsd_drives': bsd_drives, 'mount_map': mount_map, 'drives': drives})
        if drives.get('carda') is None and drives.get('cardb') is not None:
            drives['carda'] = drives.pop('cardb')
        if drives.get('main') is None and drives.get('carda') is not None:
            drives['main'] = drives.pop('carda')
        if drives.get('carda') is None and drives.get('cardb') is not None:
            drives['carda'] = drives.pop('cardb')
        if drives.get('main') is None:
            raise DeviceError(_('Unable to detect the %s mount point. Try rebooting.')%self.__class__.__name__)
        pat = self.OSX_MAIN_MEM_VOL_PAT
        if pat is not None and len(drives) > 1 and 'main' in drives:
            if pat.search(drives['main']) is None:
                main = drives['main']
                for x in ('carda', 'cardb'):
                    if x in drives and pat.search(drives[x]):
                        drives['main'] = drives.pop(x)
                        drives[x] = main
                        break

        self._main_prefix = drives['main']+os.sep

        def get_card_prefix(c):
            ans = drives.get(c, None)
            if ans is not None:
                ans += os.sep
            return ans
        self._card_a_prefix = get_card_prefix('carda')
        self._card_b_prefix = get_card_prefix('cardb')

    def find_device_nodes(self, detected_device=None):

        def walk(base):
            base = os.path.abspath(os.path.realpath(base))
            for x in os.listdir(base):
                p = os.path.join(base, x)
                if os.path.islink(p) or not os.access(p, os.R_OK):
                    continue
                isfile = os.path.isfile(p)
                yield p, isfile
                if not isfile:
                    yield from walk(p)

        def raw2num(raw):
            raw = raw.lower()
            if not raw.startswith('0x'):
                raw = '0x' + raw
            return int(raw, 16)

        # Find device node based on vendor, product and bcd
        d, j = os.path.dirname, os.path.join
        usb_dir = None

        if detected_device is None:
            detected_device = self.detected_device

        def test(val, attr):
            q = getattr(detected_device, attr)
            return q == val

        def getnum(usb_dir):
            def rc(q):
                with open(j(usb_dir, q), 'rb') as f:
                    return raw2num(f.read().decode('utf-8'))
            return rc

        for x, isfile in walk('/sys/devices'):
            if isfile and x.endswith('idVendor'):
                usb_dir = d(x)
                for y in ('idProduct', 'idVendor', 'bcdDevice'):
                    if not os.access(j(usb_dir, y), os.R_OK):
                        usb_dir = None
                        break
                if usb_dir is None:
                    continue
                ven, prod, bcd = map(getnum(usb_dir), ('idVendor', 'idProduct', 'bcdDevice'))
                if not (test(ven, 'idVendor') and test(prod, 'idProduct') and
                        test(bcd, 'bcdDevice')):
                    usb_dir = None
                    continue
                else:
                    break

        if usb_dir is None:
            raise DeviceError(_('Unable to detect the %s disk drive.')
                    %self.__class__.__name__)

        devnodes, ok = [], {}
        for x, isfile in walk(usb_dir):
            if not isfile and '/block/' in x:
                parts = x.split('/')
                idx = parts.index('block')
                if idx == len(parts)-2:
                    sz = j(x, 'size')
                    node = parts[idx+1]
                    try:
                        with open(sz, 'rb') as szf:
                            exists = int(szf.read().decode('utf-8')) > 0
                        if exists:
                            node = self.find_largest_partition(x)
                            ok[node] = True
                        else:
                            ok[node] = False
                    except Exception:
                        ok[node] = False
                    if is_debugging() and not ok[node]:
                        print(f'\nIgnoring the node: {node} as could not read size from: {sz}')

                    devnodes.append(node)

        devnodes += list(repeat(None, 3))
        ans = ['/dev/'+x if ok.get(x) else None for x in devnodes]
        ans.sort(key=lambda x: x[5:] if x else 'zzzzz')
        return self.linux_swap_drives(ans[:3])

    def linux_swap_drives(self, drives):
        return drives

    def node_mountpoint(self, node):
        from calibre.devices.udisks import node_mountpoint
        return node_mountpoint(node)

    def find_largest_partition(self, path):
        node = path.split('/')[-1]
        nodes = []
        for x in glob.glob(path+'/'+node+'*'):
            sz = x + '/size'

            if not os.access(sz, os.R_OK):
                continue
            try:
                with open(sz, 'rb') as szf:
                    sz = int(szf.read().decode('utf-8'))
            except Exception:
                continue
            if sz > 0:
                nodes.append((x.split('/')[-1], sz))

        nodes.sort(key=lambda x: x[1])
        if not nodes:
            return node
        return nodes[-1][0]

    def open_linux(self):

        def mount(node, type):
            mp = self.node_mountpoint(node)
            if mp is not None:
                return mp, 0

            def do_mount(node):
                try:
                    from calibre.devices.udisks import mount
                    mount(node)
                    return 0
                except Exception:
                    print('Udisks mount call failed:')
                    import traceback
                    traceback.print_exc()
                    return 1

            ret = do_mount(node)
            if ret != 0:
                return None, ret
            return self.node_mountpoint(node)+'/', 0

        main, carda, cardb = self.find_device_nodes()
        if main is None:
            raise DeviceError(_('Unable to detect the %s disk drive. Either '
            'the device has already been ejected, or your '
            'kernel is exporting a deprecated version of SYSFS.')
                    %self.__class__.__name__)
        if is_debugging():
            print('\nFound device nodes:', main, carda, cardb)

        self._linux_mount_map = {}
        mp, ret = mount(main, 'main')
        if mp is None:
            raise DeviceError(
            _('Unable to mount main memory (Error code: %d)')%ret)
        if not mp.endswith('/'):
            mp += '/'
        self._linux_mount_map[main] = mp
        self._main_prefix = mp
        self._linux_main_device_node = main
        cards = [(carda, '_card_a_prefix', 'carda'),
                 (cardb, '_card_b_prefix', 'cardb')]
        for card, prefix, typ in cards:
            if card is None:
                continue
            mp, ret = mount(card, typ)
            if mp is None:
                print(f'Unable to mount card (Error code: {ret})', file=sys.stderr)
            else:
                if not mp.endswith('/'):
                    mp += '/'
                setattr(self, prefix, mp)
                self._linux_mount_map[card] = mp

        self.filter_read_only_mount_points()

    def filter_read_only_mount_points(self):

        def is_readonly(mp):
            if mp is None:
                return True
            path = os.path.join(mp, 'calibre_readonly_test')
            ro = True
            try:
                with open(path, 'wb'):
                    ro = False
            except Exception:
                pass
            else:
                try:
                    os.remove(path)
                except Exception:
                    pass
            if is_debugging() and ro:
                print('\nThe mountpoint', mp, 'is readonly, ignoring it')
            return ro

        for mp in ('_main_prefix', '_card_a_prefix', '_card_b_prefix'):
            if is_readonly(getattr(self, mp, None)):
                setattr(self, mp, None)

        if self._main_prefix is None:
            for p in ('_card_a_prefix', '_card_b_prefix'):
                nmp = getattr(self, p, None)
                if nmp is not None:
                    self._main_prefix = nmp
                    setattr(self, p, None)
                    break

        if self._main_prefix is None:
            raise DeviceError(_('The main memory of %s is read only. '
            'This usually happens because of file system errors.')
                    %self.__class__.__name__)

        if self._card_a_prefix is None and self._card_b_prefix is not None:
            self._card_a_prefix = self._card_b_prefix
            self._card_b_prefix = None

# ------------------------------------------------------
#
#  open for FreeBSD
#      find the device node or nodes that match the S/N we already have from the scanner
#      and attempt to mount each one
#              1.  get list of devices via DBUS UDisk2 with matching s/n etc.
#              2.  get list of volumes associated with each
#              3.  attempt to mount each one using UDisks2
#              4.  when finished, we have a list of mount points and associated dbus nodes
#
    def open_freebsd(self):
        from calibre.devices.udisks import find_device_vols_by_serial

        # There should be some way to access the -v arg...
        verbose = False

        # this gives us access to the S/N, etc. of the reader that the scanner has found
        # and the match routines for some of that data, like s/n, vendor ID, etc.
        d=self.detected_device

        if not d.serial:
            raise DeviceError("Device has no S/N.  Can't continue")

        vols = find_device_vols_by_serial(d.serial)

        if verbose:
            print('FBSD:\t', vols)

        ok, mv = self.freebsd_mount_volumes(vols)
        if not ok:
            raise DeviceError(_('Unable to mount the device'))
        for k, v in mv.items():
            setattr(self, k, v)

    def freebsd_mount_volumes(self, vols):
        def fmount(node):
            mp = self.node_mountpoint(node)
            if mp is not None:
                # Already mounted
                return mp

            from calibre.devices.udisks import mount, rescan
            for i in range(6):
                try:
                    mp = mount(node)
                    break
                except Exception:
                    if i < 5:
                        rescan(node)
                        time.sleep(1)
                    else:
                        print('Udisks mount call failed:')
                        import traceback
                        traceback.print_exc()

            return mp

        mp = None
        mtd = 0
        ans = {
            '_main_prefix': None, '_main_vol': None,
            '_card_a_prefix': None, '_card_a_vol': None,
            '_card_b_prefix': None, '_card_b_vol': None,
        }
        for vol in vols:
            try:
                mp = fmount(vol['Device'])
            except Exception:
                print('Failed to mount: ' + vol['Device'])
                import traceback
                traceback.print_exc()

            if mp is None:
                continue

            # Mount Point becomes Mount Path
            mp += '/'
            DEBUG = is_debugging()
            if DEBUG:
                print('FBSD:\tmounted', vol['Device'], 'on', mp)
            if mtd == 0:
                ans['_main_prefix'], ans['_main_vol'] = mp, vol['Device']
                if DEBUG:
                    print('FBSD:\tmain = ', mp)
            elif mtd == 1:
                ans['_card_a_prefix'], ans['_card_a_vol'] = mp, vol['Device']
                if DEBUG:
                    print('FBSD:\tcard a = ', mp)
            elif mtd == 2:
                ans['_card_b_prefix'], ans['_card_b_vol'] = mp, vol['Device']
                if DEBUG:
                    print('FBSD:\tcard b = ', mp)
                break
            mtd += 1

        return mtd > 0, ans

#
# ------------------------------------------------------
#
#    this one is pretty simple:
#        just umount each of the previously
#        mounted filesystems, using the stored volume object
#
    def eject_freebsd(self):
        from calibre.devices.udisks import umount
        if self._main_prefix:
            umount(self._main_vol)
        if self._card_a_prefix:
            umount(self._card_a_vol)
        if self._card_b_prefix:
            umount(self._card_b_vol)

        self._main_prefix = self._main_vol = None
        self._card_a_prefix = self._card_a_vol = None
        self._card_b_prefix = self._card_b_vol = None
# ------------------------------------------------------

    def is_folder_still_available(self):
        if self.eject_connected_folder:
            self.eject_connected_folder = False
            self.connected_folder_path = ''
        with suppress(OSError):
            if self.connected_folder_path:
                return os.path.isdir(self.connected_folder_path)
        return False

    def open(self, connected_device, library_uuid):
        self._main_prefix = self._card_a_prefix = self._card_b_prefix = None
        self.connected_folder_path = ''
        if getattr(connected_device, 'serial', None) and connected_device.serial.startswith(FAKE_DEVICE_SERIAL):
            folder_path = connected_device.serial[len(FAKE_DEVICE_SERIAL):]
            if not os.path.isdir(folder_path):
                raise DeviceError(f'The path {folder_path} is not a folder cannot connect to it')
            if not os.access(folder_path, os.R_OK | os.W_OK):
                raise DeviceError(f'You do not have permission to read and write to {folder_path} cannot connect to it')
            if not folder_path.endswith(os.sep) and not folder_path.endswith('/'):
                folder_path += os.sep
            self._main_prefix = folder_path
            self.current_library_uuid = library_uuid
            self.device_being_opened = connected_device
            try:
                self.post_open_callback()
            finally:
                self.device_being_opened = None
            self.connected_folder_path = folder_path
            return

        time.sleep(5)
        self.device_being_opened = connected_device
        try:
            if islinux:
                try:
                    self.open_linux()
                except DeviceError:
                    time.sleep(7)
                    self.open_linux()
            if isfreebsd:
                self._main_vol = self._card_a_vol = self._card_b_vol = None
                self.open_freebsd()
            if iswindows:
                self.open_windows()
            if ismacos:
                try:
                    self.open_osx()
                except DeviceError:
                    time.sleep(7)
                    self.open_osx()

            self.current_library_uuid = library_uuid
            self.post_open_callback()
        finally:
            self.device_being_opened = None

    def post_open_callback(self):
        pass

    def eject_windows(self):
        from threading import Thread
        drives = []
        for x in ('_main_prefix', '_card_a_prefix', '_card_b_prefix'):
            x = getattr(self, x, None)
            if x is not None:
                drives.append(x[0].upper())

        def do_it(drives):
            subprocess.Popen([eject_exe()] + drives, creationflags=subprocess.CREATE_NO_WINDOW).wait()

        t = Thread(target=do_it, args=[drives])
        t.daemon = True
        t.start()
        self.__save_win_eject_thread = t

    def eject_osx(self):
        for x in ('_main_prefix', '_card_a_prefix', '_card_b_prefix'):
            x = getattr(self, x, None)
            if x is not None:
                try:
                    subprocess.Popen(self.OSX_EJECT_COMMAND + [x])
                except Exception:
                    pass

    def eject_linux(self):
        from calibre.devices.udisks import eject, umount
        drives = [d for d in self.find_device_nodes() if d]
        for d in drives:
            try:
                umount(d)
            except Exception:
                pass
        for d in drives:
            try:
                eject(d)
            except Exception as e:
                print('Udisks eject call for:', d, 'failed:')
                print('\t', e)

    def on_device_close(self):
        pass

    def unmount_device(self):
        if self.connected_folder_path:
            self.eject_connected_folder = True

    def eject(self):
        if islinux:
            try:
                self.eject_linux()
            except Exception:
                pass
        if isfreebsd:
            try:
                self.eject_freebsd()
            except Exception:
                pass
        if iswindows:
            try:
                self.eject_windows()
            except Exception:
                pass
        if ismacos:
            try:
                self.eject_osx()
            except Exception:
                pass
        self._main_prefix = self._card_a_prefix = self._card_b_prefix = None
        self.on_device_close()

    def linux_post_yank(self):
        self._linux_mount_map = {}

    def post_yank_cleanup(self):
        if islinux:
            try:
                self.linux_post_yank()
            except Exception:
                import traceback
                traceback.print_exc()
        self._main_prefix = self._card_a_prefix = self._card_b_prefix = None
        self.on_device_close()

    def get_main_ebook_dir(self, for_upload=False):
        return self.EBOOK_DIR_MAIN

    def get_carda_ebook_dir(self, for_upload=False):
        return self.EBOOK_DIR_CARD_A

    def get_cardb_ebook_dir(self, for_upload=False):
        return self.EBOOK_DIR_CARD_B

    def _sanity_check(self, on_card, files):
        from calibre.devices.utils import sanity_check
        sanity_check(on_card, files, self.card_prefix(), self.free_space())

        def get_dest_dir(prefix, candidates):
            if isinstance(candidates, string_or_bytes):
                candidates = [candidates]
            if not candidates:
                candidates = ['']
            candidates = [
                ((os.path.join(prefix, *(x.split('/')))) if x else prefix)
                for x in candidates]
            existing = [x for x in candidates if os.path.exists(x)]
            if not existing:
                existing = candidates
            return existing[0]

        if on_card == 'carda':
            candidates = self.get_carda_ebook_dir(for_upload=True)
            path = get_dest_dir(self._card_a_prefix, candidates)
        elif on_card == 'cardb':
            candidates = self.get_cardb_ebook_dir(for_upload=True)
            path = get_dest_dir(self._card_b_prefix, candidates)
        else:
            candidates = self.get_main_ebook_dir(for_upload=True)
            path = get_dest_dir(self._main_prefix, candidates)

        return path

    def sanitize_callback(self, path):
        '''
        Callback to allow individual device drivers to override the path sanitization
        used by :meth:`create_upload_path`.
        '''
        return sanitize(path)

    def filename_callback(self, default, mi):
        '''
        Callback to allow drivers to change the default file name
        set by :meth:`create_upload_path`.
        '''
        return default

    def sanitize_path_components(self, components):
        '''
        Perform any device specific sanitization on the path components
        for files to be uploaded to the device
        '''
        return components

    def get_annotations(self, path_map):
        '''
        Resolve path_map to annotation_map of files found on the device
        '''
        return {}

    def add_annotation_to_library(self, db, db_id, annotation):
        '''
        Add an annotation to the calibre library
        '''
        pass

    def create_upload_path(self, path, mdata, fname, create_dirs=True):
        from calibre.devices.utils import create_upload_path
        settings = self.settings()
        filepath = create_upload_path(mdata, fname, self.save_template(), self.sanitize_callback,
                prefix_path=os.path.abspath(path),
                maxlen=self.MAX_PATH_LEN,
                use_subdirs=self.SUPPORTS_SUB_DIRS and settings.use_subdirs,
                news_in_folder=self.NEWS_IN_FOLDER,
                filename_callback=self.filename_callback,
                sanitize_path_components=self.sanitize_path_components
                )
        filedir = os.path.dirname(filepath)

        if create_dirs and not os.path.exists(filedir):
            os.makedirs(filedir)

        return filepath

    def create_annotations_path(self, mdata, device_path=None):
        return self.create_upload_path(os.path.abspath('/<storage>'), mdata, 'x.bookmark', create_dirs=False)
