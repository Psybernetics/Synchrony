"""
This file defines a dictionary of suite names to run function mappings.
Your tests should define a function that's the entry point to your test suite.
"""
from synchrony.tests import rpc_append_suite

maps = {
	'rpc_append': rpc_append_suite.run,
}
