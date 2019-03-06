# Copyright (C) 2016-2017 Dmitry Marakasov <amdmi3@amdmi3.ru>
#
# This file is part of repology
#
# repology is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# repology is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with repology.  If not, see <http://www.gnu.org/licenses/>.

import os

from repology.atomic_fs import AtomicDir
from repology.fetchers import PersistentDirFetcher
from repology.subprocess import get_subprocess_output, run_subprocess


class GitFetcher(PersistentDirFetcher):
    def __init__(self, url, branch='master', sparse_checkout=None, fetch_timeout=600):
        self.url = url
        self.branch = branch
        self.sparse_checkout = sparse_checkout
        self.fetch_timeout = fetch_timeout

    def _setup_sparse_checkout(self, statedir: AtomicDir, logger):
        sparse_checkout_path = os.path.join(statedir.get_path(), '.git', 'info', 'sparse-checkout')

        # We always enable sparse checkout, as it's harder to
        # properly disable sparse checkout and restore all files
        # than to leave it enabled with all files whitelisted
        #
        # See https://stackoverflow.com/questions/36190800/how-to-disable-sparse-checkout-after-enabled/36195275
        run_subprocess(['git', 'config', 'core.sparsecheckout', 'true'], cwd=statedir.get_path(), logger=logger)
        with open(sparse_checkout_path, 'w') as sparse_checkout_file:
            if self.sparse_checkout:
                for item in self.sparse_checkout:
                    print(item, file=sparse_checkout_file)
            else:
                print('/*', file=sparse_checkout_file)

    def _do_fetch(self, statedir: AtomicDir, logger) -> bool:
        run_subprocess(['timeout', str(self.fetch_timeout), 'git', 'clone', '--progress', '--no-checkout', '--depth=1', '--branch', self.branch, self.url, statedir], logger=logger)
        self._setup_sparse_checkout(statedir, logger)
        run_subprocess(['git', 'checkout'], cwd=statedir.get_path(), logger=logger)

        return True

    def _do_update(self, statedir: AtomicDir, logger) -> bool:
        old_head = get_subprocess_output(['git', 'rev-parse', 'HEAD'], cwd=statedir.get_path(), logger=logger).strip()

        run_subprocess(['timeout', str(self.fetch_timeout), 'git', 'fetch', '--progress', '--depth=1'], cwd=statedir.get_path(), logger=logger)
        run_subprocess(['git', 'checkout'], cwd=statedir.get_path(), logger=logger)  # needed for reset to not fail on changed sparse checkout
        self._setup_sparse_checkout(statedir, logger)
        run_subprocess(['git', 'reset', '--hard', 'origin/' + self.branch], cwd=statedir.get_path(), logger=logger)
        run_subprocess(['git', 'reflog', 'expire', '--expire=0', '--all'], cwd=statedir.get_path(), logger=logger)
        run_subprocess(['git', 'prune'], cwd=statedir.get_path(), logger=logger)

        new_head = get_subprocess_output(['git', 'rev-parse', 'HEAD'], cwd=statedir.get_path(), logger=logger).strip()

        if new_head == old_head:
            logger.log('HEAD has not changed: {}'.format(new_head))
            return False

        logger.log('HEAD was updated from {} to {}'.format(old_head, new_head))
        return True
