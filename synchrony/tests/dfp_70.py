# _*_ coding: utf-8 _*_
"""
Test suite for a dishonest feedback percentage of 70%.
Nearly three quarters of network peers will be malign with colluding groups.
"""
import random
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

        # Set a positive (though constrained) trust rating on all peers
        for p in self.peers.values():
            for x in p:
                x.trust = random.randint(50, 60)

        # Make some transactions and then calculate_trust
        self.honest_peers.values()[0][revision] = revision
        self.honest_peers.values()[0].tbucket.calculate_trust()

        # Adjust trust ratings manually and then calculate_trust
        p = random.choice([p for p in self.peers[0]])
        p.trust = random.randint(1,100)
        self.honest_peers.values()[0].tbucket.calculate_trust()


def run():
    suite = unittest.TestSuite()
    suite.addTest(TestSuite('store_and_retrieve'))
    unittest.TextTestRunner(verbosity=2).run(suite)
