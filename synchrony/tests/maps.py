"""
This file defines a dictionary of suite names to run function mappings.
Your tests should define a function that's the entry point to your test suite.
"""
from synchrony.tests import dfp_70
from synchrony.tests import rpc_append_suite
from synchrony.tests import rpc_friend_suite

maps = {
	'dfp_70':     dfp_70.run,
	'rpc_append': rpc_append_suite.run,
    'rpc_friend': rpc_friend_suite.run,          
}
