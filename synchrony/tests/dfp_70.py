# _*_ coding: utf-8 _*_
"""
Test sim for 70% dishonest feedback. Nearly three quarters of network nodes
will be malign, with colluding groups.
"""

import hashlib
import unittest
from synchrony.models import Revision
from synchrony.controllers import dht
from synchrony.tests.utils import BaseSuite

class TestSuite(BaseSuite):

    peer_amount = 250
    storage_method = "rpc_append"

    def store_and_retrieve(self):
        rev = Revision.query.first()
        if not rev:
            print "Couldn't find a revision to test with."
            print "You may want to browse with Synchrony and try again."
            raise SystemExit
        self.peers[0][rev] = rev

        # Now that we've stored references to the 0th peer
        # let's see if we can find them from the 1st peer.
        self.assertEqual(self.peers[1][rev], rev)

def run():
    suite = unittest.TestSuite()
    suite.addTest(TestSuite('store_and_retrieve'))
    unittest.TextTestRunner(verbosity=2).run(suite)
