# -*- coding: utf-8 -*-
'''
Module for interfacing with SysFS

.. seealso:: https://www.kernel.org/doc/Documentation/filesystems/sysfs.txt
.. versionadded:: Boron
'''
# Import python libs
from __future__ import absolute_import
import logging
import os
import stat

# Import external libs
import salt.ext.six as six

# Import salt libs
import salt.utils

log = logging.getLogger(__name__)


def __virtual__():
    '''
    Only work on Linux
    '''
    return salt.utils.is_linux()


def attr(key, value=None):
    '''
    Access/write a SysFS attribute.
    If the attribute is a symlink, it's destination is returned

    :return: value or bool

    CLI example:
     .. code-block:: bash

        salt '*' sysfs.attr block/sda/queue/logical_block_size
    '''
    key = target(key)

    if key is False:
        return False
    elif os.path.isdir(key):
        return key
    elif value is not None:
        return write(key, value)
    else:
        return read(key)


def write(key, value):
    '''
    Write a SysFS attribute/action

    CLI example:
     .. code-block:: bash

        salt '*' sysfs.write devices/system/cpu/cpu0/cpufreq/scaling_governor 'performance'
    '''
    try:
        key = target(key)
        log.trace('Writing {0} to {1}'.format(value, key))
        with salt.utils.fopen(key, 'w') as twriter:
            twriter.write('{0}\n'.format(value))
            return True
    except:  # pylint: disable=bare-except
        return False


def read(key, root=None):
    '''
    Read from SysFS
    :param key: file or path in SysFS; if key is a list then root will be prefixed on each key
    :return: the full (tree of) SysFS attributes under key

    CLI example:
     .. code-block:: bash

        salt '*' sysfs.read class/net/em1/statistics
    '''

    if not isinstance(key, six.string_types):
        res = {}
        for akey in key:
            ares = read(os.path.join(root, akey))
            if ares is not False:
                res[akey] = ares
        return res

    key = target(os.path.join(root, key))
    if key is False:
        return False
    elif os.path.isdir(key):
        keys = interfaces(key)
        result = {}
        for subkey in keys['r'] + keys['rw']:
            subval = read(os.path.join(key, subkey))
            if subval is not False:
                subkeys = subkey.split('/')
                subkey = subkeys.pop()
                subresult = result
                if len(subkeys):
                    for skey in subkeys:
                        if skey not in subresult:
                            subresult[skey] = {}
                        subresult = subresult[skey]
                subresult[subkey] = subval
        return result
    else:
        try:
            log.trace('Reading {0}...'.format(key))

            # Certain things in SysFS are pipes 'n such.
            # This opens it non-blocking, which prevents indefinite blocking
            with os.fdopen(os.open(key, os.O_RDONLY | os.O_NONBLOCK)) as treader:
                # alternative method for the same idea, but only works for completely empty pipes
                # treader = select.select([treader], [], [], 1)[0][0]
                val = treader.read().strip()
                if not val:
                    return False
                try:
                    val = int(val)
                except:  # pylint: disable=bare-except
                    try:
                        val = float(val)
                    except:  # pylint: disable=bare-except
                        pass
                return val
        except:  # pylint: disable=bare-except
            return False


def target(key, full=True):
    '''
    Return the basename of a SysFS key path
    :param key: the location to resolve within SysFS
    :param full: full path instead of basename
    :return: fullpath or basename of path

    CLI example:
     .. code-block:: bash

        salt '*' sysfs.read class/ttyS0

    '''
    if not key.startswith('/sys'):
        key = os.path.join('/sys', key)
    key = os.path.realpath(key)

    if not os.path.exists(key):
        log.debug('Unkown SysFS key {0}'.format(key))
        return False
    elif full:
        return key
    else:
        return os.path.basename(key)


def interfaces(root):
    '''
    Generate a dictionary with all available interfaces relative to root.
    Symlinks are not followed.

    'r' interfaces are read-only
    'w' interfaces are write-only (e.g. actions)
    'rw' are interfaces that can both be read or written

    CLI example:
     .. code-block:: bash

        salt '*' sysfs.interfaces block/bcache0/bcache
    '''

    root = target(root)
    if root is False or not os.path.isdir(root):
        log.error('SysFS {0} not a dir'.format(root))
        return False

    readwrites = []
    reads = []
    writes = []

    for path, _, files in os.walk(root, followlinks=False):
        for afile in files:
            canpath = os.path.join(path, afile)

            if not os.path.isfile(canpath):
                continue

            stat_mode = os.stat(canpath).st_mode
            is_r = bool(stat.S_IRUSR & stat_mode)
            is_w = bool(stat.S_IWUSR & stat_mode)

            relpath = os.path.relpath(canpath, root)
            if is_w:
                if is_r:
                    readwrites.append(relpath)
                else:
                    writes.append(relpath)
            elif is_r:
                reads.append(relpath)
            else:
                log.warn('Unable to find any interfaces in {0}'.format(canpath))

    return {
        'r': reads,
        'w': writes,
        'rw': readwrites
    }
