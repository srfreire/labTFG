"""Benchmark / golden-scenario evaluation harness for the virtual lab (Phase 2).

Contains reference baseline models that anchor the behavioural metrics used by
the golden scenarios: an optimal forager (performance ceiling) and a random
agent (performance floor). Phase 1 generated models are expected to fall
between these two bounds, close to the oracle when they forage well.
"""
