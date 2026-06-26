import pytest


def pytest_addoption(parser):
    parser.addoption("--graph",      required=True, help="Path to road graph JSON to test")
    parser.addoption("--contiguity", default=None,  help="Path to contiguity graph JSON")
    parser.addoption("--reference",  default=None,  help="Path to reference graph JSON")
