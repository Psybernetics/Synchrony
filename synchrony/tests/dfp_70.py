# _*_ coding: utf-8 _*_
"""
Test suite for a dishonest feedback percentage of 70%.
Nearly three quarters of network peers will be malign with colluding groups.
"""
import hashlib
import unittest
from synchrony import db
from synchrony.models import Revision
from synchrony.controllers import dht
from synchrony.tests.utils import BaseSuite

class TestSuite(BaseSuite):

    dfp         = 0.7
    peer_amount = 100

    def store_and_retrieve(self):
        revision = Revision.query.first()

        # Permit this to compute in headless environments.
        if not revision:
            print "Couldn't find a revision to test with."
            choice = raw_input("Create revision [y/n]: ")
            if choice.lower() != "y":
                raise SystemExit
            revision         = Revision()
            revision.content = "Hello, world."
            revision.size    = len(revision.content)
            revision.hash    = hashlib.sha1(revision.content).hexdigest()
            revision.get_mimetype()
    
            db.session.add(revision)
            db.session.commit()
            print "New revision committed."

        self.peers[0][revision] = revision

        # Now that we've stored references to the 0th peer
        # let's see if we can find them from the 1st peer.
        self.assertEqual(self.peers[1][revision], revision)

def run():
    suite = unittest.TestSuite()
    suite.addTest(TestSuite('store_and_retrieve'))
    unittest.TextTestRunner(verbosity=2).run(suite)
